"""
With every design lever at its default the ported bot is the live bot v3.9.2: replayed on the same market,
it takes the same decision on every poll (signal, scores, counts, floating P/L, unit, cooldown, ladder RSIs)
and the same fills as the code before the port (the branch's 'demo: ...' commit).

The old code knows no mode rule and no account check: it runs in its own mode ('demo') on the fake's real account.
The ported bot runs as it does for real money: mode 'live', the credentials of that account. (Both keep 1 unit on
this $2,000 account: the old code counts the whole balance over $2,500, the ported bot its share of it.)
"""
import pytest

from conftest import COMMENT, DEFAULTS, F, MAGIC, ROOT, market

POLL_KEYS = ('t', 'buy', 'sell', 'fresh', 'open_score', 'fc_score', 'nb', 'ns', 'profit', 'units',
             'entry_allowed', 'exit_reason', 'rsi')


def _deals(fake):
    return [(d.time_msc, d.type, d.entry, d.volume, d.price, d.profit) for d in fake.deals]


def _replay_both(baseline_root, tmp_path, seconds, seed, overrides=None):
    out = {}
    for name, root in (('ported', ROOT), ('baseline', baseline_root)):
        fake, clock = market(seconds, seed=seed)
        # the ported bot from its default constants (a design block at the end of constants.py is ignored)
        ov = {**DEFAULTS, **(overrides or {})} if name == 'ported' else dict(overrides or {})
        # both bots write in this test's tmp_path, never in their OUTPUT_DIR (on the server: a running bot's folder)
        ov['OUTPUT_DIR'] = str(tmp_path / name / 'output')
        run = F.run_bot(root, fake, clock, 'XAUUSDm', overrides=ov, state_dir=tmp_path / name / 'state',
                        mode='live' if name == 'ported' else 'demo')
        assert not run.errors, run.errors[:3]
        out[name] = (run, fake)
    return out


def _assert_same(out):
    (new, fnew), (old, fold) = out['ported'], out['baseline']
    assert len(new.polls) == len(old.polls)
    for i, (p, q) in enumerate(zip(new.polls, old.polls)):
        for k in POLL_KEYS:
            assert p[k] == q[k], f'poll {i} {k}: ported {p[k]!r} != baseline {q[k]!r}'
    assert _deals(fnew) == _deals(fold)
    assert fnew.balance == fold.balance
    # the same broker sl / tp on every request (no stop: the live auto sl / tp, no backstop)
    assert [(o.get('sl'), o.get('tp')) for o in fnew.orders] == [(o.get('sl'), o.get('tp')) for o in fold.orders]


@pytest.mark.slow
def test_live_defaults_take_the_live_decisions(baseline_root, tmp_path):
    """H1 + M15 entry, M15 force-close, $1 x unit target, the RSI ladder: 40 minutes, several baskets."""
    out = _replay_both(baseline_root, tmp_path, 2400, seed=3)
    _assert_same(out)
    fake = out['ported'][1]
    assert sum(d.entry == 1 for d in fake.deals) >= 2          # baskets were opened and closed
    # the only difference in what was sent: this bot's magic number and comment
    for o in fake.orders:
        assert o['magic'] == MAGIC and o['comment'] == COMMENT
    assert all('magic' not in o for o in out['baseline'][1].orders)


@pytest.mark.slow
def test_live_rules_on_fast_timeframes_with_the_fibonacci_ladder(baseline_root, tmp_path):
    """The same live rules driven by M5/M1 sections (as the backtester's parity tests do), so that the ladder
    adds 0.02 and 0.03 lots within the window: still poll-for-poll the same."""
    ov = {'OPEN_SCORE_WEIGHTS': {'M5': 1, 'M1': 1}, 'FORCE_CLOSE_SCORE_WEIGHTS': {'M1': 1},
          'SLOPE_TIMEFRAMES': ['TIMEFRAME_M5', 'TIMEFRAME_M1']}
    out = _replay_both(baseline_root, tmp_path, 1500, seed=7, overrides=ov)
    _assert_same(out)
    vols = sorted({d.volume for d in out['ported'][1].deals if d.entry == 0})
    assert vols == [0.01, 0.02, 0.03]
