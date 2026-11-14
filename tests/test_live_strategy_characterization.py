"""
Characterization tests of the LIVE strategy (``strategy.py``).

These tests do not involve the backtester at all. They pin what the live decision code
does TODAY, so that an accidental edit of ``strategy.py`` -- the file that decides
real-money orders -- is caught before it is deployed, and so that the backtester's claim
"same rules as live" keeps referring to a known set of rules.

Two variants of ``strategy.py`` exist in the fleet and this file passes on both; the
variant is detected at import:

* hedging (no ``BOOK_SCORE_WEIGHTS``): a basket is closed at the ``+$unit`` target
  (``profit > close_threshold``, the caller passes ``close_threshold = unit``), else by
  the force-close score.
* netting (has ``BOOK_SCORE_WEIGHTS``): no target; a basket in profit by more than
  ``unit * PROFIT_PROTECT_USD_PER_UNIT`` is booked when the BOOK score reverses, else it
  is closed by the force-close score.

The rules are written against the thresholds and timeframe weights CONFIGURED in
``constants.py`` (read through the strategy module), so retuning a threshold does not
break them. ``test_configured_thresholds_snapshot`` is the one deliberate exception: it
pins the numbers themselves.
"""

from __future__ import annotations

import inspect
import itertools

import numpy as np
import pytest

import strategy as S
from strategy import Signal, Strategy

IS_NETTING = hasattr(S, "BOOK_SCORE_WEIGHTS")
VARIANT = "netting" if IS_NETTING else "hedging"

NONE, BUY, SELL = Signal.DO_NOTHING, Signal.BUY, Signal.SELL
CLOSE_BUY, CLOSE_SELL, BUY_MORE, SELL_MORE = Signal.CLOSE_BUY, Signal.CLOSE_SELL, Signal.BUY_MORE, Signal.SELL_MORE

# The ladder tier of each open-position count is hard-coded in strategy.py: 1 -> M1 ... 5 -> H4.
LADDER_KEYS = ["TIMEFRAME_M1", "TIMEFRAME_M5", "TIMEFRAME_M15", "TIMEFRAME_H1", "TIMEFRAME_H4"]

# One timeframe's (rsi_sign, macd_sign) -> what it contributes per unit of weight.
RAW_VOTE = {(-1, -1): -2, (-1, 0): -1, (-1, 1): 0, (0, -1): -1, (0, 0): 0, (0, 1): 1, (1, -1): 0, (1, 0): 1, (1, 1): 2}
# grey_fill: a single grey (0) sign borrows the other indicator's sign; split and both-grey are unchanged.
GREY_VOTE = {(-1, -1): -2, (-1, 0): -2, (-1, 1): 0, (0, -1): -2, (0, 0): 0, (0, 1): 2, (1, -1): 0, (1, 0): 2, (1, 1): 2}

SECTION_WEIGHTS = [S.OPEN_SCORE_WEIGHTS, S.FORCE_CLOSE_SCORE_WEIGHTS] + ([S.BOOK_SCORE_WEIGHTS] if IS_NETTING else [])
SCORE_TFS = list(dict.fromkeys(tf for w in SECTION_WEIGHTS for tf in w))
# timeframes no section reads: their slopes must never influence a decision
NOISE_TFS = [tf for tf in ("D1", "H4", "H1", "M30", "M15", "M5", "M1") if tf not in SCORE_TFS][:2]


def _slope(sign: int) -> dict:
    """A slope record shaped like Indicator.latest_pivot_slope's return value."""
    return {"side": None if sign == 0 else ("low" if sign > 0 else "high"),
            "value": None if sign == 0 else 50.0, "bars_ago": None if sign == 0 else 3,
            "slope": float(sign), "sign": sign}


def slopes_from(signs: dict) -> dict:
    """{tf: (rsi_sign, macd_sign)} -> the ``slopes`` argument of calculate_signal."""
    return {tf: {"rsi": _slope(r), "macd": _slope(m)} for tf, (r, m) in signs.items()}


def score(signs: dict, weights: dict, grey_fill: bool) -> float:
    """Independent statement of Strategy._weighted_score."""
    table = GREY_VOTE if grey_fill else RAW_VOTE
    return sum(w * table[signs.get(tf, (0, 0))] for tf, w in weights.items())


def scores(signs: dict):
    """(open, force-close, book-or-None) for a sign assignment, as the live variant computes them."""
    return (score(signs, S.OPEN_SCORE_WEIGHTS, True),
            score(signs, S.FORCE_CLOSE_SCORE_WEIGHTS, False),
            score(signs, S.BOOK_SCORE_WEIGHTS, True) if IS_NETTING else None)


def _sign_space():
    """Every (rsi, macd) sign assignment over the scored timeframes (sampled if that is too many)."""
    n = 2 * len(SCORE_TFS)
    if 3 ** n <= 729:
        combos = list(itertools.product((-1, 0, 1), repeat=n))
    else:
        rng = np.random.default_rng(2026)
        combos = [tuple(int(x) for x in rng.integers(-1, 2, n)) for _ in range(700)]
        combos += [tuple([s] * n) for s in (-1, 0, 1)]
    return [{tf: (c[2 * i], c[2 * i + 1]) for i, tf in enumerate(SCORE_TFS)} for c in combos]


SIGN_SPACE = _sign_space()


def find_signs(predicate):
    """First sign assignment whose (open, fc, book) scores satisfy ``predicate``; skips if the config allows none."""
    for signs in SIGN_SPACE:
        if predicate(*scores(signs)):
            return signs
    pytest.skip("no slope combination produces these scores with the configured timeframe weights")


