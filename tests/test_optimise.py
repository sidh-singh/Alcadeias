"""
The optimiser (``backtesting/optimise.py``).

* A search space is read from JSON: value lists, ranges, log scales, labelled lists and dicts,
  price-scaled parameters, conditions and constraints. Unknown names are errors.
* The samplers are reproducible from a seed, give every equivalent setting once and never a
  setting that breaks a constraint.
* The period is cut into blocks and months counted from its start; a hold-out sits on block
  boundaries; history before 2024 is refused unless unlocked.
* On the bundled ticks: the months of a block add up to its net P/L and agree with an
  independent run of the engine; results are stored as they arrive, a second run computes
  nothing, an interrupted one continues, and results of another build are never reused.
* On synthetic month-by-setting matrices, where the right answer is known: the objectives, the
  overfitting probability (one half on noise, zero with one genuinely better setting), the
  haircut for the number of settings tried, the walk-forward (which cannot see the future), the
  hold-out (which cannot influence the choice) and the stability tables.
* The command line, end to end, and the raw-tick validation of the short list.
"""

from __future__ import annotations

import itertools
import json
import math
import shlex
from collections import Counter

import numpy as np
import pandas as pd
import pytest

from backtesting import cli
from backtesting import optimise as O
from backtesting.config import BacktestConfig, FIBO

SYM = "BTCUSDm"
HOUR = ("2026-11-09 06:00", "2026-11-09 07:00")          # the bundled BTC ticks
V2 = {"trend_tf": "H1", "max_adds": 0, "target_usd_per_unit": 20, "stop_loss_usd_per_unit": 20,
      "force_close_enabled": False, "loss_cooldown_s": 14400}

# a small space whose answers can be counted by hand: 3 x 2 x 3 raw combinations
TINY = {
    "name": "tiny",
    "parameters": {
        "max_adds": [0, 1, 2],
        "ladder_multipliers": {"values": {"flat": [1, 1, 1], "linear": [1, 2, 3]}},
        "target_usd_per_unit": [0.5, 1, 2],
    },
    "conditions": [{"when": "max_adds == 0", "ignore": ["ladder_multipliers"]}],
    # (the target is named so that this reference is one of the 15 settings on both variants: the netting
    #  variant's own profit exit is the slope book, not a target)
    "references": {"no ladder": {"max_adds": 0, "target_usd_per_unit": 1}},
}


def quiet(_msg: str) -> None:
    pass


# ───────────────────────────── search spaces ─────────────────────────────

def test_value_lists_ranges_and_log_scales_become_ordered_values():
    sp = O.Space({"parameters": {
        "max_adds": {"range": [0, 4], "step": 1},
        "stop_loss_usd_per_unit": {"range": [10, 40], "step": 7.5},
        "loss_cooldown_s": {"range": [300, 28800], "log": True, "n": 4},
        "entry_confirm_s": {"range": [0, 300], "n": 4},
        "rsi_length": {"range": [5, 40], "log": True, "n": 4, "int": True},
        "trend_tf": [None, "H1", "H4"],
    }})
    by = {p.name: p for p in sp.params}
    assert by["max_adds"].values == [0, 1, 2, 3, 4] and all(isinstance(v, int) for v in by["max_adds"].values)
    assert by["stop_loss_usd_per_unit"].values == [10, 17.5, 25, 32.5, 40]
    assert by["loss_cooldown_s"].values == [300.0, 1370.0, 6290.0, 28800.0]        # geometric, three significant digits
    assert by["entry_confirm_s"].values == [0, 100, 200, 300]
    assert by["rsi_length"].values == [5, 10, 20, 40]
    assert by["trend_tf"].values == [None, "H1", "H4"]
    # numbers have an order (neighbours are the values next door), names do not unless the file says so
    assert by["max_adds"].ordered and by["loss_cooldown_s"].ordered and not by["trend_tf"].ordered
    assert sp.size() == 5 * 5 * 4 * 4 * 4 * 3


@pytest.mark.parametrize("symbol, px", [("XAUUSDm", 1.0), ("BTCUSDm", 100.0)])
def test_price_scaled_parameters_follow_the_symbol(symbol, px):
    """A parameter in price units is written once, in USD per 0.01 lot, and scaled by the symbol's contract."""
    sp = O.Space({"base": {"entry_max_spread": 0.5},
                  "price_units": ["entry_max_spread"],
                  "parameters": {"ladder_min_gap": {"values": [0, 3, 5], "scale": "price"}, "max_adds": [1, 2]},
                  "constraints": ["ladder_min_gap * max_adds <= 6"],
                  "references": {"wide": {"ladder_min_gap": 8}}},
                 live=BacktestConfig(symbol=symbol))
    assert sp.px == px
    grid = sp.grid()
    assert len(grid) == 5                                    # (5, 2) breaks the constraint, which is in file units
    c = next(c for c in grid if sp.values(c) == {"ladder_min_gap": 3, "max_adds": 2})
    assert sp.overrides(c) == {"entry_max_spread": 0.5 * px, "ladder_min_gap": 3.0 * px, "max_adds": 2}
    assert sp.config(c).ladder_min_gap == 3.0 * px and sp.config(c).entry_max_spread == 0.5 * px
    assert sp.references["wide"] == {"ladder_min_gap": 8.0 * px}


def test_lists_and_dicts_are_choices_with_labels():
    sp = O.Space({"parameters": {
        "ladder_multipliers": {"values": {"flat": [1, 1, 1], "fibonacci": list(FIBO[:6])}},
        "open_weights": [{"H1": 1, "M15": 1}, {"H4": [1, 0], "M15": [0, 1]}],
    }})
    mult, weights = sp.params
    assert mult.labels == ["flat", "fibonacci"]
    assert weights.labels == ['{"H1":1,"M15":1}', '{"H4":[1,0],"M15":[0,1]}']         # no names given: compact JSON
    c = sp.canonical((1, 1))
    cfg = sp.config(c)
    assert cfg.ladder_multipliers == [1.0, 2.0, 3.0, 5.0, 8.0, 13.0]
    assert cfg.open_weights == {"H4": (1.0, 0.0), "M15": (0.0, 1.0)}
    assert sp.values(c) == {"ladder_multipliers": "fibonacci", "open_weights": '{"H4":[1,0],"M15":[0,1]}'}
    # the configuration, not the spelling, is the identity of a setting
    again = O.Space({"parameters": {"ladder_multipliers": {"values": {"a": [1.0, 1, 1], "b": list(FIBO[:6])}},
                                    "open_weights": [{"M15": 1, "H1": [1, 1]}, {"M15": [0, 1], "H4": [1, 0]}]}})
    assert [again.key(c) for c in again.grid()] == [sp.key(c) for c in sp.grid()]


@pytest.mark.parametrize("spec, needle", [
    ({"parameters": {"no_such_field": [1, 2]}}, "unknown BacktestConfig field(s): no_such_field"),
    ({"base": {"no_such_field": 1}}, "unknown BacktestConfig field(s): no_such_field"),
    ({"references": {"x": {"no_such_field": 1}}}, "reference x: unknown BacktestConfig field(s)"),
    ({"parameters": {"max_adds": [0, 1]}, "conditions": [{"when": "max_adds == 0", "ignore": ["rsi_length"]}]},
     "rsi_length is not a parameter of this space"),
    ({"parameters": {"max_adds": [0, 1]}, "constraints": ["max_add > 0"]}, "max_add in 'max_add > 0' is not a field"),
    ({"base": {"start": "2026-01-01"}}, "start is set by the optimiser"),
    ({"parameters": {"fixed_units": [1, 2]}}, "fixed_units is set by the optimiser"),
    ({"base": {"max_adds": 0}, "parameters": {"max_adds": [0, 1]}}, "a field is fixed or varied, not both"),
    ({"parameters": {"target_usd_per_unit": [20, 20.0]}}, "listed twice"),
    ({"parameters": {"open_weights": [{"H1": 1}, {"H1": [1, 1]}]}}, "listed twice"),
    ({"parameters": {"trend_tf": ["H1", "H7"]}}, "timeframe"),
    ({"parameters": {"ladder_multipliers": [[2, 2, 2]]}}, "ladder_multipliers[0] is the entry"),
    ({"parameters": {"max_adds": {"range": [0, 4]}}}, "a range needs"),
    ({"parameters": {"max_adds": {"values": [1], "range": [0, 4], "step": 1}}}, "either \"values\""),
    ({"parameters": {"max_adds": []}}, "no values"),
    ({"parameters": {"max_adds": {"values": [1, 2], "scale": "log"}}}, "the only \"scale\" is \"price\""),
    ({"parameters": {"max_adds": [0, 1]}, "conditions": [{"when": "max_adds == 0", "fix": {"max_adds": 7}}]},
     "7 is not one of the values of max_adds"),
    ({"parameters": {"max_adds": [0, 1]}, "sampler": "grid"}, "unknown key(s) in the search space: sampler"),
])
def test_what_a_space_cannot_say_is_an_error_that_names_it(spec, needle):
    with pytest.raises(O.SpaceError) as e:
        O.Space(spec)
    assert needle in str(e.value)


@pytest.mark.parametrize("text", ["max_adds.real > 0", "__import__('os')", "max_adds[0] > 0", "(lambda: 1)()",
                                  "[x for x in (1, 2)]", "open('f')", "max_adds ** 99 > 0", "max_adds >"])
def test_expressions_are_limited_to_comparisons_and_arithmetic(text):
    with pytest.raises(O.SpaceError):
        O.Space({"parameters": {"max_adds": [0, 1]}, "constraints": [text]})


def test_expressions_read_labels_json_words_and_fail_loudly_on_none():
    sp = O.Space({"parameters": {"trend_tf": [None, "H1"], "stop_loss_usd_per_unit": [None, 10, 20],
                                 "ladder_multipliers": {"values": {"flat": [1, 1], "linear": [1, 2]}},
                                 "force_close_enabled": [False, True]},
                  "constraints": ["trend_tf == null or stop_loss_usd_per_unit is not None",
                                  "not (ladder_multipliers == 'linear' and force_close_enabled == true)",
                                  "stop_loss_usd_per_unit is None or abs(stop_loss_usd_per_unit - 15) <= max(5, 1)"]})
    got = [sp.values(c) for c in sp.grid()]
    assert len(got) == 2 * 3 * 2 * 2 - 4 - 6 + 1          # 4 with a trend and no stop, 6 linear with force-close, 1 both
    assert not any(v["trend_tf"] == "H1" and v["stop_loss_usd_per_unit"] is None for v in got)
    assert not any(v["ladder_multipliers"] == "linear" and v["force_close_enabled"] for v in got)
    bad = O.Space({"parameters": {"stop_loss_usd_per_unit": [None, 10]}, "constraints": ["stop_loss_usd_per_unit > 5"]})
    with pytest.raises(O.SpaceError, match="cannot be worked out with stop_loss_usd_per_unit=None"):
        bad.grid()


