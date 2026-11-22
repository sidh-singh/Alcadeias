"""
A basket's target, stop and add gap: multiples of the volatility unit, in USD per unit = multiple x unit x
contract_size x mtqty (gold 100 x 0.01 = $1 per $1 move, BTC 1 x 0.01 = $0.01 per $1 move), the unit first
capped at VOL_CAP_USD_PER_UNIT / (contract_size x mtqty); the stop is checked before the target, the stop is
inclusive (<=) and the target strict (>). Values from the backtester's worked example (map_levers.md §5).
"""
import pytest

from conftest import F, MAGIC, baskets, market, run_bot

XAU_V3LITE = dict(VOL_TF='H1', VOL_LEN=24, TARGET_USD_PER_UNIT=None, STOP_LOSS_USD_PER_UNIT=None,
                  TARGET_VOL=8.0, STOP_VOL=8.0, VOL_CAP_USD_PER_UNIT=0.0)
XAU_TOP2 = dict(XAU_V3LITE, TARGET_VOL=8.0, STOP_VOL=4.0, VOL_CAP_USD_PER_UNIT=12.0)
XAU_TOP1 = dict(XAU_V3LITE, TARGET_VOL=10.0, STOP_VOL=8.0, LADDER_GAP_VOL=1.0)
XAU_TOP3 = dict(XAU_TOP1, VOL_CAP_USD_PER_UNIT=12.0)
BTC_TOP2 = dict(XAU_V3LITE, TARGET_VOL=10.0, STOP_VOL=8.0, VOL_CAP_USD_PER_UNIT=12.0)


def _pos(count, profit, vol=0.01):
    return {'count': count, 'total_profit': profit, 'total_volume': round(vol * count, 2), 'first_profit': profit,
            'first_volume': vol, 'last_profit': profit, 'last_volume': vol, 'positions': []}


def test_gold_and_btc_usd_per_price_from_the_terminal_and_from_the_table(mods):
    fake, clock = market(60)
    m = mods(fake=fake, clock=clock)
    bot = F.make_bot(m, fake, 'XAUUSDm', F.Run())
    assert bot._usd_per_price_of('XAUUSDm', 'XAUUSDm', 0.01) == 1.0          # trade_contract_size 100
    fake2, clock2 = market(60, symbol='BTCUSDm', contract=1.0, price0=70000.0, report_contract_size=False)
    m2 = mods(fake=fake2, clock=clock2)
    bot2 = F.make_bot(m2, fake2, 'BTCUSDm', F.Run())
    assert bot2._usd_per_price_of('BTCUSDm', 'BTCUSDm', 0.01) == 0.01        # CONTRACT_SIZE_FALLBACK 'BTC': 1


def test_xau_v3lite_distances_are_uncapped(mods):
    app = mods(**XAU_V3LITE).app
    lv = app.basket_levels(9.4, 1.0)
    assert lv['target_usd_per_unit'] == 8.0 * 9.4 * 1.0 and lv['stop_usd_per_unit'] == 8.0 * 9.4 * 1.0
    assert lv['gap_px'] == 0.0
    big = app.basket_levels(50.967, 1.0)                  # 2 Feb 2026: one stop = $407.74 per unit
    assert round(big['stop_usd_per_unit'], 2) == 407.74 and big['vol_unit'] == 50.967


def test_xau_top2_cap_binds_above_12_dollars(mods):
    app = mods(**XAU_TOP2).app
    lv = app.basket_levels(13.7, 1.0)
    assert lv['vol_unit'] == 12.0 and lv['vol_unit_raw'] == 13.7
    assert lv['target_usd_per_unit'] == 96.0 and lv['stop_usd_per_unit'] == 48.0
    free = app.basket_levels(9.4, 1.0)
    assert free['vol_unit'] == 9.4 and free['target_usd_per_unit'] == 8.0 * 9.4 and free['stop_usd_per_unit'] == 4.0 * 9.4


def test_xau_top3_worked_example(mods):
    app = mods(**XAU_TOP3).app
    capped = app.basket_levels(50.967, 1.0)
    assert (capped['target_usd_per_unit'], capped['stop_usd_per_unit'], capped['gap_px']) == (120.0, 96.0, 12.0)
    free = app.basket_levels(9.931, 1.0)
    assert round(free['target_usd_per_unit'], 2) == 99.31 and round(free['stop_usd_per_unit'], 2) == 79.45
    assert free['gap_px'] == 9.931