def position(count: int, profit: float, pos_type: int = 0, lots: float = 0.01) -> dict:
    """Shaped like MT5PositionHelper.get_buy_positions() / get_sell_positions()."""
    return {"type": pos_type, "count": count, "total_profit": profit, "total_volume": round(lots * count, 2),
            "first_profit": profit, "first_volume": lots, "last_profit": profit, "last_volume": lots}


def decide(signs, buy=None, sell=None, units=1, rsi_mtf=None, entry_allowed=True, close_threshold=None):
    """Call the live strategy the way app.py does (close_threshold = units)."""
    return Strategy().calculate_signal(
        None, buy, sell, units, close_threshold=units if close_threshold is None else close_threshold,
        rsi_value=(rsi_mtf or {}).get("TIMEFRAME_M1"), rsi_mtf=rsi_mtf, slopes=slopes_from(signs),
        entry_allowed=entry_allowed)


def all_rsi(value: float) -> dict:
    return {k: value for k in LADDER_KEYS}


def profit_bar(units: int) -> float:
    """The profit a basket must EXCEED before the variant's profit exit can fire."""
    return units * S.PROFIT_PROTECT_USD_PER_UNIT if IS_NETTING else float(units)


def expected_decision(signs, buy, sell, units, close_threshold, rsi_mtf, entry_allowed):
    """
    The decision table of calculate_signal, restated independently from its docstring.
    Returns (buy_signal, sell_signal, exit_reason).
    """
    open_s, fc_s, book_s = scores(signs)
    n_buy = buy["count"] if buy else 0
    n_sell = sell["count"] if sell else 0
    if n_buy == 0 and n_sell == 0:
        if entry_allowed and open_s >= S.ENTRY_S and fc_s >= S.ENTRY_AGREE_S:
            return BUY, NONE, None
        if entry_allowed and open_s <= -S.ENTRY_S and fc_s <= -S.ENTRY_AGREE_S:
            return NONE, SELL, None
        return NONE, NONE, None
    if n_buy > 0 and n_sell > 0:
        return NONE, NONE, None                       # both sides open: the strategy stands aside
    side = 1 if n_buy else -1
    pos = buy if n_buy else sell
    close = (CLOSE_BUY, NONE) if side > 0 else (NONE, CLOSE_SELL)
    more = (BUY_MORE, NONE) if side > 0 else (NONE, SELL_MORE)
    # 1. the profit exit
    if IS_NETTING:
        if pos["total_profit"] > units * S.PROFIT_PROTECT_USD_PER_UNIT and -side * book_s >= S.BOOK_S:
            return (*close, "book")
    elif pos["total_profit"] > close_threshold:
        return (*close, "target")
    # 2. the force-close
    if -side * fc_s >= S.FORCE_CLOSE_S:
        return (*close, "force_close")
    # 3. the RSI ladder, gated on the OPEN score, one tier per open count
    add_ok = open_s > -S.LADDER_S if side > 0 else open_s < S.LADDER_S
    if add_ok and 1 <= pos["count"] <= len(LADDER_KEYS):
        rsi = (rsi_mtf or {}).get(LADDER_KEYS[pos["count"] - 1], 50.0)
        if (rsi <= S.RSI_OVERSOLD) if side > 0 else (rsi >= S.RSI_OVERBOUGHT):
            return (*more, None)
    return NONE, NONE, None


# ───────────────────────────── basics ─────────────────────────────

def test_signal_enum_values():
    """
    Protects: the numeric signal codes. The backtester's kernel, its parity trace and the
    dashboard JSON all identify signals by these numbers / names.
    """
    assert {s.name: s.value for s in Signal} == {
        "DO_NOTHING": 0, "BUY": 1, "SELL": 2, "CLOSE_BUY": 3, "CLOSE_SELL": 4, "BUY_MORE": 5, "SELL_MORE": 6}


def test_configured_thresholds_snapshot():
    """
    Protects: the numbers the live bot trades with (and the backtest baseline was run
    with). This is a deliberate snapshot: if you retune ``constants.py`` on purpose,
    update the values here AND regenerate the backtest results -- the committed results
    describe the old numbers.
    """
    expected = {
        "ENTRY_S": 2, "ENTRY_AGREE_S": 2, "LADDER_S": 2, "FORCE_CLOSE_S": 1,
        "RSI_OVERSOLD": 35, "RSI_OVERBOUGHT": 65, "FIBO_SEQUENCE_LENGTH": 25,
        "OPEN_SCORE_WEIGHTS": {"H1": 1, "M15": 1},
        "FORCE_CLOSE_SCORE_WEIGHTS": {"M15": 1},
    }
    if IS_NETTING:
        expected.update({"BOOK_S": 1, "BOOK_SCORE_WEIGHTS": {"M15": 1}, "PROFIT_PROTECT_USD_PER_UNIT": 1.0})
    actual = {name: getattr(S, name) for name in expected}
    assert actual == expected, f"live {VARIANT} constants changed: {actual}"


def test_slope_sign_tolerates_missing_and_malformed_slopes():
    """
    Protects: a timeframe whose slope could not be computed (missing bars, a failed
    fetch) counts as "no direction" (0) instead of raising inside the trading loop.
    """
    good = slopes_from({"H1": (1, -1)})
    assert Strategy._slope_sign(good, "H1", "rsi") == 1
    assert Strategy._slope_sign(good, "H1", "macd") == -1
    assert Strategy._slope_sign(good, "M15", "rsi") == 0             # timeframe missing
    assert Strategy._slope_sign({"H1": {"rsi": {"sign": 1}}}, "H1", "macd") == 0   # indicator missing
    assert Strategy._slope_sign({"H1": {"rsi": {}}}, "H1", "rsi") == 0             # no 'sign'
    assert Strategy._slope_sign({"H1": {"rsi": None}}, "H1", "rsi") == 0
    assert Strategy._slope_sign({"H1": None}, "H1", "rsi") == 0
    assert Strategy._slope_sign(None, "H1", "rsi") == 0
    for junk in (2, -3, 0.5, None, "up", float("nan")):
        assert Strategy._slope_sign({"H1": {"rsi": {"sign": junk}}}, "H1", "rsi") == 0