def test_conditions_reduce_equivalent_settings_to_one():
    sp = O.Space({"parameters": {
        "max_adds": [0, 1, 2, 3],
        "ladder_multipliers": {"values": {"flat": [1, 1, 1, 1], "linear": [1, 2, 3, 4], "fibonacci": [1, 2, 3, 5]}},
        "ladder_min_gap": [0, 5],
        "target_usd_per_unit": [1, 5],
    }, "conditions": [
        {"when": "max_adds == 0", "ignore": ["ladder_multipliers", "ladder_min_gap"]},
        {"when": "max_adds <= 2 and ladder_multipliers == 'fibonacci'", "fix": {"ladder_multipliers": "linear"}},
    ], "constraints": ["ladder_min_gap * max_adds <= 10"]})
    assert sp.size() == 4 * 3 * 2 * 2
    grid = sp.grid()
    # no ladder: 2 targets. One or two adds: flat or linear x 2 gaps x 2 targets. Three adds: three shapes, and the
    # gap of 5 is out (5 x 3 > 10). The constraint does not apply where the gap is switched off.
    assert len(grid) == 2 + 2 * (2 * 2 * 2) + 3 * 1 * 2 == len(set(grid)) == len({sp.key(c) for c in grid})
    # every raw combination lands on one of them, and equivalent ones on the same
    for raw in itertools.product(range(4), range(3), range(2), range(2)):
        c = sp.canonical(raw)
        assert c is None or c in grid
    assert sp.canonical((0, 0, 0, 1)) == sp.canonical((0, 2, 1, 1)) == (0, None, None, 1)
    assert sp.canonical((2, 2, 1, 0)) == sp.canonical((2, 1, 1, 0)) == (2, 1, 1, 0)
    assert sp.canonical((3, 2, 0, 0)) == (3, 2, 0, 0) and sp.canonical((3, 2, 1, 0)) is None
    # a switched-off parameter is not overridden at all: it stays at the base configuration's value
    off = sp.canonical((0, 2, 1, 1))
    assert sp.values(off) == {"max_adds": 0, "target_usd_per_unit": 5}
    assert sp.overrides(off) == {"max_adds": 0, "target_usd_per_unit": 5.0}
    assert sp.config(off).ladder_multipliers == BacktestConfig().ladder_multipliers


def test_conditions_that_contradict_each_other_are_reported():
    sp = O.Space({"parameters": {"max_adds": [1, 2]}, "conditions": [
        {"when": "max_adds == 1", "fix": {"max_adds": 2}}, {"when": "max_adds == 2", "fix": {"max_adds": 1}}]})
    with pytest.raises(O.SpaceError, match="contradict"):
        sp.canonical((0,))


@pytest.mark.parametrize("symbol", ["XAUUSDm", "BTCUSDm"])
def test_the_shipped_spaces_load_and_every_setting_is_a_valid_configuration(symbol, live_root):
    from backtesting import experiments as E
    from backtesting.config import TF_SECONDS

    live = E.live_config(symbol, live_root, fixed_units=1, initial_balance=E.SWEEP_BALANCE)
    names = sorted(p.stem for p in O.SPACES_DIR.glob("*.json"))
    assert {"v2", "ladder"} <= set(names)
    for name in names:
        sp = O.Space.load(name, live=live)
        assert sp.name == name and sp.description and "live" in sp.references and sp.references["V2"]["trend_tf"] == "H1"
        sample = sp.random(60, seed=3)
        assert len(sample) == len(set(sample)) == 60
        for c in sample:
            cfg = sp.config(c)
            assert cfg.fixed_units == 1 and cfg.initial_balance == E.SWEEP_BALANCE and cfg.symbol == symbol
            assert set(cfg.timeframes()) <= set(TF_SECONDS)
            assert all(sp.canonical([i if i is not None else 0 for i in n]) is not None for n in sp.neighbours(c))
    # the V2 reference is the design of that name, and a point of the v2 space
    v2 = O.Space.load("v2", live=live)
    assert v2.references["V2"] == {k: (float(v) if isinstance(v, int) and not isinstance(v, bool) and k != "max_adds" else v)
                                   for k, v in V2.items()}
    assert O.config_key(live.replace(**v2.references["V2"])) in {v2.key(c) for c in v2.grid()}
    # the ladder space: a bounded ladder (never more than four adds, always a stop), no ladder included
    lad = O.Space.load("ladder", live=live)
    assert {"max_adds", "ladder_multipliers", "ladder_min_gap", "ladder_min_interval_s", "rsi_oversold", "rsi_overbought",
            "stop_loss_usd_per_unit", "target_usd_per_unit", "target_per_lot", "trend_tf", "loss_cooldown_s"} \
        <= {p.name for p in lad.params}
    by = {p.name: p for p in lad.params}
    assert by["max_adds"].values == [0, 1, 2, 3, 4] and None not in by["stop_loss_usd_per_unit"].values
    assert by["ladder_multipliers"].labels == ["flat", "linear", "fibonacci"]
    assert by["ladder_multipliers"].values[2] == FIBO[:5] and by["ladder_min_gap"].price
    for c in lad.random(300, seed=1):
        v = lad.values(c)
        if v["max_adds"] == 0:
            assert set(v) == {"max_adds", "stop_loss_usd_per_unit", "target_usd_per_unit", "trend_tf", "loss_cooldown_s",
                              "force_close_enabled"}
        else:
            assert v["rsi_oversold"] + v["rsi_overbought"] == 100
            assert v["ladder_min_gap"] * v["max_adds"] < v["stop_loss_usd_per_unit"]      # the last add can be reached
            assert not (v["max_adds"] <= 2 and v["ladder_multipliers"] == "fibonacci")
            assert lad.config(c).ladder_min_gap == v["ladder_min_gap"] * lad.px


def test_a_space_is_found_by_file_or_by_name_and_says_what_exists(tmp_path):
    p = tmp_path / "mine.json"
    p.write_text(json.dumps(TINY), encoding="utf-8")
    assert O.Space.load(p).name == "tiny" and O.Space.load("v2").name == "v2"
    with pytest.raises(O.SpaceError, match="not one of the shipped spaces .*ladder.*v2"):
        O.Space.load("nothing_like_it")
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(O.SpaceError, match="not valid JSON"):
        O.Space.load(p)


def test_any_configuration_field_can_be_a_parameter():
    """Nothing knows the fields by name: whatever BacktestConfig holds, today or after a lever is added, can be varied."""
    import dataclasses

    default = BacktestConfig()
    names = [f.name for f in dataclasses.fields(BacktestConfig) if f.name not in O.RESERVED_FIELDS]
    assert len(names) > 60 and {"trend_tf", "loss_cooldown_s", "entry_max_spread", "open_weights"} <= set(names)
    for name in names:
        value = getattr(default, name)
        sp = O.Space({"parameters": {name: [value]}, "constraints": [f"{name} == {name}"]})
        (c,) = sp.grid()
        assert sp.config(c) == default and sp.key(c) == O.config_key(default), name
        assert list(sp.overrides(c)) == [name]
    for name in O.RESERVED_FIELDS:
        with pytest.raises(O.SpaceError, match="set by the optimiser"):
            O.Space({"parameters": {name: [getattr(default, name)]}})


def test_the_guide_agrees_with_the_code():
    """OPTIMISER.md: its example is a valid space, it names every option of the command and the sizes it quotes are right."""
    from pathlib import Path

    guide = (Path(O.__file__).parent / "OPTIMISER.md").read_text(encoding="utf-8")
    example = O.Space(json.loads(guide.split("```json")[1].split("```")[0]))
    assert example.name == "example" and [p.name for p in example.params] == [
        "max_adds", "ladder_multipliers", "ladder_min_gap", "loss_cooldown_s", "stop_loss_usd_per_unit", "trend_tf"]
    assert len(example.random(40, seed=1)) == 40 and "V2" in example.references
    command = cli.build_parser()._subparsers._group_actions[0].choices["optimise"]
    options = [o for action in command._actions for o in action.option_strings if o.startswith("--") and o != "--help"]
    assert len(options) == len(O.Options.__dataclass_fields__) and all(f"`{o}`" in guide for o in options), \
        [o for o in options if f"`{o}`" not in guide]
    assert len(O.Space.load("v2").grid()) == 640 and "(640 settings)" in guide
    assert len(O.Space.load("entries").grid()) == 384 and "(384 settings)" in guide
    for name in O.OBJECTIVES:
        assert f"| `{name}`" in guide


def test_the_fingerprint_follows_what_a_setting_means_and_nothing_else():
    base = O.Space(TINY).fingerprint()
    assert O.Space({**TINY, "description": "other words", "references": {}, "name": "x"}).fingerprint() == base
    assert O.Space(TINY, live=BacktestConfig(symbol="BTCUSDm")).fingerprint() == base
    for change in ({"base": {"rsi_length": 10}}, {"conditions": []}, {"constraints": ["max_adds < 2"]},
                   {"parameters": {**TINY["parameters"], "target_usd_per_unit": [0.5, 1, 2, 3]}}):
        assert O.Space({**TINY, **change}).fingerprint() != base


# ───────────────────────────── samplers ─────────────────────────────

BIG = {"parameters": {"rsi_length": {"range": [8, 19], "step": 1}, "peak_lookback": [10, 15, 20, 25, 30, 40],
                      "target_usd_per_unit": [1, 2, 3, 5, 8], "trend_tf": [None, "H1", "H4"]}}        # 12 x 6 x 5 x 3


def test_the_grid_is_every_distinct_setting_and_is_refused_above_its_limit():
    sp = O.Space(TINY)
    grid = sp.grid()
    assert [sp.values(c) for c in grid][:4] == [
        {"max_adds": 0, "target_usd_per_unit": 0.5}, {"max_adds": 0, "target_usd_per_unit": 1},
        {"max_adds": 0, "target_usd_per_unit": 2}, {"max_adds": 1, "ladder_multipliers": "flat", "target_usd_per_unit": 0.5}]
    assert len(grid) == 3 + 2 * 2 * 3 == len(sp.grid(limit=15))
    with pytest.raises(O.SpaceError, match="15 settings after conditions and constraints, above the limit of 14"):
        sp.grid(limit=14)
    huge = O.Space({"parameters": {"rsi_length": {"range": [2, 101], "step": 1}, "peak_lookback": {"range": [2, 101], "step": 1},
                                   "macd_slow": {"range": [2, 101], "step": 1}}})
    with pytest.raises(O.SpaceError, match="1,000,000 raw combinations"):
        huge.grid()
    assert len(huge.random(25, seed=1)) == 25                 # a space too large to enumerate can still be sampled