def test_xau_top1_gap_is_one_uncapped_unit(mods):
    app = mods(**XAU_TOP1).app
    lv = app.basket_levels(30.175, 1.0)
    assert lv['gap_px'] == 30.175 and lv['target_usd_per_unit'] == 10.0 * 30.175 and lv['stop_usd_per_unit'] == 8.0 * 30.175


def test_btc_top2_cap_is_usd_per_unit_not_price(mods):
    app = mods(**BTC_TOP2).app
    lv = app.basket_levels(725.7, 0.01)                   # 6 Feb 2026: target $72.57, stop $58.06
    assert round(lv['target_usd_per_unit'], 2) == 72.57 and round(lv['stop_usd_per_unit'], 2) == 58.06
    assert lv['vol_unit'] == 725.7                        # $7.26 per unit < $12: not capped
    wild = app.basket_levels(1500.0, 0.01)                # the cap starts at a unit of 1,200 BTC-$
    assert wild['vol_unit'] == pytest.approx(1200.0) and wild['target_usd_per_unit'] == pytest.approx(120.0)
    assert wild['stop_usd_per_unit'] == pytest.approx(96.0)


def test_live_levels_are_the_strategy_hedge_dollar_target_and_no_stop(mods):
    app = mods().app
    lv = app.basket_levels(None, 1.0)
    assert lv['target_usd_per_unit'] == 1 and lv['stop_usd_per_unit'] is None and lv['gap_px'] == 0.0
    assert mods(TARGET_USD_PER_UNIT=2.5, STOP_LOSS_USD_PER_UNIT=4.0).app.basket_levels(None, 1.0)['stop_usd_per_unit'] == 4.0


@pytest.mark.parametrize('side', [1, -1])
def test_stop_is_inclusive_target_strict_and_the_stop_comes_first(mods, side):
    s = mods(FORCE_CLOSE_ENABLED=False, MAX_ADDS=0).strategy
    st = s.Strategy()
    stop, target = 75.2, 75.2
    close = s.Signal.CLOSE_BUY if side > 0 else s.Signal.CLOSE_SELL

    def sig(profit):
        b, sl = (_pos(1, profit), None) if side > 0 else (None, _pos(1, profit))
        out = st.calculate_signal(None, b, sl, 1, close_threshold=target, stop_threshold=stop, rsi_mtf={}, slopes={})
        return (out[0] if side > 0 else out[1]), out[2]['exit_reason']

    assert sig(-75.2) == (close, 'stop_loss')              # at the stop: closed
    assert sig(-75.19)[0] == s.Signal.DO_NOTHING
    assert sig(75.2)[0] == s.Signal.DO_NOTHING              # at the target: held (strict)
    assert sig(75.21) == (close, 'target')
    # both "hit" (a zero stop): the stop is the reason
    out = st.calculate_signal(None, _pos(1, 0.0), None, 1, close_threshold=-1.0, stop_threshold=0.0, rsi_mtf={}, slopes={})
    assert out[2]['exit_reason'] == 'stop_loss'


def test_the_basket_levels_scale_with_its_unit(tmp_path):
    """In the loop: a basket's USD target / stop = the per-unit amounts x the basket's unit count."""
    from conftest import SCALED
    fake, clock = market(900, seed=5, balance=5000.0)                # the whole of $5,000 over $2,500: 3 units
    run = run_bot(fake, clock, overrides=dict(SCALED, ACCOUNT_SHARE=1.0), state_dir=tmp_path)
    assert not run.errors
    opens = [d for d in fake.deals if d.entry == 0 and d.magic == MAGIC]
    assert opens and opens[0].volume == 0.03
    held = [p for p in run.polls if p['levels']]
    assert held and held[0]['levels']['units'] == 3
    for p in held:
        lv = p['levels']
        u = lv['units']               # the balance moves with this run's own results (2 after losses)
        assert u == p['units'] and u in (2, 3)
        assert lv['stop_usd'] == pytest.approx(round(2.0 * lv['vol_unit'] * 1.0 * u, 2))
        assert lv['target_usd'] == pytest.approx(round(2.0 * lv['vol_unit'] * 1.0 * u, 2))
    first_vols = {round(b['legs'][0]['vol'] / 0.01) for b in baskets(fake, magic=MAGIC)}
    assert first_vols <= {2, 3}