# ───────────────────────────── _weighted_score ─────────────────────────────

@pytest.mark.parametrize("weight", [1, 3, 0.5, -2])
def test_weighted_score_single_timeframe_vote_table(weight):
    """
    Protects: how one timeframe votes. Raw: weight * (rsi_sign + macd_sign). With
    grey_fill a SINGLE grey sign borrows the other indicator's direction (a full +-2 vote),
    while split signs (+1 / -1) and both-grey stay 0. All nine sign pairs are pinned.
    """
    for (r, m), raw in RAW_VOTE.items():
        slopes = slopes_from({"M15": (r, m)})
        assert Strategy._weighted_score(slopes, {"M15": weight}) == weight * raw
        assert Strategy._weighted_score(slopes, {"M15": weight}, grey_fill=False) == weight * raw
        assert Strategy._weighted_score(slopes, {"M15": weight}, grey_fill=True) == weight * GREY_VOTE[(r, m)]
    # the special cases named in the strategy's docstring
    assert Strategy._weighted_score(slopes_from({"M15": (0, 0)}), {"M15": weight}, grey_fill=True) == 0     # both grey
    assert Strategy._weighted_score(slopes_from({"M15": (1, -1)}), {"M15": weight}, grey_fill=True) == 0    # split
    assert Strategy._weighted_score(slopes_from({"M15": (0, -1)}), {"M15": weight}, grey_fill=True) == -2 * weight
    assert Strategy._weighted_score(slopes_from({"M15": (1, 0)}), {"M15": weight}, grey_fill=True) == 2 * weight


def test_weighted_score_sums_the_weight_map_and_ignores_everything_else():
    """
    Protects: a section score is the weighted sum over ITS OWN timeframe map only. A
    timeframe missing from the slopes contributes 0; a timeframe not in the map is
    ignored; an empty map scores 0. Range is +-(2 * sum|w|).
    """
    weights = {"M15": 4, "H1": 3, "H4": 2, "D1": 1}
    rng = np.random.default_rng(3)
    for _ in range(600):
        signs = {tf: (int(rng.integers(-1, 2)), int(rng.integers(-1, 2))) for tf in ("M5", "M15", "H1", "H4", "D1")}
        if rng.random() < 0.3:
            del signs[("M15", "H1", "H4", "D1")[int(rng.integers(0, 4))]]
        slopes = slopes_from(signs)
        for grey in (False, True):
            got = Strategy._weighted_score(slopes, weights, grey_fill=grey)
            assert got == score(signs, weights, grey)
            assert abs(got) <= 20
    assert Strategy._weighted_score(slopes_from({"M15": (1, 1)}), {}) == 0
    assert Strategy._weighted_score(None, weights) == 0
    assert Strategy._weighted_score({}, weights, grey_fill=True) == 0
    assert Strategy._weighted_score(slopes_from({tf: (1, 1) for tf in weights}), weights) == 20
    assert Strategy._weighted_score(slopes_from({tf: (-1, -1) for tf in weights}), weights) == -20


def test_live_sections_use_grey_fill_for_open_and_raw_signs_for_force_close():
    """
    Protects: which sections grey-fill. OPEN (and BOOK on netting) count a half-grey
    timeframe as a full vote; FORCE-CLOSE counts raw signs. Checked through
    calculate_signal's own reported scores for every sign combination.
    """
    for signs in SIGN_SPACE:
        _b, _s, an = decide(signs)
        open_s, fc_s, book_s = scores(signs)
        assert an["open_score"] == open_s
        assert an["fc_score"] == fc_s
        if IS_NETTING:
            assert an["book_score"] == book_s
        else:
            assert "book_score" not in an


# ───────────────────────────── _entry_direction ─────────────────────────────

def test_entry_direction_follows_the_configured_thresholds():
    """
    Protects: the fresh-entry rule with the configured ENTRY_S / ENTRY_AGREE_S.
    BUY iff open_score >= ENTRY_S and fc_score >= ENTRY_AGREE_S; SELL is the mirror;
    anything else waits. Both comparisons are inclusive.
    """
    e, a = S.ENTRY_S, S.ENTRY_AGREE_S
    top = 2 * max(abs(e), abs(a), 2) + 2
    grid = np.arange(-top, top + 0.25, 0.5)
    for open_s in grid:
        for fc_s in grid:
            want = "BUY" if (open_s >= e and fc_s >= a) else ("SELL" if (open_s <= -e and fc_s <= -a) else None)
            assert Strategy._entry_direction(float(open_s), float(fc_s)) == want, (open_s, fc_s)
    eps = 1e-9
    assert Strategy._entry_direction(e, a) == "BUY"
    assert Strategy._entry_direction(-e, -a) == ("SELL" if (e > 0 or a > 0) else "BUY")
    if e > 0:
        assert Strategy._entry_direction(e - eps, a + 5) is None
        assert Strategy._entry_direction(-e + eps, -a - 5) is None
    if a > 0:
        assert Strategy._entry_direction(e + 5, a - eps) is None
        assert Strategy._entry_direction(-e - 5, -a + eps) is None
        # the anti-"vibration" gate: OPEN wants in, FORCE-CLOSE does not agree -> wait
        assert Strategy._entry_direction(e + 5, 0) is None
        assert Strategy._entry_direction(-e - 5, 0) is None


# ───────────────────────────── calculate_signal: the whole table ─────────────────────────────