def test_the_random_sample_is_reproducible_nested_and_covers_every_value_evenly():
    sp = O.Space(BIG)
    a = sp.random(120, seed=7)
    assert a == sp.random(120, seed=7) and a != sp.random(120, seed=8)
    assert len(a) == len(set(a)) == 120
    assert sp.random(60, seed=7) == a[:60] and sp.random(180, seed=7)[:120] == a      # a larger sample continues a smaller one
    for size in (120, 77, 13):                                # at any length, not only at whole rounds
        for j, p in enumerate(sp.params):
            seen = Counter(c[j] for c in a[:size])
            assert len(seen) == min(len(p.values), size) or size < len(p.values)
            assert max(seen.values()) - min(seen[i] for i in range(len(p.values))) <= 1, (size, p.name, seen)
    assert Counter(c[3] for c in a) == {0: 40, 1: 40, 2: 40} and set(Counter(c[0] for c in a).values()) == {10}
    # a space with no more settings than asked for is returned whole
    tiny = O.Space(TINY)
    assert tiny.random(500, seed=1) == tiny.grid() and tiny.random(0) == []
    # with conditions and constraints: only distinct, admissible settings, still reproducible
    part = tiny.random(9, seed=2)
    assert len(part) == len(set(part)) == 9 and set(part) <= set(tiny.grid()) and part == tiny.random(9, seed=2)
    # ... and still even where the conditions leave a parameter in play: the ladder shape among the settings with a ladder
    lad = O.Space({"parameters": {"max_adds": [0, 1, 2, 3, 4], "ladder_min_gap": [0, 2, 5, 10], "rsi_length": {"range": [5, 30], "step": 1},
                                  "stop_loss_usd_per_unit": [10, 20, 40]},
                   "conditions": [{"when": "max_adds == 0", "ignore": ["ladder_min_gap"]}],
                   "constraints": ["ladder_min_gap * max_adds <= stop_loss_usd_per_unit"]})
    got = lad.random(100, seed=4)
    assert all(lad.values(c).get("ladder_min_gap", 0) * lad.values(c)["max_adds"] <= lad.values(c)["stop_loss_usd_per_unit"] for c in got)
    adds, gaps = Counter(c[0] for c in got), Counter(c[1] for c in got if c[1] is not None)
    assert set(adds.values()) == {20} and sum(gaps.values()) == 80 and max(gaps.values()) - min(gaps.values()) <= 1


def test_neighbours_move_one_parameter_by_one_step():
    sp = O.Space({"parameters": {
        "max_adds": [0, 1, 2, 3],
        "ladder_multipliers": {"values": {"flat": [1, 1, 1, 1], "linear": [1, 2, 3, 4], "double": [1, 2, 4, 8]}},
        "ladder_min_gap": [0, 5, 10],
        "trend_tf": [None, "H1", "H4"],
    }, "conditions": [{"when": "max_adds == 0", "ignore": ["ladder_multipliers", "ladder_min_gap"]}],
        "constraints": ["ladder_min_gap * max_adds <= 20"]})
    c = sp.canonical((2, 1, 1, 0))
    near = sp.neighbours(c)
    assert c not in near and len(near) == len(set(near))
    diffs = [[j for j in range(4) if n[j] != c[j]] for n in near]
    assert all(len(d) >= 1 for d in diffs)
    described = {tuple(sorted(sp.values(n).items(), key=lambda kv: kv[0])) for n in near}
    assert len(described) == len(near)
    want = [
        (1, 1, 1, 0), (3, 1, 1, 0),                 # max_adds is ordered: one step down, one step up
        (2, 0, 1, 0), (2, 2, 1, 0),                 # the ladder shape has no order: every other shape
        (2, 1, 0, 0), (2, 1, 2, 0),                 # the gap: next smaller, next larger (10 x 2 = 20 is still allowed)
        (2, 1, 1, 1), (2, 1, 1, 2),                 # the trend timeframe: every other one
    ]
    assert near == want
    # a step that breaks the constraint is not a neighbour; the edge of a range has one neighbour on that side
    assert (3, 1, 2, 0) not in sp.neighbours((3, 1, 1, 0)) and (3, 1, 0, 0) in sp.neighbours((3, 1, 1, 0))
    # a step that switches parameters on starts them from the base value when it is listed, else from the first value
    off = sp.canonical((0, 2, 2, 1))
    assert off == (0, None, None, 1)
    assert sp.neighbours(off) == [(1, 0, 0, 1), (0, None, None, 0), (0, None, None, 2)]


# ───────────────────────────── blocks, months, hold-out ─────────────────────────────

def test_blocks_and_months_are_counted_from_the_start_of_the_period():
    per = O.make_period(*O.DEV)
    assert [b.label for b in per.blocks] == [
        "2025-07-01 → 2025-10-01", "2025-10-01 → 2026-01-01", "2026-01-01 → 2026-04-01", "2026-04-01 → 2026-07-01",
        "2026-07-01 → 2026-10-01", "2026-10-01 → 2026-11-13"]
    assert [m.label for m in per.months] == [f"{y}-{m:02d}" for y, m in
                                             [(2025, k) for k in range(7, 13)] + [(2026, k) for k in range(1, 12)]]
    assert [len(b.months) for b in per.blocks] == [3, 3, 3, 3, 3, 2] and per.unit == "month"
    assert all(m.full for m in per.months[:-1])
    last = per.months[-1]
    assert not last.full and last.coverage == pytest.approx(12 / 30) and last.block == 5       # twelve days of November
    # every block starts where the one before ended, and a month belongs to exactly one block
    assert all(a.end == b.start for a, b in zip(per.blocks, per.blocks[1:]))
    assert sorted(i for b in per.blocks for i in b.months) == list(range(len(per.months)))
    # the confirmation period before it shares the block boundaries, so its blocks can simply be added
    both = O.make_period(O.CONFIRM[0], O.DEV[1])
    assert O.CONFIRM[1] == O.DEV[0] and [b.id for b in both.blocks[6:]] == [b.id for b in per.blocks]
    # a period that starts mid-month is cut from that day, not from the first of the month
    mid = O.make_period("2025-08-13", "2026-02-13")
    assert [b.label for b in mid.blocks] == ["2025-08-13 → 2025-11-13", "2025-11-13 → 2026-02-13"]
    assert [m.label for m in mid.months][:3] == ["2025-08-13", "2025-09-13", "2025-10-13"] and all(m.full for m in mid.months)
    # month ends do not drift: 31 January + 1 month is the end of February, + 2 months the 31st of March
    ends = O.make_period("2026-01-31", "2026-05-31", "1mo", "1mo")
    assert [str(b.start.date()) for b in ends.blocks] == ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]
    # other lengths, down to minutes
    short = O.make_period(*HOUR, "20min", "10min")
    assert len(short.blocks) == 3 and len(short.months) == 6 and short.unit == "slice"
    assert short.edges_ms(short.blocks[1]) == [1794205200000, 1794205800000, 1794206400000]
    assert O.parse_span("2w") == ("minute", 20160) and O.parse_span("3 months") == ("month", 3)
    for bad in ("", "3", "month", "0mo", "-1d", "3y"):
        with pytest.raises(ValueError):
            O.parse_span(bad)


def test_a_hold_out_begins_and_ends_where_a_block_does():
    per = O.make_period(O.CONFIRM[0], O.DEV[1])
    assert O.holdout_mask(per).tolist() == [False] * 12
    assert O.holdout_mask(per, None, O.CONFIRM[1]).tolist() == [True] * 6 + [False] * 6
    assert O.holdout_mask(per, "2026-07-01", None).tolist() == [False] * 10 + [True] * 2
    assert O.holdout_mask(per, "2025-01-01", "2025-07-01").tolist() == [False] * 4 + [True] * 2 + [False] * 6
    with pytest.raises(ValueError, match="--holdout-to 2025-06-01 is not where a block starts or ends"):
        O.holdout_mask(per, None, "2025-06-01")
    with pytest.raises(ValueError, match="covers the whole period"):
        O.holdout_mask(per, O.CONFIRM[0], O.DEV[1])
    with pytest.raises(ValueError, match="contains no block"):
        O.holdout_mask(per, "2025-07-01", "2025-07-01")


def test_history_before_2024_is_refused_unless_unlocked(tmp_path, fixture_store, monkeypatch):
    """The default period is the development period; the year kept for the final test needs an explicit switch."""
    monkeypatch.setenv("ALCADEIAS_STORE_DIR", str(fixture_store))
    args = cli.build_parser().parse_args(["optimise", "--space", "v2"])
    assert (args.start, args.end) == O.DEV and args.holdout_from is None and args.objective == "lcb" and args.jobs == 2
    p = tmp_path / "tiny.json"
    p.write_text(json.dumps(TINY), encoding="utf-8")
    o = O.Options(space=str(p), symbol=SYM, start="2023-06-01", end="2023-09-01", out=str(tmp_path / "out"), jobs=1)
    with pytest.raises(ValueError, match="reserved for one final test"):
        O.optimise(o, log=quiet)
    o.allow_reserved = True
    with pytest.raises(ValueError, match="the tick store has no BTCUSDm data for 2023-06, 2023-07, 2023-08"):
        O.optimise(o, log=quiet)
    # a period too short to hold one full month (here: one full ten-minute slice) has nothing to compute statistics on
    with pytest.raises(ValueError, match="hold no full slice"):
        O.optimise(O.Options(space=str(p), symbol=SYM, start=HOUR[0], end="2026-11-09 06:04", block="20min", slice="10min",
                             out=str(tmp_path / "out"), jobs=1), log=quiet)
    assert not (tmp_path / "out").exists()                    # nothing was written for a run that never started


# ───────────────────────────── on the bundled ticks ─────────────────────────────

@pytest.fixture(scope="module")
def tiny_run(tmp_path_factory, fixture_store, live_root):
    """One run of the tiny space on the bundled BTC hour: three blocks of 20 minutes, the first one held out."""
    mp = pytest.MonkeyPatch()
    mp.setenv("ALCADEIAS_STORE_DIR", str(fixture_store))
    d = tmp_path_factory.mktemp("optimise")
    space = d / "tiny.json"
    space.write_text(json.dumps(TINY), encoding="utf-8")

    def options(**kw) -> O.Options:
        base = dict(space=str(space), symbol=SYM, start=HOUR[0], end=HOUR[1], block="20min", slice="10min",
                    holdout_to="2026-11-09 06:20", jobs=1, bootstrap=200, out=str(d / "out"), live_root=str(live_root))
        base.update(kw)
        return O.Options(**base)

    log: list = []
    try:
        res = O.optimise(options(), log=log.append)
        yield {"dir": d, "out": d / "out", "options": options, "res": res, "log": log, "mp": mp}
    finally:
        mp.undo()


def stored(out):
    rows = [json.loads(line) for line in (out / "evaluations.jsonl").read_text(encoding="utf-8").splitlines()]
    return rows[0], [r for r in rows if r["kind"] == "setting"], [r for r in rows if r["kind"] == "eval"]