def _rsi_patterns(side: int, count: int):
    """RSI maps that separate 'the tier of this count is at its extreme' from everything else."""
    extreme, threshold = (0.0, S.RSI_OVERSOLD) if side > 0 else (100.0, S.RSI_OVERBOUGHT)
    inside = threshold + 0.01 if side > 0 else threshold - 0.01
    patterns = [None, all_rsi(50.0), all_rsi(extreme), all_rsi(100.0 - extreme)]
    if count <= len(LADDER_KEYS):
        tier = LADDER_KEYS[count - 1]
        on_threshold = all_rsi(50.0)
        on_threshold[tier] = float(threshold)          # exactly 35 / 65 still adds
        others_extreme = all_rsi(extreme)
        others_extreme[tier] = inside                   # every OTHER tier screams, this one does not
        patterns += [on_threshold, others_extreme]
    return patterns


def test_calculate_signal_matches_the_decision_table_exhaustively():
    """
    Protects: the complete decision order of the live strategy.

    For every slope-sign combination of the scored timeframes, for flat / long / short
    books with 1..7 positions, for profits below / exactly at / just above the profit
    bar, for RSI maps that put the right or the wrong ladder tier at its extreme, with and
    without the re-entry cooldown, and for units 1 and 3, the live result must equal the
    table:

      flat   -> BUY / SELL when the OPEN score is directional and FORCE-CLOSE agrees,
                only if entry is allowed (cooldown over)
      open   -> 1. profit exit (hedging: profit > close_threshold, reason 'target';
                   netting: profit > unit * PROFIT_PROTECT and BOOK score reversed, 'book')
                2. force-close when the FORCE-CLOSE score is against the basket
                3. ladder add when the OPEN score is not strongly adverse AND the RSI of
                   the tier belonging to the current position count is at its extreme
                   (count 1 -> M1, 2 -> M5, 3 -> M15, 4 -> H1, 5 -> H4; none from 6 on)
      both sides open -> nothing.

    Slopes of timeframes outside every section's weight map are set at random and must
    not matter.
    """
    rng = np.random.default_rng(77)
    strat = Strategy()
    n_calls = 0
    outcomes = set()
    for signs in SIGN_SPACE:
        noisy = dict(signs)
        for tf in NOISE_TFS:
            noisy[tf] = (int(rng.integers(-1, 2)), int(rng.integers(-1, 2)))
        slopes = slopes_from(noisy)
        for units in (1, 3):
            bar = profit_bar(units)
            cases = [(None, None, None, True), (None, None, None, False)]
            for side in (1, -1):
                for count in range(1, 8):
                    for profit in (-5.0 * bar, 0.0, bar, bar + 0.01, 5.0 * bar):
                        pos = position(count, profit, 0 if side > 0 else 1, 0.01 * units)
                        for rsi_mtf in _rsi_patterns(side, count):
                            cases.append((pos if side > 0 else None, pos if side < 0 else None, rsi_mtf, True))
            for buy, sell, rsi_mtf, entry_allowed in cases:
                got_buy, got_sell, an = strat.calculate_signal(
                    None, buy, sell, units, close_threshold=units, rsi_value=None, rsi_mtf=rsi_mtf,
                    slopes=slopes, entry_allowed=entry_allowed)
                want = expected_decision(signs, buy, sell, units, units, rsi_mtf, entry_allowed)
                assert (got_buy, got_sell, an["exit_reason"]) == want, (
                    f"{VARIANT}: signs {signs} scores {scores(signs)} buy {buy} sell {sell} units {units} "
                    f"rsi {rsi_mtf} entry_allowed {entry_allowed}: live {(got_buy, got_sell, an['exit_reason'])}")
                outcomes.add(want)
                n_calls += 1
    assert n_calls >= 20_000
    # every kind of decision occurred, so the comparison was not vacuous
    seen_signals = {s for o in outcomes for s in o[:2]}
    assert seen_signals == set(Signal), f"never produced: {set(Signal) - seen_signals}"
    assert {o[2] for o in outcomes} == {None, "force_close", "book" if IS_NETTING else "target"}


def test_cooldown_blocks_only_fresh_entries():
    """
    Protects: REENTRY cooldown semantics. ``entry_allowed=False`` suppresses BUY / SELL on
    a flat book but never an exit or a ladder add on an open basket.
    """
    bull = find_signs(lambda o, f, b: o >= S.ENTRY_S and f >= S.ENTRY_AGREE_S)
    bear = find_signs(lambda o, f, b: o <= -S.ENTRY_S and f <= -S.ENTRY_AGREE_S)
    assert decide(bull)[:2] == (BUY, NONE)
    assert decide(bear)[:2] == (NONE, SELL)
    assert decide(bull, entry_allowed=False)[:2] == (NONE, NONE)
    assert decide(bear, entry_allowed=False)[:2] == (NONE, NONE)
    # an open long whose force-close score has turned: closes even during the cooldown
    turned = find_signs(lambda o, f, b: -f >= S.FORCE_CLOSE_S)
    assert decide(turned, buy=position(1, -3.0), entry_allowed=False)[0] == CLOSE_BUY
    # an open long with the M1 tier oversold and a supportive score: adds even during the cooldown
    calm = find_signs(lambda o, f, b: o > -S.LADDER_S and -f < S.FORCE_CLOSE_S and (b is None or -b < S.BOOK_S))
    assert decide(calm, buy=position(1, -3.0), rsi_mtf=all_rsi(10.0), entry_allowed=False)[0] == BUY_MORE