def test_every_setting_is_run_once_per_block_at_one_fixed_unit(tiny_run):
    res, out = tiny_run["res"], tiny_run["out"]
    head, settings, evals = stored(out)
    # 15 distinct settings; the references are the live settings and "no ladder", which is one of the 15
    assert len(settings) == 15 and res["settings"] == 15
    assert res["evaluated"] == len(evals) == 16 * 3
    assert Counter(e["block"] for e in evals) == {b: 16 for b in
                                                  ("2026-11-09T06:00/2026-11-09T06:20/minute10",
                                                   "2026-11-09T06:20/2026-11-09T06:40/minute10",
                                                   "2026-11-09T06:40/2026-11-09T07:00/minute10")}
    assert len({(e["key"], e["block"]) for e in evals}) == len(evals)
    assert set(head["stamp"]) == {"format", "space", "symbol", "engine", "live", "account"}
    for s in settings:
        assert s["origin"] == "random" and s["round"] == 0 and s["key"].startswith("s") and len(s["key"]) == 12
    for name in ("trials.csv", "monthly.csv", "report.md", "best.json", "evaluations.jsonl"):
        assert (out / name).stat().st_size > 0, name


def test_the_months_of_a_block_add_up_to_its_net_and_agree_with_an_independent_run(tiny_run, fixture_store, live_root):
    from backtesting import experiments as E
    from backtesting.analysis.metrics import score_row
    from backtesting.engine import fast

    _, settings, evals = stored(tiny_run["out"])
    by_key = {s["key"]: s for s in settings}
    traded = 0
    for e in evals:
        assert len(e["pnl"]) == len(e["n"]) == 2
        assert sum(e["pnl"]) == pytest.approx(e["net"], abs=0.006)                 # the months of a block are the block
        traded += e["baskets"]
    assert traded > 20                  # (the netting variant holds its baskets longer and closes fewer in the hour)
    # three (setting, block) cells against a plain run of the engine with that configuration on that block
    per = O.make_period(*HOUR, "20min", "10min")
    picks = [e for e in evals if e["key"] in by_key and e["baskets"] >= 2][:3]
    assert len(picks) == 3
    for e in picks:
        block = next(b for b in per.blocks if b.id == e["block"])
        cfg = E.live_config(SYM, live_root, fixed_units=1, initial_balance=E.SWEEP_BALANCE,
                            start=block.window[0], end=block.window[1], **by_key[e["key"]]["overrides"])
        run = fast.run(cfg, fast.prepare(SYM, cfg.start, cfg.end, cfg.timeframes(), store_dir=fixture_store), light=True)
        row = score_row(run)
        assert e["net"] == row["net_profit"] and e["baskets"] == row["baskets"] and e["worst_basket"] == row["largest_loss"]
        assert (e["wiped"], e["dip"]) == (row["acct_wiped"], row["acct_dip"])      # the 2,000 USD account replay
        b = run.baskets
        first = b[b["close_time"] < pd.Timestamp(block.start + pd.Timedelta(minutes=10), tz="UTC")]
        assert e["n"] == [len(first), len(b) - len(first)]
        assert e["pnl"][0] == pytest.approx(first["pnl"].sum(), abs=1e-6)
        assert e["pnl"][1] == pytest.approx(b["pnl"].sum() - first["pnl"].sum() + run.scalars["open_profit_at_end"], abs=1e-6)