def test_open_score_alone_is_not_enough_to_enter():
    """
    Protects: the anti-"vibration" agreement gate. When the OPEN score wants in but the
    FORCE-CLOSE score does not agree the bot WAITS and reports ``entry_chop_block``.
    """
    signs = find_signs(lambda o, f, b: o >= S.ENTRY_S and f < S.ENTRY_AGREE_S)
    buy, sell, an = decide(signs)
    assert (buy, sell) == (NONE, NONE)
    assert an["entry_direction"] == "WAIT" and an["entry_chop_block"] is True
    signs = find_signs(lambda o, f, b: o <= -S.ENTRY_S and f > -S.ENTRY_AGREE_S)
    buy, sell, an = decide(signs)
    assert (buy, sell) == (NONE, NONE) and an["entry_chop_block"] is True
    agreed = find_signs(lambda o, f, b: o >= S.ENTRY_S and f >= S.ENTRY_AGREE_S)
    assert decide(agreed)[2]["entry_chop_block"] is False


@pytest.mark.skipif(IS_NETTING, reason="hedging variant only: the +$unit target")
def test_hedging_target_is_first_strict_and_scales_with_the_unit():
    """
    Protects (hedging): the profit target. A basket closes with reason 'target' as soon
    as its floating profit is strictly ABOVE ``close_threshold`` (= the unit: $1 for unit
    1, $3 for unit 3) -- before the force-close and before any ladder add, whatever the
    scores say. Exactly at the threshold it does not close.
    """
    against = find_signs(lambda o, f, b: -f >= S.FORCE_CLOSE_S)          # force-close would fire too
    for side, close_sig, idx in ((1, CLOSE_BUY, 0), (-1, CLOSE_SELL, 1)):
        signs = against if side > 0 else {tf: (-r, -m) for tf, (r, m) in against.items()}
        extreme = all_rsi(0.0 if side > 0 else 100.0)
        for units in (1, 3, 10):
            kw = dict(units=units, rsi_mtf=extreme)
            pos = lambda p: {"buy" if side > 0 else "sell": position(2, p, 0 if side > 0 else 1)}
            res = decide(signs, **pos(units + 0.01), **kw)
            assert res[idx] == close_sig and res[2]["exit_reason"] == "target"
            # exactly at the threshold: not the target (here the force-close takes it instead)
            res = decide(signs, **pos(float(units)), **kw)
            assert res[idx] == close_sig and res[2]["exit_reason"] == "force_close"
    # a supportive score and a neutral RSI: profit above the unit still closes, below it holds
    calm = find_signs(lambda o, f, b: o > -S.LADDER_S and -f < S.FORCE_CLOSE_S)
    assert decide(calm, buy=position(1, 1.01))[0] == CLOSE_BUY
    assert decide(calm, buy=position(1, 1.00))[0] == NONE
    assert decide(calm, buy=position(1, 2.50), units=3)[0] == NONE         # unit 3 -> target $3
    assert decide(calm, buy=position(1, 3.01), units=3)[0] == CLOSE_BUY
    # the caller's close_threshold is what counts (app.py passes close_threshold=units)
    assert decide(calm, buy=position(1, 2.50), units=3, close_threshold=2)[0] == CLOSE_BUY


@pytest.mark.skipif(not IS_NETTING, reason="netting variant only: the slope profit-book")
def test_netting_book_needs_profit_and_a_reversed_book_score():
    """
    Protects (netting): the profit-book. A basket is booked (reason 'book') only when
    BOTH hold: profit strictly above ``unit * PROFIT_PROTECT_USD_PER_UNIT`` and the BOOK
    score reversed by BOOK_S against it. It is checked before the force-close. There is
    no USD target: a large profit with no reversal is held, and ``close_threshold`` is
    ignored.
    """
    rev = find_signs(lambda o, f, b: -b >= S.BOOK_S and -f >= S.FORCE_CLOSE_S)   # book AND force-close against a long
    for units in (1, 3, 10):
        bar = units * S.PROFIT_PROTECT_USD_PER_UNIT
        res = decide(rev, buy=position(2, bar + 0.01), units=units)
        assert res[0] == CLOSE_BUY and res[2]["exit_reason"] == "book"
        res = decide(rev, buy=position(2, bar), units=units)                    # not strictly above: no book
        assert res[0] == CLOSE_BUY and res[2]["exit_reason"] == "force_close"
        mirror = {tf: (-r, -m) for tf, (r, m) in rev.items()}
        res = decide(mirror, sell=position(2, bar + 0.01, 1), units=units)
        assert res[1] == CLOSE_SELL and res[2]["exit_reason"] == "book"
    calm = find_signs(lambda o, f, b: -b < S.BOOK_S and -f < S.FORCE_CLOSE_S and o > -S.LADDER_S)
    for threshold in (0, 1, 2):
        assert decide(calm, buy=position(1, 500.0), close_threshold=threshold)[0] == NONE


def test_force_close_beats_the_ladder_and_needs_no_profit():
    """
    Protects: exit priority. When the FORCE-CLOSE score is against the basket by
    FORCE_CLOSE_S the basket closes (reason 'force_close') at any loss, even if the
    ladder tier's RSI is at its extreme and the OPEN score would still allow an add.
    """
    signs = find_signs(lambda o, f, b: -f >= S.FORCE_CLOSE_S and o > -S.LADDER_S)
    res = decide(signs, buy=position(1, -25.0), rsi_mtf=all_rsi(0.0))
    assert res[0] == CLOSE_BUY and res[2]["exit_reason"] == "force_close" and res[2]["buy_add_ok"] is True
    mirror = {tf: (-r, -m) for tf, (r, m) in signs.items()}
    res = decide(mirror, sell=position(1, -25.0, 1), rsi_mtf=all_rsi(100.0))
    assert res[1] == CLOSE_SELL and res[2]["exit_reason"] == "force_close" and res[2]["sell_add_ok"] is True
    # the comparison is inclusive: exactly -FORCE_CLOSE_S closes
    edge = find_signs(lambda o, f, b: -f == S.FORCE_CLOSE_S)
    assert decide(edge, buy=position(1, -1.0))[0] == CLOSE_BUY


def test_ladder_adds_use_the_tier_of_the_current_position_count():
    """
    Protects: the DCA ladder. With N positions open only tier N's RSI is consulted
    (1 -> M1, 2 -> M5, 3 -> M15, 4 -> H1, 5 -> H4): a BUY adds at RSI <= RSI_OVERSOLD,
    a SELL at RSI >= RSI_OVERBOUGHT (both inclusive). Other tiers at their extreme do
    nothing, and from the sixth position on there are no more adds.
    """
    calm = find_signs(lambda o, f, b: abs(o) < S.LADDER_S and abs(f) < S.FORCE_CLOSE_S
                      and (b is None or abs(b) < S.BOOK_S))
    for count in range(1, 6):
        tier = LADDER_KEYS[count - 1]
        for side in (1, -1):
            threshold, extreme = (S.RSI_OVERSOLD, 0.0) if side > 0 else (S.RSI_OVERBOUGHT, 100.0)
            kw = "buy" if side > 0 else "sell"
            pos = {kw: position(count, -4.0, 0 if side > 0 else 1)}
            idx, more = (0, BUY_MORE) if side > 0 else (1, SELL_MORE)
            only_tier = all_rsi(50.0)
            only_tier[tier] = float(threshold)
            assert decide(calm, rsi_mtf=only_tier, **pos)[idx] == more, f"count {count} side {side}"
            just_inside = all_rsi(50.0)
            just_inside[tier] = threshold + (0.01 if side > 0 else -0.01)
            assert decide(calm, rsi_mtf=just_inside, **pos)[idx] == NONE
            others = all_rsi(extreme)
            others[tier] = 50.0
            assert decide(calm, rsi_mtf=others, **pos)[idx] == NONE, f"count {count}: a foreign tier triggered an add"
            wrong_way = all_rsi(100.0 - extreme)
            assert decide(calm, rsi_mtf=wrong_way, **pos)[idx] == NONE
    for count in (6, 7, 12):
        assert decide(calm, buy=position(count, -40.0), rsi_mtf=all_rsi(0.0))[:2] == (NONE, NONE)
        assert decide(calm, sell=position(count, -40.0, 1), rsi_mtf=all_rsi(100.0))[:2] == (NONE, NONE)
    # no RSI map at all -> every tier reads 50 -> never adds
    assert decide(calm, buy=position(1, -4.0), rsi_mtf=None)[:2] == (NONE, NONE)
    assert decide(calm, buy=position(1, -4.0), rsi_mtf={})[:2] == (NONE, NONE)


def test_ladder_add_is_blocked_when_the_open_score_is_strongly_adverse():
    """
    Protects: the "do not average into a trend" gate. A BUY basket may add only while
    open_score > -LADDER_S, a SELL basket only while open_score < +LADDER_S (strict).
    """
    def no_exit(f, b):
        return abs(f) < S.FORCE_CLOSE_S and (b is None or abs(b) < S.BOOK_S)

    adverse = find_signs(lambda o, f, b: o <= -S.LADDER_S and no_exit(f, b))
    res = decide(adverse, buy=position(1, -4.0), rsi_mtf=all_rsi(0.0))
    assert res[:2] == (NONE, NONE) and res[2]["buy_add_ok"] is False
    # the same adverse-for-longs score is fine for a short basket
    res = decide(adverse, sell=position(1, -4.0, 1), rsi_mtf=all_rsi(100.0))
    assert res[1] == SELL_MORE and res[2]["sell_add_ok"] is True
    adverse_short = find_signs(lambda o, f, b: o >= S.LADDER_S and no_exit(f, b))
    res = decide(adverse_short, sell=position(1, -4.0, 1), rsi_mtf=all_rsi(100.0))
    assert res[:2] == (NONE, NONE) and res[2]["sell_add_ok"] is False