def test_month_pnl_books_a_basket_where_it_closed_and_the_open_one_last():
    t = lambda s: pd.Timestamp(s, tz="UTC")
    baskets = pd.DataFrame({"close_time": pd.to_datetime([t("2026-01-31 23:59:59.999"), t("2026-02-01 00:00:00"),
                                                          t("2026-02-10"), t("2026-03-31 23:00")]).as_unit("ns"),
                            "pnl": [1.0, -2.0, 4.0, 8.0]})
    edges = [pd.Timestamp(d, tz="UTC").value // 10**6 for d in ("2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01")]
    assert O.month_pnl(baskets, edges, open_profit=-0.5) == ([1.0, 2.0, 7.5], [1, 2, 1])
    assert O.month_pnl(baskets.iloc[:0], edges, open_profit=3.0) == ([0.0, 0.0, 3.0], [0, 0, 0])


def test_the_output_files_describe_the_run(tiny_run):
    out, res = tiny_run["out"], tiny_run["res"]
    trials = pd.read_csv(out / "trials.csv")
    monthly = pd.read_csv(out / "monthly.csv")
    best = json.loads((out / "best.json").read_text(encoding="utf-8"))
    report = (out / "report.md").read_text(encoding="utf-8")
    cand = trials[trials["origin"] != "reference"]
    assert len(cand) == 15 and list(trials["name"].dropna()) == ["live", "no ladder"]
    assert list(cand["rank"]) == list(range(1, 16)) and cand["objective"].is_monotonic_decreasing
    assert cand["objective"].tolist() == pytest.approx(cand["lcb"].tolist())
    assert (cand["mean"] - cand["se"]).tolist() == pytest.approx(cand["lcb"].tolist(), abs=2e-4)
    assert set(cand["months"]) == {4} and set(cand["holdout_months"]) == {2}
    # a parameter that a condition switched off is empty, in the table and in the overrides
    no_ladder = cand[cand["max_adds"] == 0]
    assert len(no_ladder) == 3 and no_ladder["ladder_multipliers"].isna().all()
    assert all("ladder_multipliers" not in json.loads(x) for x in no_ladder["overrides"])
    # monthly.csv: the same settings in the same order, hold-out months marked, summing to the totals of trials.csv
    assert list(monthly["key"]) == list(trials["key"])
    assert list(monthly.columns) == ["rank", "name", "key", "2026-11-09 06:00 hold-out", "2026-11-09 06:10 hold-out",
                                     "2026-11-09 06:20", "2026-11-09 06:30", "2026-11-09 06:40", "2026-11-09 06:50"]
    assert monthly.iloc[:, 5:].sum(axis=1).tolist() == pytest.approx(trials["total"].tolist(), abs=1e-3)
    assert monthly.iloc[:, 3:5].sum(axis=1).tolist() == pytest.approx(trials["holdout_total"].tolist(), abs=1e-3)
    # best.json names the top row and how to run it
    assert best["best"]["key"] == trials["key"][0] == res["best"] and best["settings_run"] == 15
    assert best["period"]["holdout_months"] == ["2026-11-09 06:00", "2026-11-09 06:10"]
    assert best["best"]["selection"]["lcb"] == pytest.approx(trials["lcb"][0], abs=1e-4)
    assert best["verdict"] == res["verdict"] and [r["name"] for r in best["references"]] == ["live", "no ladder"]
    for needle in ("# Optimiser report: `tiny` on BTCUSDm", "## What to believe", "## The top 10 settings",
                   "### Selection and hold-out, side by side", "## Is the best result more than luck?",
                   "## Does choosing on one half work on the other?", "## Walk-forward: choosing with past data only",
                   "### Average by parameter value", "## Reproduce", "live (reference)", "no ladder (reference)",
                   best["best"]["run"], best["best"]["run_last_block"]):
        assert needle in report, needle
    assert "nan" not in report.lower() and "None" not in report


def test_the_run_lines_reproduce_the_setting(tiny_run, fixture_store, live_root):
    """best.json's command for the last block gives exactly the stored figure through the ordinary `run` command."""
    from backtesting.analysis.metrics import score_row
    from backtesting.engine import fast

    best = json.loads((tiny_run["out"] / "best.json").read_text(encoding="utf-8"))["best"]
    for line in (best["run"], best["run_last_block"]):
        words = shlex.split(line)
        assert words[:4] == ["python", "-m", "backtesting", "run"]
        args = cli.build_parser().parse_args(words[3:])
        sets = cli._parse_sets(args.set)
        assert {k: v for k, v in sets.items() if k != "fixed_units"} == best["overrides"]
    cfg = cli._config(args)                                   # the last-block line
    assert cfg.fixed_units == 1 and cfg.initial_balance == 1_000_000 and (cfg.start, cfg.end) == ("2026-11-09 06:40:00", "2026-11-09 07:00:00")
    run = fast.run(cfg, fast.prepare(cfg.symbol, cfg.start, cfg.end, cfg.timeframes(), store_dir=fixture_store), light=True)
    assert score_row(run)["net_profit"] == best["last_block_net"]


def test_a_second_run_computes_nothing_and_changes_nothing(tiny_run):
    out = tiny_run["out"]
    before = {p.name: p.read_bytes() for p in out.iterdir() if p.suffix in (".csv", ".jsonl")}
    log: list = []
    again = O.optimise(tiny_run["options"](), log=log.append)
    assert again["evaluated"] == 0 and again["best"] == tiny_run["res"]["best"]
    assert {p.name: p.read_bytes() for p in out.iterdir() if p.suffix in (".csv", ".jsonl")} == before
    assert not any("runs in" in line for line in log)
    # neither does a report with another objective, or with nothing held out; both only read what is stored
    for kw in ({"objective": "mean"}, {"holdout_to": None}, {"objective": "worst_block", "max_dip": 0.0}):
        res = O.optimise(tiny_run["options"](report_only=True, out=str(out), **kw), log=quiet)
        assert res["evaluated"] == 0 and res["settings"] == 15
    assert (out / "evaluations.jsonl").read_bytes() == before["evaluations.jsonl"]
    O.optimise(tiny_run["options"](), log=quiet)              # leave the files as the other tests expect them


def test_an_interrupted_run_continues_where_it_stopped(tiny_run, tmp_path):
    """Results are on disk as they arrive: cut the file anywhere, even inside a line, and only the missing runs are made."""
    whole = (tiny_run["out"] / "evaluations.jsonl").read_text(encoding="utf-8").splitlines(keepends=True)
    out = tmp_path / "cut"
    out.mkdir()
    kept = whole[: len(whole) - 20]
    (out / "evaluations.jsonl").write_text("".join(kept) + whole[len(kept)][:37], encoding="utf-8")       # 20 runs lost, one half-written
    res = O.optimise(tiny_run["options"](out=str(out)), log=quiet)
    assert res["evaluated"] == 20
    lines = (out / "evaluations.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(whole) and all(json.loads(x) for x in lines)             # the cut line is gone, not glued to the next
    a, b = pd.read_csv(out / "monthly.csv"), pd.read_csv(tiny_run["out"] / "monthly.csv")
    pd.testing.assert_frame_equal(a, b)


def test_only_the_missing_blocks_are_run_when_the_period_grows(tiny_run, tmp_path):
    """Choose on the later blocks first, add an earlier one as hold-out afterwards: the finished blocks are kept."""
    out = tmp_path / "grow"
    first = O.optimise(tiny_run["options"](out=str(out), start="2026-11-09 06:20", holdout_to=None), log=quiet)
    assert first["evaluated"] == 16 * 2
    chosen = pd.read_csv(out / "trials.csv")
    assert "holdout_mean" not in chosen.columns
    grown = O.optimise(tiny_run["options"](out=str(out)), log=quiet)
    assert grown["evaluated"] == 16 * 1 and grown["best"] == first["best"]
    confirmed = pd.read_csv(out / "trials.csv")
    assert confirmed["key"].tolist() == chosen["key"].tolist()                        # the hold-out changed no rank
    assert confirmed["lcb"].tolist() == chosen["lcb"].tolist() and confirmed["holdout_mean"].notna().all()
    # ... and it is the run of the module fixture, block for block
    pd.testing.assert_frame_equal(pd.read_csv(out / "monthly.csv"), pd.read_csv(tiny_run["out"] / "monthly.csv"))


def test_results_of_another_build_space_or_data_are_never_reused(tiny_run, tmp_path, monkeypatch):
    from backtesting import experiments as E

    out = tmp_path / "stamps"
    opt = tiny_run["options"]
    assert O.optimise(opt(out=str(out)), log=quiet)["evaluated"] == 48
    assert O.optimise(opt(out=str(out)), log=quiet)["evaluated"] == 0
    # another build of the engine: the file is set aside, everything is run again
    log: list = []
    with monkeypatch.context() as m:
        m.setattr(E, "engine_fingerprint", lambda: "f" * 12)
        res = O.optimise(opt(out=str(out)), log=log.append)
        assert res["evaluated"] == 48 and any("written for another engine" in x for x in log)
        assert len(list(out.glob("evaluations.stale-*.jsonl"))) == 1
        assert json.loads((out / "evaluations.jsonl").read_text(encoding="utf-8").splitlines()[0])["stamp"]["engine"] == "f" * 12
        assert res["analysis"].earlier == 0                    # the same settings again: nothing else was tried
        with pytest.raises(ValueError, match="written for another account"):
            O.optimise(opt(out=str(out), account=5000.0, report_only=True), log=quiet)
    # back on the real build: set aside again
    assert O.optimise(opt(out=str(out)), log=quiet)["evaluated"] == 48
    assert len(list(out.glob("evaluations.stale-*.jsonl"))) == 2
    # another space (one more value): set aside, and the settings of the earlier space still count as tried
    wider = dict(TINY, parameters=dict(TINY["parameters"], target_usd_per_unit=[0.5, 1, 2, 3], max_adds=[1, 2]))
    (tmp_path / "wider.json").write_text(json.dumps(wider), encoding="utf-8")
    res = O.optimise(opt(out=str(out), space=str(tmp_path / "wider.json")), log=quiet)
    assert res["settings"] == 16 and res["evaluated"] == 18 * 3          # 16 settings and the two references
    a = res["analysis"]
    assert a.earlier == 3 and a.haircut["extra"] == 3                     # the three no-ladder settings of the first space
    assert "3 others were tried in earlier runs kept in this directory" in (out / "report.md").read_text(encoding="utf-8")
    # other tick data under a block (here: pretend the month was rebuilt): those results are run again, nothing is set aside
    real = O.data_stamps

    def rebuilt(symbol, period, reach=None):
        return ["dchanged00" if b.index == 1 else s for b, s in zip(period.blocks, real(symbol, period, reach))]

    monkeypatch.setattr(O, "data_stamps", rebuilt)
    with pytest.raises(ValueError, match="tick history under or before 1 of its blocks has changed since their results"):
        O.optimise(opt(out=str(out), space=str(tmp_path / "wider.json"), report_only=True), log=quiet)
    log = []
    assert O.optimise(opt(out=str(out), space=str(tmp_path / "wider.json")), log=log.append)["evaluated"] == 18
    assert any("has changed since their results were stored (2026-11-09 06:20 → 2026-11-09 06:40)" in x for x in log)
    assert len(list(out.glob("evaluations.stale-*.jsonl"))) == 3
    log.clear()
    assert O.optimise(opt(out=str(out), space=str(tmp_path / "wider.json")), log=log.append)["evaluated"] == 0
    assert not any("has changed since" in x for x in log)                 # the new results are the ones in force


def test_worker_processes_give_the_results_of_one_process(tiny_run, tmp_path):
    out = tmp_path / "two"
    res = O.optimise(tiny_run["options"](out=str(out), jobs=2), log=quiet)
    assert res["evaluated"] == 48
    pd.testing.assert_frame_equal(pd.read_csv(out / "trials.csv"), pd.read_csv(tiny_run["out"] / "trials.csv"))


def test_a_process_never_holds_two_blocks_and_tasks_come_block_by_block(tiny_run, tmp_path, monkeypatch):
    from backtesting.engine import fast

    seen, alive = [], []
    real = fast.prepare

    def watching(symbol, start, end, tfs, **kw):
        alive.append(O._W.get("prep"))                        # what the process still holds when it loads a block
        seen.append((str(start), tuple(tfs)))
        return real(symbol, start, end, tfs, **kw)

    monkeypatch.setattr(fast, "prepare", watching)
    O.optimise(tiny_run["options"](out=str(tmp_path / "watch")), log=quiet)
    # one load per block for the selection blocks, then one for the held-out block; never two at once
    assert [s for s, _ in seen] == ["2026-11-09 06:20:00", "2026-11-09 06:40:00", "2026-11-09 06:00:00"]
    assert alive == [None, None, None]
    assert all(set(tfs) == {"M1", "M5", "M15", "H1", "H4"} for _, tfs in seen)       # every timeframe any setting reads (the live ladder: five)
    assert O._W == {}                                         # and the last block is let go when the run ends


def test_refinement_adds_the_neighbours_of_the_best_and_is_repeatable(tiny_run, tmp_path):
    """A sample of 5 of the 15 settings, then two rounds around the best 2: the same settings whenever it is run."""
    out = tmp_path / "refine"
    opt = lambda **kw: tiny_run["options"](**{"out": str(out), "n": 5, "refine_top": 2, "refine_rounds": 2, "holdout_to": None, **kw})
    res = O.optimise(opt(), log=quiet)
    _, settings, _ = stored(out)
    origin = Counter((s["origin"], s["round"]) for s in settings)
    assert origin[("random", 0)] == 5 and origin[("refine", 1)] >= 1 and set(origin) <= {("random", 0), ("refine", 1), ("refine", 2)}
    a = res["analysis"]
    sp = a.space                                              # the space as the run bound it to the live settings
    first = {s["key"]: tuple(s["canon"]) for s in settings if s["round"] == 0}
    # round 1 is exactly the untried neighbours of the two best of the sample
    sample_rows = [i for i in a.order if a.settings[i]["round"] == 0][:2]
    want = {sp.key(c) for i in sample_rows for c in sp.neighbours(tuple(a.settings[i]["canon"]))} - set(first)
    assert {s["key"] for s in settings if s["round"] == 1} == want
    assert res["evaluated"] == (len(settings) + 1) * 3 and res["settings"] == len(settings)
    again = O.optimise(opt(), log=quiet)
    assert again["evaluated"] == 0 and stored(out)[1] == settings
    # a third round goes on from there; "stored" adds no sample and no settings when the rounds are off
    more = O.optimise(opt(refine_rounds=3), log=quiet)
    assert more["settings"] >= len(settings)
    kept = O.optimise(opt(sampler="stored", refine_rounds=0), log=quiet)
    assert kept["evaluated"] == 0 and kept["settings"] == more["settings"]
    with pytest.raises(ValueError, match="no settings to run"):
        O.optimise(tiny_run["options"](out=str(tmp_path / "empty"), sampler="stored"), log=quiet)


def test_hold_out_for_the_short_list_only(tiny_run, tmp_path):
    out = tmp_path / "toponly"
    res = O.optimise(tiny_run["options"](out=str(out), holdout_top_only=True, top=3), log=quiet)
    assert res["evaluated"] == 16 * 2 + (3 + 2) * 1           # held-out block: the best three and the two references
    trials = pd.read_csv(out / "trials.csv")
    cand = trials[trials["origin"] != "reference"]
    assert cand["holdout_mean"].iloc[:3].notna().all() and trials[trials["origin"] == "reference"]["holdout_mean"].notna().all()
    # one more candidate has held-out figures: the one that is the "no ladder" reference
    rest = cand[cand["holdout_mean"].notna()].iloc[3:]
    assert len(rest) == 1 and rest["key"].iloc[0] == trials[trials["name"] == "no ladder"]["key"].iloc[0]
    full = pd.read_csv(tiny_run["out"] / "trials.csv")
    assert cand["key"].tolist() == full["key"].tolist()[:15] and cand["holdout_mean"].iloc[:3].tolist() == full["holdout_mean"].iloc[:3].tolist()
    assert res["analysis"].carry is None                      # no comparison of all settings across the two periods


# ───────────────────────────── objectives, on a matrix worked out by hand ─────────────────────────────

def quarters(n_blocks: int, per: int = 3):
    return [np.arange(i * per, (i + 1) * per) for i in range(n_blocks)]


def test_objectives_on_a_hand_made_matrix():
    X = np.array([[10.0, 10, 10, 10, 10, 10],          # steady
                  [0.0, 0, 0, 0, 0, 90],               # one lucky month, the higher mean
                  [-30.0, 20, 40, 10, 20, 30],         # a bad first quarter month
                  [0.0, 0, 0, 0, 0, 0]])               # never trades
    g = quarters(2)
    assert O.objective("mean", X, g).tolist() == [10, 15, 15, 0]
    assert O.objective("median", X, g).tolist() == [10, 0, 20, 0]
    assert O.objective("worst_block", X, g).tolist() == [30, 0, 30, 0]
    se = X.std(axis=1, ddof=1) / math.sqrt(6)
    assert O.objective("lcb", X, g).tolist() == pytest.approx((X.mean(axis=1) - se).tolist()) and se[1] == pytest.approx(15.0)
    assert O.objective("sharpe", X, g)[1:].tolist() == pytest.approx([15 / X[1].std(ddof=1), 15 / X[2].std(ddof=1), 0.0])
    # the default objective prefers the steady setting to the lucky one, the mean does not
    assert O.objective("lcb", X, g)[0] == 10 > O.objective("lcb", X, g)[2] > O.objective("lcb", X, g)[1] == 0
    order = O.ranking(O.objective("lcb", X, g), X.mean(axis=1), np.ones(4, bool))
    assert order.tolist() == [0, 2, 1, 3]                    # lucky and idle both have a lower bound of 0: the mean decides
    # restricted to some blocks, and with no month at all
    assert O.objective("mean", X, g[1:]).tolist() == [10, 30, 20, 0]
    assert O.objective("lcb", X, []).tolist() == [0, 0, 0, 0]
    with pytest.raises(ValueError, match="unknown objective"):
        O.objective("profit", X, g)


def test_wiped_or_deep_dipping_settings_are_not_eligible():
    wiped = np.array([[0, 0], [0, 1], [0, 0], [0, 0]], float)
    dip = np.array([[100, 300], [50, 2000], [100, 1200], [np.nan, 10]], float)
    assert O.eligible(wiped, dip).tolist() == [True, False, True, True]
    assert O.eligible(wiped, dip, max_dip=1000).tolist() == [True, False, False, True]
    assert O.eligible(wiped, dip, allow_wiped=True, max_dip=0).tolist() == [True] * 4
    assert O.eligible(wiped[:, :1], dip[:, :1], max_dip=80).tolist() == [False, True, False, True]     # only the blocks given
    obj = np.array([5.0, 9.0, 7.0, 7.0])
    assert O.ranking(obj, obj, O.eligible(wiped, dip, max_dip=1000)).tolist() == [3, 0, 1, 2]           # eligible first


# ───────────────────────────── overfitting diagnostics, on matrices whose truth is known ─────────────────────────────

def noise(seed: int, settings: int = 150, blocks: int = 8, sd: float = 50.0):
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, sd, (settings, blocks * 3)), quarters(blocks), np.zeros((settings, blocks)), np.zeros((settings, blocks))


def test_pure_noise_has_an_overfitting_probability_near_one_half_and_the_haircut_explains_the_best_row():
    pbo, p, best, null, oos = [], [], [], [], []
    for seed in range(6):
        X, g, w, d = noise(seed)
        c = O.cscv(X, g, w, d)
        assert c["splits"] == c["of"] == math.comb(8, 4) and c["skipped"] == 0
        h = O.haircut(X, g, np.ones(len(X), bool), n_boot=400, seed=seed)
        pbo.append(c["pbo"]), oos.append(c["oos_mean"]), p.append(h["p"]), best.append(h["mean"]), null.append(h["null_mean"])
        assert c["is_mean"] > 20 and h["mean"] > 15                          # the best of 150 always looks like an edge
        assert h["mean"] < h["null_mean_p95"] * 1.6
    assert 0.4 < np.mean(pbo) < 0.6, pbo                                     # where the best lands out of sample: anywhere
    assert abs(np.mean(oos)) < 6, oos                                        # ... and what it makes there: nothing
    assert np.mean(best) == pytest.approx(np.mean(null), rel=0.15)           # the haircut is the size of the best result
    assert min(p) > 0.03 and np.mean(p) > 0.25, p                            # which luck alone reaches all the time


def test_one_genuinely_better_setting_is_found_and_everything_says_so():
    for seed in range(4):
        X, g, w, d = noise(seed)
        X[17] += 70.0
        c = O.cscv(X, g, w, d)
        assert c["pbo"] < 0.05 and c["oos_mean"] > 50 and c["rank_median"] > 0.95
        h = O.haircut(X, g, np.ones(len(X), bool), n_boot=400, seed=seed)
        assert h["best"] == 17 and h["p"] < 0.01 and h["mean"] > 1.5 * h["null_mean_p95"]
        wf = O.walk_forward(X, g, w, d)
        assert [s["chosen"] for s in wf["steps"]][-4:] == [17] * 4 and wf["mean"] > 25


def test_the_split_count_follows_the_number_of_blocks():
    for blocks, want in ((2, 2), (4, 6), (5, 20), (6, 20), (7, 70)):
        X, g, w, d = noise(1, settings=12, blocks=blocks)
        c = O.cscv(X, g, w, d)
        assert c["splits"] == c["of"] == want, blocks        # odd: the smaller half and the larger half both get to choose
    X, g, w, d = noise(1, settings=12, blocks=12)
    c = O.cscv(X, g, w, d, max_splits=50, seed=3)
    assert c["splits"] == 50 and c["of"] == math.comb(12, 6)
    assert O.cscv(X, g, w, d, max_splits=50, seed=3)["pbo"] == c["pbo"]
    assert O.cscv(X[:, :3], g[:1], w[:, :1], d[:, :1]) is None and O.cscv(X[:1], g, w[:1], d[:1]) is None


def test_the_overfitting_test_chooses_like_the_search_does_with_the_account_limits():
    """A setting that is best on every half but wipes the account in one block is only chosen where that block is unseen."""
    X, g, w, d = noise(4, settings=40, blocks=6)
    X[5] += 200.0
    w[5, 2] = 1.0
    c = O.cscv(X, g, w, d)
    # eligible only on the 10 halves without block 2: chosen there, and wiped on the other half, which holds block 2
    assert c["oos_wiped"] == 0.5 and 90 < c["oos_mean"] < 110 and 90 < c["is_mean"] < 130
    free = O.cscv(X, g, w, d, allow_wiped=True)               # without the limit it is chosen on every half
    assert free["oos_wiped"] == 0.5 and free["oos_mean"] > 190 and free["is_mean"] > 190 and free["pbo"] == 0.0
    wf = O.walk_forward(X, g, w, d)
    assert [s["chosen"] == 5 for s in wf["steps"]] == [True, True, False, False, False]
    assert wf["wiped_steps"] == 1 and wf["steps"][1]["wiped"]
    # nothing eligible on the past: the step stays out
    w[:, 0] = 1.0
    out = O.walk_forward(X, g, w, d)
    assert out["stayed_out"] == 5 and out["total"] == 0.0 and all(s["chosen"] == -1 for s in out["steps"])


def test_walk_forward_cannot_profit_from_a_signal_that_only_the_future_shows():
    """Setting k is excellent in block k and slightly bad everywhere else: only hindsight can pick the right one."""
    blocks = 8
    X = np.full((blocks, blocks * 3), -1.0)
    g = quarters(blocks)
    for k in range(blocks):
        X[k, g[k]] = 100.0
    w = d = np.zeros((blocks, blocks))
    wf = O.walk_forward(X, g, w, d, name="mean")
    assert wf["n"] == 21 and wf["total"] == -21.0 and wf["positive"] == 0                 # it always trades yesterday's winner
    assert [s["chosen"] for s in wf["steps"]] == [0, 0, 0, 0, 0, 0, 0]                    # (ties go to the first found)
    assert all(s["train_mean"] > 0 for s in wf["steps"]) and wf["mean"] == -1.0
    # what a step chooses depends on earlier blocks only: rewriting everything from block 4 on changes no earlier step
    X2, g2, w2, d2 = noise(11, settings=60, blocks=blocks)
    base = O.walk_forward(X2, g2, w2, d2)
    Y = X2.copy()
    Y[:, 12:] = np.random.default_rng(99).normal(0, 500, Y[:, 12:].shape)
    w3 = w2.copy()
    w3[:, 4:] = 1.0
    moved = O.walk_forward(Y, g2, w3, d2)
    for a, b in zip(base["steps"][:4], moved["steps"][:4]):                                # steps trading blocks 1 .. 4
        assert (a["chosen"], a["train_objective"], a["train_mean"]) == (b["chosen"], b["train_objective"], b["train_mean"])
    assert base["steps"][2]["pnl"].tolist() == moved["steps"][2]["pnl"].tolist()           # block 3 itself is untouched
    assert base["steps"][3]["pnl"].tolist() != moved["steps"][3]["pnl"].tolist()           # block 4 was rewritten
    # every step is scored on the block after the ones it chose on, and the series is those months joined
    assert [s["block"] for s in base["steps"]] == list(range(1, blocks)) and base["months"].tolist() == list(range(3, 24))
    assert base["pnl"].tolist() == [X2[s["chosen"], m] for s in base["steps"] for m in s["months"]]
    assert base["total"] == pytest.approx(base["pnl"].sum()) and base["se"] == pytest.approx(base["pnl"].std(ddof=1) / math.sqrt(21))


def test_the_expected_maximum_of_normal_draws_and_its_inverse():
    for n, want in ((1, 0.0), (2, 0.5642), (3, 0.8463), (10, 1.5388), (100, 2.5076), (1000, 3.2414)):
        assert O.expected_max_normal(n) == pytest.approx(want, abs=2e-4)
    assert O.expected_max_normal(0.5) == 0.0 and 0.5642 < O.expected_max_normal(2.5) < 0.8463
    for n in (2, 7.5, 40, 3000):
        assert O.effective_trials(O.expected_max_normal(n)) == pytest.approx(n, rel=1e-3)
    assert O.effective_trials(0.0) == 1.0


def test_the_haircut_is_smaller_for_similar_settings_and_larger_for_more_trials():
    rng = np.random.default_rng(5)
    g = quarters(8)
    unrelated = rng.normal(0, 50, (200, 24))
    families = np.repeat(rng.normal(0, 50, (5, 24)), 40, axis=0) + rng.normal(0, 5, (200, 24))      # 5 ideas, 40 variants each
    everyone = np.ones(200, bool)
    a = O.haircut(unrelated, g, everyone, n_boot=400, seed=1)
    b = O.haircut(families, g, everyone, n_boot=400, seed=1)
    assert b["n_eff"] < 12 < 60 < a["n_eff"] and b["null_mean"] < 0.6 * a["null_mean"]
    assert a["independent"] == pytest.approx(b["independent"], rel=0.2)                   # the rule of thumb cannot tell them apart
    assert a["null_mean"] == pytest.approx(a["independent"], rel=0.15)                    # and is right for unrelated settings
    # settings tried elsewhere raise the haircut and the chance of a lucky best
    more = O.haircut(families, g, everyone, n_boot=400, seed=1, extra_trials=1800)
    assert more["extra"] == 1800 and more["null_mean"] > b["null_mean"] and more["null_mean_p95"] > b["null_mean_p95"]
    assert more["p"] == b["p"] and more["p_all"] == pytest.approx(1 - (1 - b["p"]) ** 10) and more["p_all"] > b["p_all"] == b["p"]
    # only eligible settings can be the best, and the result is reproducible from the seed
    some = everyone.copy()
    some[:150] = False
    c = O.haircut(unrelated, g, some, n_boot=400, seed=1)
    assert c["pool"] == 50 and c["best"] >= 150 and c["null_mean"] < a["null_mean"]
    assert O.haircut(unrelated, g, some, n_boot=400, seed=1) == c
    assert O.haircut(unrelated, g, np.zeros(200, bool)) is None and O.haircut(unrelated[:, :1], [np.arange(1)], everyone) is None


# ───────────────────────────── a whole analysis on a synthetic store ─────────────────────────────

GRID = {"name": "synthetic",
        "base": {"pivot_width": 3},                           # so that no setting of the grid is the live reference itself
        "parameters": {"rsi_length": [10, 12, 14, 16, 18], "peak_lookback": [10, 20, 30], "trend_tf": [None, "H4"],
                       "trend_mode": [1, -1]},
        "conditions": [{"when": "trend_tf is None", "ignore": ["trend_mode"]}],
        "references": {"other": {"rsi_length": 99}}}


def synthetic(tmp_path, monthly, start="2025-01-01", end="2026-01-01", wiped=lambda v, b: False, dip=lambda v, b: 50.0,
              origin=lambda v: "grid"):
    """
    A store filled by hand: every setting of GRID on every block, with ``monthly(values, month, rng)`` as its
    net P/L in a month. Returns what ``analyse`` needs.
    """
    sp = O.Space(GRID)
    per = O.make_period(start, end)
    stamps = ["d0"] * len(per.blocks)
    store = O.Store(tmp_path / "synthetic", {"format": O.STORE_FORMAT, "space": sp.fingerprint()}, log=quiet)
    rng = np.random.default_rng(0)
    todo = [(sp.key(c), c, sp.values(c), sp.overrides(c)) for c in sp.grid()]
    for key, c, values, ov in todo:
        store.add_setting(key, c, values, ov, origin(values), 0 if origin(values) == "grid" else 1)
    todo += [(O.config_key(sp.live.replace(**ov)), None, {"reference": name}, ov) for name, ov in sp.references.items()]
    for key, _, values, _ in todo:
        for b in per.blocks:
            pnl = [float(monthly(values, m, rng)) for m in b.months]
            store.add_eval({"kind": "eval", "key": key, "block": b.id, "data": "d0", "net": sum(pnl), "pnl": pnl,
                            "n": [12] * len(pnl), "baskets": 12 * len(pnl), "worst_basket": -7.5,
                            "wiped": bool(wiped(values, b.index)), "dip": float(dip(values, b.index))})
    store.close()
    return sp, store, per, stamps


def options(**kw) -> O.Options:
    return O.Options(**{"space": "synthetic", "bootstrap": 300, "top": 5, **kw})


def by_length(values, month, rng):
    """A plateau: the longer the RSI the better, the same in every month, plus a little noise; references lose."""
    if "reference" in values:
        return -40.0
    return 4.0 * (values["rsi_length"] - 13) + (5.0 if values["trend_tf"] == "H4" else 0.0) + rng.normal(0, 3)


def test_analysis_ranks_on_the_selection_months_and_reports_the_rest(tmp_path):
    sp, store, per, stamps = synthetic(tmp_path, by_length)
    hold = O.holdout_mask(per, "2025-10-01", None)
    a = O.analyse(sp, store, per, hold, stamps, options())
    assert len(a.keys) == 5 * 3 * 3 and a.incomplete == 0 and a.ok.all()        # trend off: 1 setting, trend on: 2 modes
    assert a.X.shape == (45, 9) and a.sel.blocks.tolist() == [0, 1, 2] and a.ho.blocks.tolist() == [3]
    best = a.settings[a.best]["values"]
    assert best["rsi_length"] == 18 and best["trend_tf"] == "H4"
    assert [a.settings[i]["values"]["rsi_length"] for i in a.top(5)] == [18] * 5
    assert a.s["mean"][a.best] == pytest.approx(25.0, abs=3.0) and a.h["mean"][a.best] == pytest.approx(25.0, abs=5.0)
    assert a.s["months"][a.best] == 9 and a.h["months"][a.best] == 3 and a.s["baskets"][a.best] == 108
    # the references are measured, shown, and never candidates
    assert [r["name"] for r in a.refs] == ["live", "other"]
    assert all(r["s"]["mean"] == -40.0 and r["h"]["mean"] == -40.0 for r in a.refs)
    assert not {r["key"] for r in a.refs} & set(a.keys)
    # the diagnostics agree that this is real
    assert a.haircut["p"] < 0.01 and a.pbo["pbo"] == 0.0 and a.wf["mean"] > 20 and a.carry["spearman"] > 0.9
    head, lines, checks = O.believe(a)
    assert head.startswith("**Holds up on every test run here, the held-out months included.**")
    assert checks == {"luck": "pass", "halves": "pass", "walk-forward": "pass", "neighbours": "pass", "hold-out": "pass"}
    assert len(lines) == 6 and "On the 3 held-out months" in lines[5]
    # without a hold-out the same result is worded as what it is: unconfirmed
    alone = O.analyse(sp, store, per, O.holdout_mask(per), stamps, options())
    head, _, checks = O.believe(alone)
    assert "hold-out" not in checks and set(checks.values()) == {"pass"}
    assert head.startswith("**Holds up on the months it was chosen on.**") and "confirm it once" in head


def test_settings_found_by_refinement_are_kept_out_of_the_tests_that_imitate_choosing(tmp_path):
    """
    Refinement looks at every selection month to decide what to run, so a setting it added is a child of hindsight.
    It can be the best setting and it counts as tried, but the walk-forward and the split test, whose point is to
    choose without part of the data, may only choose among the settings of the sample.
    """
    refined = lambda v: "refine" if v.get("rsi_length") == 18 else "grid"
    sp, store, per, stamps = synthetic(tmp_path / "a", by_length, origin=refined)
    a = O.analyse(sp, store, per, O.holdout_mask(per), stamps, options())
    assert len(a.keys) == 45 and a.sample == 36
    assert a.settings[a.best]["values"]["rsi_length"] == 18 and a.settings[a.best]["origin"] == "refine"
    assert a.haircut["pool"] == 45                                           # tried is tried
    chosen = [a.settings[st["chosen"]] for st in a.wf["steps"]]
    assert [c["values"]["rsi_length"] for c in chosen] == [16, 16, 16] and all(c["origin"] == "grid" for c in chosen)
    assert a.wf["mean"] == pytest.approx(12 + 5, abs=4) and a.wf["hindsight_mean"] == pytest.approx(20 + 5, abs=4)
    # the same store with every setting part of the sample: now the walk-forward may choose the 18s
    sp, store, per, stamps = synthetic(tmp_path / "b", by_length)
    b = O.analyse(sp, store, per, O.holdout_mask(per), stamps, options())
    assert b.sample == 45 and [b.settings[st["chosen"]]["values"]["rsi_length"] for st in b.wf["steps"]] == [18, 18, 18]
    assert a.X.tolist() == b.X.tolist() and a.order.tolist() == b.order.tolist()
    report = O.report_md(a)
    assert "Chosen among the 36 settings of the sample. The 9 settings added by refinement are left out here" in report
    assert "Chosen among all 45 settings." in O.report_md(b)
    # the parameter averages are over the sample too
    assert set(a.params[a.params["parameter"] == "rsi_length"]["value"]) == {10, 12, 14, 16}


def test_the_hold_out_plays_no_part_in_choosing(tmp_path):
    """Two stores that differ only in the held-out block give the same ranking, the same diagnostics, the same best."""
    def with_holdout(scale):
        def monthly(values, month, rng):
            noise_ = rng.normal(0, 20)
            if month >= 9:                                    # the last block: the truth is turned upside down
                return scale * by_length(values, month, rng) + noise_
            return by_length(values, month, rng) + noise_
        return monthly

    results = []
    for k, scale in enumerate((1.0, -3.0)):
        sp, store, per, stamps = synthetic(tmp_path / str(k), with_holdout(scale))
        a = O.analyse(sp, store, per, O.holdout_mask(per, "2025-10-01", None), stamps, options())
        results.append(a)
    a, b = results
    assert a.keys == b.keys and a.order.tolist() == b.order.tolist() and a.best == b.best
    assert a.X.tolist() == b.X.tolist() and a.s["objective"].tolist() == b.s["objective"].tolist()
    for name in ("haircut", "pbo"):
        assert {k: v for k, v in getattr(a, name).items() if k != "ranks"} == {k: v for k, v in getattr(b, name).items() if k != "ranks"}
    assert a.wf["pnl"].tolist() == b.wf["pnl"].tolist() and a.params["objective"].tolist() == b.params["objective"].tolist()
    assert a.nb["objective"].tolist() == b.nb["objective"].tolist()
    # only the held-out columns differ, and they say that the choice did not carry over
    assert a.h["mean"][a.best] > 15 and b.h["mean"][b.best] < -45
    assert O.believe(a)[2]["hold-out"] == "pass" and O.believe(b)[2]["hold-out"] == "fail"
    assert O.believe(b)[0].startswith("**Not proven.**") and "fails hold-out" in O.believe(b)[0]
    # with the same block chosen on instead of held out, the ranking does change
    sp, store, per, stamps = synthetic(tmp_path / "all", with_holdout(-3.0))
    c = O.analyse(sp, store, per, O.holdout_mask(per), stamps, options())
    assert c.order.tolist() != b.order.tolist() and c.X.shape == (45, 12)


def test_parameter_averages_and_neighbours_tell_a_plateau_from_a_spike(tmp_path):
    sp, store, per, stamps = synthetic(tmp_path / "plateau", by_length)
    a = O.analyse(sp, store, per, O.holdout_mask(per), stamps, options())
    p = a.params.set_index(["parameter", "value"])
    # the average over every setting that contains the value: 4 USD per step of the RSI length, nothing for the look-back
    means = [p.loc[("rsi_length", v), "mean"] for v in (10, 12, 14, 16, 18)]
    assert means == pytest.approx([-12 + 10 / 3, -4 + 10 / 3, 4 + 10 / 3, 12 + 10 / 3, 20 + 10 / 3], abs=1.0)
    assert [p.loc[("rsi_length", v), "settings"] for v in (10, 18)] == [9, 9]
    assert [p.loc[("peak_lookback", v), "mean"] for v in (10, 20, 30)] == pytest.approx([10 / 3 + 4] * 3, abs=1.0)
    assert p.loc[("trend_tf", "H4"), "mean"] - p.loc[("trend_tf", None), "mean"] == pytest.approx(5.0, abs=1.0)
    assert p.loc[("trend_tf", "H4"), "settings"] == 30 and p.loc[("trend_tf", None), "settings"] == 15
    # trend_mode exists only where the trend filter is on: the settings without one are left out of its averages
    assert p.loc[("trend_mode", 1), "settings"] == p.loc[("trend_mode", -1), "settings"] == 15
    assert p.loc[("rsi_length", 18), "positive"] == 1.0 and p.loc[("rsi_length", 10), "positive"] == 0.0
    # the best setting: its neighbours are one RSI step down (-8), the look-backs next to its own, no trend filter (-5)
    # and the other trend mode
    b = a.best
    around = 4 + (a.settings[b]["values"]["peak_lookback"] == 20)
    assert a.nb["of"][b] == a.nb["n"][b] == a.nb["positive"][b] == around
    assert a.nb["objective"][b] == pytest.approx(a.s["objective"][b] - (8 + 5) / around, abs=2.5)
    assert O.believe(a)[2]["neighbours"] == "pass"

    # a spike: one single setting is good, everything around it loses
    def spike(values, month, rng):
        if "reference" in values:
            return 0.0
        lone = values["rsi_length"] == 14 and values["peak_lookback"] == 20 and values["trend_tf"] is None
        return (60.0 if lone else -10.0) + rng.normal(0, 3)

    sp, store, per, stamps = synthetic(tmp_path / "spike", spike)
    a = O.analyse(sp, store, per, O.holdout_mask(per), stamps, options())
    b = a.best
    assert a.settings[b]["values"] == {"rsi_length": 14, "peak_lookback": 20, "trend_tf": None}
    assert a.nb["of"][b] == a.nb["n"][b] == 5 and a.nb["positive"][b] == 0 and a.nb["objective"][b] < -8
    head, lines, checks = O.believe(a)
    assert checks["neighbours"] == "fail" and checks["luck"] == "pass" and head.startswith("**Not proven.**")
    assert any("It is a spike" in x for x in lines)


def test_no_edge_and_no_eligible_setting_are_said_in_so_many_words(tmp_path):
    losing = lambda values, month, rng: rng.normal(-30.0, 10.0)
    sp, store, per, stamps = synthetic(tmp_path / "losing", losing)
    a = O.analyse(sp, store, per, O.holdout_mask(per), stamps, options())
    head, lines, checks = O.believe(a)
    assert a.s["mean"].max() < 0 and head.startswith("**No edge in this space.**") and "lower bound -" in head
    # settings without any edge: the best of 45 has a positive mean, and the luck test says that this is all it is
    flat = lambda values, month, rng: rng.normal(0.0, 30.0)
    sp, store, per, stamps = synthetic(tmp_path / "flat", flat)
    a = O.analyse(sp, store, per, O.holdout_mask(per), stamps, options(objective="mean"))
    head, lines, checks = O.believe(a)
    assert a.s["mean"][a.best] > 10 and a.haircut["null_mean"] == pytest.approx(a.s["mean"][a.best], abs=10.0)
    assert checks["luck"] == "fail" and not head.startswith("**Holds up")

    sp, store, per, stamps = synthetic(tmp_path / "wiped", by_length, wiped=lambda v, b: b == 2,
                                       dip=lambda v, b: 2000.0 if b == 2 else 50.0)
    a = O.analyse(sp, store, per, O.holdout_mask(per), stamps, options())
    assert a.best == -1 and not a.ok.any() and a.top() == [] and a.haircut is None
    head, lines, _ = O.believe(a)
    assert head.startswith("**No setting can be recommended.**") and "45 wiped the replayed 2,000 USD account" in head
    assert O.best_json(a)["best"] is None and "(1)" in O.report_md(a)                   # ranked all the same, in brackets
    # the same store with the limits lifted has a best setting again
    free = O.analyse(sp, store, per, O.holdout_mask(per), stamps, options(allow_wiped=True, max_dip=0.0))
    assert free.best >= 0 and free.ok.all() and free.s["wiped_blocks"][free.best] == 1
    # a dip limit alone: only the blocks chosen on count, the held-out block's dip does not
    held = O.analyse(sp, store, per, O.holdout_mask(per, "2025-07-01", "2025-10-01"), stamps, options(allow_wiped=True))
    assert held.ok.all() and held.h["max_dip"][held.best] == 2000.0 and held.s["max_dip"][held.best] == 50.0


def test_files_written_from_a_synthetic_analysis(tmp_path):
    sp, store, per, stamps = synthetic(tmp_path, by_length, start="2025-01-01", end="2026-01-13")
    hold = O.holdout_mask(per, None, "2025-04-01")
    a = O.analyse(sp, store, per, hold, stamps, options(symbol="XAUUSDm"), {"space": sp.fingerprint(), "engine": "e", "live": "l"})
    out = tmp_path / "files"
    paths = O.write_outputs(a, out)
    assert sorted(p.name for p in out.iterdir()) == ["best.json", "holdout_looks.json", "monthly.csv", "report.md", "trials.csv"]
    monthly = pd.read_csv(paths["monthly.csv"])
    # January to March are held out; the thirteen days of January 2026 are shown and used nowhere
    assert list(monthly.columns[3:6]) == ["2025-01 hold-out", "2025-02 hold-out", "2025-03 hold-out"]
    assert monthly.columns[-1] == "2026-01 partial" and len(monthly.columns) == 3 + 13
    trials = pd.read_csv(paths["trials.csv"])
    assert len(trials) == 45 + 2 and set(trials["months"]) == {9} and set(trials["holdout_months"]) == {3}
    assert trials["total"].tolist() == pytest.approx(monthly.iloc[:, 6:15].sum(axis=1).tolist(), abs=1e-3)
    assert (trials["trend_tf"].fillna("") == "").sum() == 2 and (trials["trend_tf"] == "none").sum() == 15    # null is a value
    assert trials[trials["trend_tf"] == "none"]["trend_mode"].isna().all()
    report = paths["report.md"].read_text(encoding="utf-8")
    assert "| Shown only | 2026-01: less than half a month inside the period" in report
    assert "| Chosen on | 9 months (2025-04 … 2025-12) |" in report and "| Held out | 3 months (2025-01 … 2025-03)" in report
    assert "### Does the ranking carry over to the held-out months?" in report and "nan" not in report.lower()
    # block by block: the held-out block is marked, and the blocks of a row are its months added up
    head = next(line for line in report.splitlines() if line.startswith("| # | 2025-01-01 →"))
    assert head == "| # | 2025-01-01 → (held out) | 2025-04-01 → | 2025-07-01 → | 2025-10-01 → | 2026-01-01 → |"
    first = report.splitlines()[report.splitlines().index(head) + 2].split("|")[1:-1]
    assert [float(x) for x in first[1:]] == pytest.approx(
        [monthly.iloc[0, 3:6].sum(), monthly.iloc[0, 6:9].sum(), monthly.iloc[0, 9:12].sum(), monthly.iloc[0, 12:15].sum(),
         monthly.iloc[0, 15]], abs=0.06)
    best = json.loads(paths["best.json"].read_text(encoding="utf-8"))
    assert best["best"]["values"] == a.settings[a.best]["values"] and best["checks"]["hold-out"] == "pass"
    assert "--start 2025-04-01 --end 2026-01-13" in best["best"]["run"]
    assert "--set rsi_length=18" in best["best"]["run"] and "--set 'trend_tf=\"H4\"'" in best["best"]["run"]
    # the hold-out has been looked at once; the same report again is not a second look, other settings in front of it are
    assert len(json.loads((out / "holdout_looks.json").read_text(encoding="utf-8"))) == 1
    O.write_outputs(a, out)
    assert len(json.loads((out / "holdout_looks.json").read_text(encoding="utf-8"))) == 1
    b = O.analyse(sp, store, per, hold, stamps, options(objective="worst_block", top=3))
    O.write_outputs(b, out)
    looks = json.loads((out / "holdout_looks.json").read_text(encoding="utf-8"))
    assert len(looks) == 2 and "This hold-out has now been reported 2 times" in (out / "report.md").read_text(encoding="utf-8")


# ───────────────────────────── the command line ─────────────────────────────

def test_the_command_line_end_to_end(tiny_run, tmp_path, capsys, live_root):
    out = tmp_path / "cli"
    argv = ["optimise", "--space", str(tiny_run["dir"] / "tiny.json"), "--symbol", SYM, "--start", HOUR[0], "--end", HOUR[1],
            "--block", "20min", "--slice", "10min", "--holdout-to", "2026-11-09 06:20", "--jobs", "1", "--bootstrap", "200",
            "--sampler", "grid", "--refine-rounds", "0", "--out", str(out), "--live-root", str(live_root)]
    assert cli.main(argv) == 0
    text = capsys.readouterr().out
    assert "grid: 15 settings, 15 new" in text and "15 settings ranked, 48 backtests run by this call" in text
    assert f"report: {out / 'report.md'}" in text and "best: max_adds=" in text
    for name in ("trials.csv", "monthly.csv", "report.md", "best.json", "evaluations.jsonl"):
        assert (out / name).exists(), name
    # the same matrix as the library call with the random sampler (a space this small is taken whole either way);
    # compared by key, since settings with identical results may be listed in either order
    a, b = (pd.read_csv(f).sort_values("key").reset_index(drop=True) for f in (out / "monthly.csv", tiny_run["out"] / "monthly.csv"))
    assert list(a["key"]) == list(b["key"])
    # (the rank among settings whose results tie may differ with the order in which they were stored)
    pd.testing.assert_frame_equal(a.drop(columns=["rank"]), b.drop(columns=["rank"]))
    assert set(pd.read_csv(out / "trials.csv")["origin"]) == {"grid", "reference"}
    # again: nothing to compute; and --report-only never computes
    assert cli.main(argv) == 0 and "15 settings ranked, 0 backtests run by this call" in capsys.readouterr().out
    assert cli.main(argv + ["--report-only", "--objective", "sharpe"]) == 0
    assert "0 backtests run by this call" in capsys.readouterr().out
    # what cannot be done is said in one line
    for extra, needle in ((["--holdout-to", "2026-11-09 06:30"], "is not where a block starts or ends"),
                          (["--space", "no_such_space"], "no search space 'no_such_space'"),
                          (["--start", "2026-09-01"], "the tick store has no BTCUSDm data for 2026-09"),
                          (["--report-only", "--out", str(tmp_path / "nowhere")], "has been run on every selection block")):
        with pytest.raises(SystemExit) as e:
            cli.main(argv + extra)
        assert str(e.value).startswith("optimise: ") and needle in str(e.value)


def test_the_short_list_is_validated_on_raw_ticks_with_the_real_account(tiny_run, tmp_path, monkeypatch):
    from backtesting.analysis import robustness

    out = tmp_path / "validated"
    opt = lambda **kw: tiny_run["options"](**{"out": str(out), "validate": True, "validate_top": 2, "validate_seeds": 3, **kw})
    calls = []
    real = robustness.timing_ensemble

    def counting(cfg, windows, **kw):
        calls.append((cfg, windows, kw))
        return real(cfg, windows, **kw)

    monkeypatch.setattr(robustness, "timing_ensemble", counting)
    res = O.optimise(opt(), log=quiet)
    v = res["analysis"].validation
    # the best two and the two references ("no ladder" is not one of the best two), three blocks, three loop timings
    assert len(v) == 4 * 3 * 3 and list(dict.fromkeys(v["setting"])) == ["#1", "#2", "live (reference)", "no ladder (reference)"]
    assert Counter(v["role"]) == {"selection": 24, "hold-out": 12} and sorted(v["seed"].unique()) == [1, 2, 3]
    assert len(calls) == 3
    cfg, windows, kw = calls[0]
    assert cfg.initial_balance == 2000.0 and cfg.fixed_units == 0 and cfg.step_up_balance == 2500.0      # the real account
    assert list(windows) == ["2026-11-09 06:00 → 2026-11-09 06:20"] and kw["seeds"] == [1, 2, 3]
    assert kw["overrides"][0] == res["analysis"].settings[res["analysis"].best]["overrides"] and kw["overrides"][2] == {}
    # a row is a raw-tick run of that block with the live loop timing of that seed
    row = v[(v["setting"] == "live (reference)") & (v["seed"] == 2) & (v["role"] == "hold-out")].iloc[0]
    from backtesting import experiments as E
    from backtesting.engine import fast
    c = E.live_config(SYM, tiny_run["options"]().live_root, start="2026-11-09 06:00:00", end="2026-11-09 06:20:00",
                      **robustness.live_timing(2))
    plain = fast.run(c, mode="ticks", light=True)
    assert row["net_profit"] == pytest.approx(plain.scalars["final_equity"] - 2000.0, abs=0.006) and row["baskets"] == len(plain.baskets)
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "## The short list on raw ticks" in report and "### Hold-out blocks" in report and "| live (reference) |" in report
    # finished blocks are kept: a second call replays nothing, and a report-only call shows what is stored
    again = O.optimise(opt(), log=quiet)
    assert len(calls) == 3 and len(again["analysis"].validation) == 36
    shown = O.optimise(opt(report_only=True, validate=False), log=quiet)
    assert len(calls) == 3 and len(shown["analysis"].validation) == 36
    # a longer short list replays only the settings that are new
    O.optimise(opt(validate_top=3), log=quiet)
    assert len(calls) == 6 and all(len(c[2]["overrides"]) == 1 for c in calls[3:])