def test_thresholds_are_read_at_call_time_and_boundaries_are_inclusive_or_strict_as_documented(monkeypatch):
    """
    Protects two things at once.

    1. The strategy reads its thresholds and weight maps from module globals on every
       call. The backtester's reference engine relies on exactly that to replay the live
       code under a different configuration (``reference._apply_config`` assigns
       ``strategy.ENTRY_S`` etc.); if the constants were ever bound at import time the
       parity check would silently compare against the wrong settings.
    2. Which comparisons are inclusive and which are strict, on a probe configuration
       where every boundary is reachable whatever ``constants.py`` currently holds:
         entry         open >= ENTRY_S   and fc >= ENTRY_AGREE_S      (inclusive)
         force-close   fc <= -FORCE_CLOSE_S                           (inclusive)
         ladder gate   open > -LADDER_S                               (strict)
         ladder RSI    rsi <= RSI_OVERSOLD / rsi >= RSI_OVERBOUGHT    (inclusive)
         book          book <= -BOOK_S (netting)                      (inclusive)
    """
    monkeypatch.setattr(S, "OPEN_SCORE_WEIGHTS", {"H4": 1})            # open  in {-2, 0, 2}
    monkeypatch.setattr(S, "FORCE_CLOSE_SCORE_WEIGHTS", {"M5": 0.5})   # fc    in {-1, -0.5, 0, 0.5, 1}
    monkeypatch.setattr(S, "ENTRY_S", 2)
    monkeypatch.setattr(S, "ENTRY_AGREE_S", 1)
    monkeypatch.setattr(S, "LADDER_S", 2)
    monkeypatch.setattr(S, "FORCE_CLOSE_S", 0.5)
    monkeypatch.setattr(S, "RSI_OVERSOLD", 30)
    monkeypatch.setattr(S, "RSI_OVERBOUGHT", 70)
    if IS_NETTING:
        monkeypatch.setattr(S, "BOOK_SCORE_WEIGHTS", {"M30": 0.5})     # book  in {-1, 0, 1}
        monkeypatch.setattr(S, "BOOK_S", 1)
        monkeypatch.setattr(S, "PROFIT_PROTECT_USD_PER_UNIT", 2.0)

    def run(h4=(0, 0), m5=(0, 0), m30=(0, 0), **kw):
        strat = Strategy()
        slopes = slopes_from({"H4": h4, "M5": m5, "M30": m30})
        return strat.calculate_signal(None, kw.get("buy"), kw.get("sell"), kw.get("units", 1),
                                      close_threshold=kw.get("units", 1), rsi_mtf=kw.get("rsi"), slopes=slopes,
                                      entry_allowed=True)

    # entry: both comparisons inclusive
    b, s, an = run(h4=(1, 1), m5=(1, 1))
    assert (b, s) == (BUY, NONE) and an["open_score"] == 2 and an["fc_score"] == 1
    assert run(h4=(1, 1), m5=(1, 0))[:2] == (NONE, NONE)            # fc 0.5 < ENTRY_AGREE_S
    assert run(h4=(1, -1), m5=(1, 1))[:2] == (NONE, NONE)           # open 0 < ENTRY_S
    assert run(h4=(-1, -1), m5=(-1, -1))[:2] == (NONE, SELL)
    assert run(h4=(-1, -1), m5=(0, -1))[:2] == (NONE, NONE)
    # force-close: inclusive at exactly -FORCE_CLOSE_S, for either side
    long_, short_ = position(1, -9.0), position(1, -9.0, 1)
    res = run(m5=(-1, 0), buy=long_)
    assert res[0] == CLOSE_BUY and res[2]["fc_score"] == -0.5 and res[2]["exit_reason"] == "force_close"
    assert run(m5=(0, 0), buy=long_)[0] == NONE
    assert run(m5=(0, 1), sell=short_)[1] == CLOSE_SELL
    # ladder gate: strict -- exactly -LADDER_S blocks a long, exactly +LADDER_S blocks a short
    low, high = all_rsi(30.0), all_rsi(70.0)
    assert run(h4=(-1, -1), buy=long_, rsi=low)[0] == NONE
    assert run(h4=(0, 0), buy=long_, rsi=low)[0] == BUY_MORE
    assert run(h4=(1, 1), sell=short_, rsi=high)[1] == NONE
    assert run(h4=(0, 0), sell=short_, rsi=high)[1] == SELL_MORE
    # ladder RSI: the patched 30 / 70 are in force (not the 35 / 65 of constants.py), inclusive
    assert run(buy=long_, rsi=all_rsi(30.01))[0] == NONE
    assert run(buy=long_, rsi=all_rsi(33.0))[0] == NONE
    assert run(sell=short_, rsi=all_rsi(69.99))[1] == NONE
    assert run(sell=short_, rsi=all_rsi(67.0))[1] == NONE
    if IS_NETTING:
        # book: inclusive at exactly -BOOK_S; profit bar = unit * the patched 2.0, strict
        res = run(m30=(-1, 0), buy=position(1, 2.01))
        assert res[0] == CLOSE_BUY and res[2]["book_score"] == -1 and res[2]["exit_reason"] == "book"
        assert run(m30=(-1, 0), buy=position(1, 2.00))[0] == NONE
        assert run(m30=(-1, 1), buy=position(1, 50.0))[0] == NONE              # split M30 -> book 0
        assert run(m30=(1, 1), sell=position(1, 2.01, 1))[1] == CLOSE_SELL
        assert run(m30=(1, 1), sell=position(1, 6.00, 1), units=3)[1] == NONE   # unit 3 -> bar $6, strict
        assert run(m30=(1, 1), sell=position(1, 6.01, 1), units=3)[1] == CLOSE_SELL
    else:
        assert run(buy=position(1, 1.01))[0] == CLOSE_BUY and run(buy=position(1, 1.00))[0] == NONE


def test_book_with_both_sides_open_is_left_alone():
    """
    Protects: a state the strategy never creates but a manual trade could -- buys and
    sells open together. Today the strategy returns DO_NOTHING for both sides: it neither
    closes, adds nor opens. (Pinned so that a change here is a conscious one.)
    """
    for signs in SIGN_SPACE[:: max(1, len(SIGN_SPACE) // 27)]:
        for profit in (-10.0, 50.0):
            res = decide(signs, buy=position(2, profit), sell=position(1, profit, 1), rsi_mtf=all_rsi(0.0))
            assert res[:2] == (NONE, NONE) and res[2]["exit_reason"] is None


def test_calculate_signal_defaults_and_analysis_contract():
    """
    Protects: the interface app.py, the dashboard and the backtester's reference engine
    rely on -- argument defaults (close_threshold 2, entry allowed) and the keys of the
    returned analysis dict (the reference engine reads open_score / fc_score / book_score
    / rsi_mtf / entry_allowed from it).
    """
    params = inspect.signature(Strategy.calculate_signal).parameters
    assert list(params) == ["self", "source_df", "buy_positions", "sell_positions", "times", "close_threshold",
                            "rsi_value", "rsi_mtf", "slopes", "entry_allowed"]
    assert params["close_threshold"].default == 2
    assert params["entry_allowed"].default is True
    assert params["rsi_mtf"].default is None and params["slopes"].default is None

    buy, sell, an = Strategy().calculate_signal(None, None, None, 1)
    assert (buy, sell) == (NONE, NONE)
    keys = {"rsi_value", "rsi_mtf", "slopes", "slope_direction", "entry_direction", "open_score", "fc_score",
            "buy_add_ok", "sell_add_ok", "entry_allowed", "entry_chop_block", "exit_reason"}
    if IS_NETTING:
        keys.add("book_score")
    assert set(an) == keys
    assert an["rsi_value"] == 50.0 and an["rsi_mtf"] == {} and an["slopes"] == {}
    assert an["slope_direction"] == "WAIT" and an["entry_direction"] == "WAIT"
    assert an["open_score"] == 0 and an["fc_score"] == 0 and an["exit_reason"] is None
    assert an["entry_allowed"] is True and an["entry_chop_block"] is False

    bull = find_signs(lambda o, f, b: o >= S.ENTRY_S and f >= S.ENTRY_AGREE_S)
    rsi = all_rsi(41.23456)
    _b, _s, an = Strategy().calculate_signal(None, None, None, 1, rsi_value=41.23456, rsi_mtf=rsi,
                                             slopes=slopes_from(bull))
    assert an["rsi_value"] == 41.23 and an["rsi_mtf"] is rsi and an["entry_direction"] == "BUY"


def test_slope_direction_is_display_only_and_follows_its_table():
    """
    Protects: ``_slope_direction`` -- the structural H4 / H1 / M15 read shown on the
    dashboard. Its table is pinned, and (in the exhaustive test above) it never affects
    a trading decision.
      H4 both up   & >=1 H1 up   & >=1 M15 up   -> BUY      (mirror for SELL)
      H4 split     & H1 both up  & >=1 M15 up   -> BUY      (mirror for SELL)
      anything else (incl. any grey H4 sign)    -> WAIT (None)
    """
    strat = Strategy()
    for h4r, h4m, h1r, h1m, m15r, m15m in itertools.product((-1, 0, 1), repeat=6):
        m15_up, m15_dn = (m15r > 0 or m15m > 0), (m15r < 0 or m15m < 0)
        if h4r > 0 and h4m > 0:
            want = "BUY" if ((h1r > 0 or h1m > 0) and m15_up) else None
        elif h4r < 0 and h4m < 0:
            want = "SELL" if ((h1r < 0 or h1m < 0) and m15_dn) else None
        elif h4r * h4m == -1:
            want = "BUY" if (h1r > 0 and h1m > 0 and m15_up) else ("SELL" if (h1r < 0 and h1m < 0 and m15_dn) else None)
        else:
            want = None
        slopes = slopes_from({"H4": (h4r, h4m), "H1": (h1r, h1m), "M15": (m15r, m15m)})
        assert strat._slope_direction(slopes) == want
    assert strat._slope_direction(None) is None and strat._slope_direction({}) is None


# ───────────────────────────── the Fibonacci lot ladder ─────────────────────────────

# unit -> the six lots of a full basket (entry + five adds)
FIBO_LOTS = {
    1: [0.01, 0.02, 0.03, 0.05, 0.08, 0.13],
    2: [0.02, 0.04, 0.06, 0.10, 0.16, 0.26],
    3: [0.03, 0.06, 0.09, 0.15, 0.24, 0.39],
    5: [0.05, 0.10, 0.15, 0.25, 0.40, 0.65],
    10: [0.10, 0.20, 0.30, 0.50, 0.80, 1.30],
}


@pytest.mark.parametrize("units", sorted(FIBO_LOTS))
def test_fibo_ladder_lots_through_all_six_positions(units):
    """
    Protects: position sizing. A basket is built as 0.01, 0.02, 0.03, 0.05, 0.08, 0.13
    lots times the unit: the entry is ``units * mtqty`` (app.py) and every add is
    ``_get_next_fibo_volume(total volume already open, units)``, fed -- as live -- with
    the 2-decimal total reported by the position helper. A full six-position basket is
    0.32 lots per unit. The literal lots for units 1, 2, 3, 5 and 10 are pinned.
    """
    strat = Strategy()
    want = FIBO_LOTS[units]
    assert want == [round(m * units * 0.01, 2) for m in (1, 2, 3, 5, 8, 13)]
    lots = [round(units * 0.01, 2)]                      # position 1: the entry order
    assert lots == want[:1]
    for n_open in range(1, 6):                           # positions 2..6: the ladder adds
        total = round(sum(lots), 2)
        got = strat._get_next_fibo_volume(total, units)
        assert got == want[n_open], f"unit {units}: with {total} lots open the next add is {got}, expected {want[n_open]}"
        lots.append(got)
    assert round(sum(lots), 2) == round(0.32 * units, 2)
    # were the ladder ever extended, the seventh rung would be the next Fibonacci number
    assert strat._get_next_fibo_volume(round(sum(lots), 2), units) == round(21 * units * 0.01, 2)


def test_fibo_volume_off_ladder_inputs():
    """
    Protects: how the sizing reacts to totals that are not on the ladder (a manual trade,
    a partial close). The total is first rounded to whole units, then the function moves
    to the rung whose cumulative size covers it. With nothing open it returns the SECOND
    rung (0.02 x unit) -- the entry itself never comes from this function.
    """
    strat = Strategy()
    assert strat._get_next_fibo_volume(0.0, 1) == 0.02
    assert strat._get_next_fibo_volume(0.0, 5) == 0.10
    assert strat._get_next_fibo_volume(0.02, 1) == 0.03       # between rung 1 (0.01) and rung 2 (0.03 in total)
    assert strat._get_next_fibo_volume(0.04, 1) == 0.05
    assert strat._get_next_fibo_volume(0.07, 1) == 0.08
    assert strat._get_next_fibo_volume(0.06, 5) == 0.10       # 1.2 units rounds to 1 -> still rung 1
    assert strat._get_next_fibo_volume(0.08, 5) == 0.15       # 1.6 units rounds to 2 -> past rung 1
    assert [strat._get_fibo_qty(i, 1) for i in range(7)] == [1, 2, 3, 5, 8, 13, 21]
    assert strat._get_fibo_qty(2, 4) == 12
    assert strat._get_fibo_qty(10_000, 4) == 4                # out of range -> the bare unit
