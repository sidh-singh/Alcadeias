"""Build backtesting/research/ladder_kernels.py: a verbatim copy of kernels.run_kernel plus asserted, opt-in patches."""
import sys
from pathlib import Path

REPO = Path("/Users/sidharthsingh/Desktop/Alcadeias/Alcadeias")
src = (REPO / "backtesting/engine/kernels.py").read_text()
i0 = src.index("@njit(cache=True)\ndef run_kernel(")
body = src[i0:]


def rep(old, new):
    global body
    n = body.count(old)
    if n != 1:
        sys.exit(f"patch anchor found {n} times:\n{old}")
    body = body.replace(old, new)


def rep_block(start, end, new):
    """Replace the lines from the one equal to `start` through the first later line equal to `end`."""
    global body
    lines = body.split("\n")
    s = [i for i, l in enumerate(lines) if l == start]
    if len(s) != 1:
        sys.exit(f"block start found {len(s)} times: {start!r}")
    e = [i for i, l in enumerate(lines) if l == end and i > s[0]]
    if not e:
        sys.exit(f"block end not found: {end!r}")
    lines[s[0]:e[0] + 1] = new.rstrip("\n").split("\n")
    body = "\n".join(lines)


# 1. name and the new inputs
rep("def run_kernel(t_ms, bid, ask,", "def run_kernel2(t_ms, bid, ask,")
rep("               ladder_tf, ladder_mult, hour_ok, reg_t, reg_v,\n               ci, cf,\n",
    "               ladder_tf, ladder_mult, hour_ok, reg_t, reg_v,\n"
    "               tier_lv, tier_ser, ser_t, ser_v, ser_off, VOL2,\n               ci, cf,\n")

# 2. the extension settings
rep("    a_sg = cf[CF_MACD_ASG]\n", """    a_sg = cf[CF_MACD_ASG]

    # ── ladder-study extensions (slots CI2_* / CF2_* after CI_N / CF_N; every one is off at its default) ──
    tier_levels = ci[CI2_TIER_LEVELS] != 0
    gap_f = ci[CI2_GAP_TF]
    gap_mult = cf[CF2_GAP_MULT]
    gap_growth = cf[CF2_GAP_GROWTH]
    stop_pct = cf[CF2_STOP_PCT]
    hold_min_adds = ci[CI2_HOLD_MIN_ADDS]
    be_after = ci[CI2_BE_AFTER_ADDS]
    be_spreads = cf[CF2_BE_SPREADS]
    tgt_shrink = ci[CI2_TARGET_SHRINK] != 0
    final_f = ci[CI2_FINAL_TF]
    add_trend_f = ci[CI2_ADD_TREND_TF]
    add_trend_mode = ci[CI2_ADD_TREND_MODE]
    add_blk_from = ci[CI2_ADD_BLOCK_FROM]
    add_blk_to = ci[CI2_ADD_BLOCK_TO]
    abn_on = ci[CI2_ABN_ON] != 0
    flat_from = ci[CI2_FLAT_FROM]
    flat_to = ci[CI2_FLAT_TO]
    side_rsi_f = ci[CI2_SIDE_RSI_TF]
    side_hi = cf[CF2_SIDE_RSI_HI]
    side_lo = cf[CF2_SIDE_RSI_LO]
    rev_on = ci[CI2_REVERSE] != 0
    rev_mult = cf[CF2_REVERSE_MULT]
    hedge_mode = ci[CI2_HEDGE_MODE]
    hedge_stop_mult = cf[CF2_HEDGE_STOP_MULT]
    partial_mode = ci[CI2_PARTIAL]
    sizing = ci[CI2_SIZING]
    pf_risk = cf[CF2_PF_RISK]
    pf_atr = cf[CF2_PF_ATR_MULT]
    vt_k = cf[CF2_VT_K]
    # closed-bar series computed outside the kernel (ladder_ind), packed: series s is ser_t/ser_v[ser_off[s]:ser_off[s+1]],
    # value ser_v[i] in force from ser_t[i] (ms) on
    n_ser = ser_off.shape[0] - 1
    eser_on = n_ser > SER_ENTRY and ser_off[SER_ENTRY + 1] > ser_off[SER_ENTRY]
    aser_on = n_ser > SER_ADD and ser_off[SER_ADD + 1] > ser_off[SER_ADD]
    sp = np.full(n_ser + 1, -1, np.int64)
    sv = np.zeros(n_ser + 1)
    sk = np.zeros(n_ser + 1, np.uint8)
""")

# 3. per-position side and the new basket state
rep("    pos_t = np.zeros(MAXPOS, np.int64)\n",
    "    pos_t = np.zeros(MAXPOS, np.int64)\n    pos_side = np.zeros(MAXPOS, np.int64)   # +1 / -1 per position (= side unless a hedge mode)\n")
rep("    basket_lot_units = 0.0\n", """    basket_lot_units = 0.0
    n_lad = 0              # ladder positions (entry + adds; = n_pos unless a hedge leg is open)
    n_opened = 0
    max_lad = 0
    part_pnl = 0.0         # realised by partial closes / hedge unwinds of the basket in hand
    n_hedge = 0
    hedged = False
    hedge_ever = False
    frozen = 0.0
    armed2 = False
    last_ref_b = 0.0
    last_ref_a = 0.0
    b_sl_abs = 0.0
    b_sl_abs_on = False
    is_rev = False
    rev_pending = 0
    rev_units = 1
    rev_deadline = 0
""")

# 4. timeframes whose bar index must advance
rep("            if need_rsi[f] == 1 or need_slope[f] == 1 or f == trend_f or f == vol_f:",
    "            if need_rsi[f] == 1 or need_slope[f] == 1 or f == trend_f or f == vol_f or f == gap_f or f == add_trend_f:")

# 5. valuation per position side
rep("                if side > 0:\n                    profit += _round2(", "                if pos_side[i] > 0:\n                    profit += _round2(")

# 6. margin: gross, or the larger side when a hedge mode is on
rep("""        used_margin = 0.0
        if n_pos > 0:
            for i in range(n_pos):
                used_margin += pos_lots[i] * contract * pos_price[i] / leverage
""", """        used_margin = 0.0
        if n_pos > 0:
            if hedge_mode == 0:
                for i in range(n_pos):
                    used_margin += pos_lots[i] * contract * pos_price[i] / leverage
            else:
                mb = 0.0
                msl = 0.0
                for i in range(n_pos):
                    if pos_side[i] > 0:
                        mb += pos_lots[i] * contract * pos_price[i] / leverage
                    else:
                        msl += pos_lots[i] * contract * pos_price[i] / leverage
                used_margin = mb if mb > msl else msl
""")

# 7. closed-bar series in force, and the weekly flat window
rep("            reg_now = reg_v[reg_i] if reg_i >= 0 else 0\n", """            reg_now = reg_v[reg_i] if reg_i >= 0 else 0
        for s in range(n_ser):
            o0 = ser_off[s]
            o1 = ser_off[s + 1]
            while o0 + sp[s] + 1 < o1 and ser_t[o0 + sp[s] + 1] <= T:
                sp[s] += 1
            if sp[s] >= 0:
                sv[s] = ser_v[o0 + sp[s]]
                sk[s] = 1
        in_flat = False
        if flat_from >= 0:
            mow2 = ((tsec // 86400 + 3) % 7) * 1440 + (tsec % 86400) // 60
            if flat_from > flat_to:
                in_flat = mow2 >= flat_from or mow2 < flat_to
            else:
                in_flat = mow2 >= flat_from and mow2 < flat_to
""")

# 8. stop-and-reverse: the pending reversal order while flat
rep("        tier = -1\n        if n_pos == 0:\n", "        tier = -1\n        rev_now = False\n        if n_pos == 0:\n")
rep("""                else:
                    signal = 2
        else:
            prev_dir = 0
""", """                else:
                    signal = 2
            if rev_pending != 0:
                if T <= rev_deadline:
                    signal = 1 if rev_pending > 0 else 2
                    rev_now = True
                else:
                    rev_pending = 0
                    counters[K2_REV_DROP] += 1
        else:
            prev_dir = 0
""")

# 9. exits: target variants, weekly flat, % stop, hedged net stop
rep("""            tgt = b_target * (basket_lot_units if target_per_lot else basket_units)
            if b_sl_on and profit <= -b_sl * basket_units:
                signal = 3 if side > 0 else 4
                reason = R_STOPLOSS
            elif b_target_on and profit > tgt:
""", """            tgt = b_target * (basket_lot_units if target_per_lot else basket_units)
            if be_after > 0 or tgt_shrink:
                lt_now = 0.0
                for i in range(n_pos):
                    lt_now += pos_lots[i]
                floor_usd = (a - b) * lt_now * contract
                if be_after > 0 and n_lad - 1 >= be_after:
                    tgt = be_spreads * floor_usd          # deep basket: break-even plus spreads
                elif tgt_shrink:
                    tgt = b_target * basket_units / n_lad  # target_0 / positions, never below one spread
                    if tgt < floor_usd:
                        tgt = floor_usd
            fin_hit = False
            if final_f >= 0 and n_lad >= n_tiers + 1:
                # the original final close: ladder full and the final timeframe's RSI at the extreme against the basket
                if side > 0:
                    fin_hit = rsi_now[final_f] <= rsi_os
                else:
                    fin_hit = rsi_now[final_f] >= rsi_ob
            # hedge-on-depth: the basket is judged on its whole P/L, the realised hedge legs included (= profit otherwise)
            pv = profit + part_pnl if hedge_mode == 1 else profit
            if in_flat:
                signal = 3 if side > 0 else 4
                reason = R_WEEKEND
            elif b_sl_on and pv <= -b_sl * basket_units:
                signal = 3 if side > 0 else 4
                reason = R_STOPLOSS
            elif b_sl_abs_on and pv <= -b_sl_abs:
                signal = 3 if side > 0 else 4
                reason = R_STOPLOSS
            elif hedge_ever and pv <= hedge_stop_mult * frozen:
                signal = 3 if side > 0 else 4
                reason = R_HEDGE_STOP
            elif b_target_on and pv > tgt:
""")

# 10. force-close onwards: final close, deep-only time stop, partial closes, hedge legs, the ladder with the new triggers and gates
rep_block("            elif fc_fire:", "                    counters[K_LADDER_EXHAUSTED] += 1", """            elif fc_fire:
                signal = 3 if side > 0 else 4
                reason = R_FORCE if fc_slope else R_RSI_FC
            elif fin_hit:
                signal = 3 if side > 0 else 4
                reason = R_FINAL
            elif max_hold > 0 and (T - basket_open_t) >= max_hold and (n_lad - 1) >= hold_min_adds:
                signal = 3 if side > 0 else 4
                reason = R_TIME
            elif partial_mode == 1 and hedge_mode == 0 and n_lad >= 2 and b_target_on and _leg_profit(
                    pos_side[n_pos - 1], pos_price[n_pos - 1], pos_lots[n_pos - 1], b, a, contract) > b_target * basket_units:
                signal = 9                      # LIFO: the newest add alone has made its own target
            elif partial_mode == 2 and hedge_mode == 0 and n_lad >= 2 and _overlap_ok(
                    pos_side, pos_price, pos_lots, n_pos, b, a, contract):
                if n_lad == 2:
                    signal = 3 if side > 0 else 4   # the pair is the whole basket
                    reason = R_OVERLAP
                else:
                    signal = 10                 # the newest leg pays for the oldest: close both
            elif hedge_mode == 1 and hedged and ((side > 0 and rsi_now[ladder_tf[0]] >= rsi_ob)
                                                 or (side < 0 and rsi_now[ladder_tf[0]] <= rsi_os)):
                signal = 8                      # unwind the hedge leg on the opposite tier-1 RSI extreme
            elif hedge_mode == 1 and (not hedge_ever) and n_tiers > 0 and n_lad >= n_tiers + 1 and profit < 0.0 and (
                    (side > 0 and rsi_now[ladder_tf[0]] < rsi_ob) or (side < 0 and rsi_now[ladder_tf[0]] > rsi_os)):
                # full and under water: freeze it with ONE opposite leg (once per basket; never inside the unwind zone)
                signal = 7
            else:
                cnt = n_lad
                if cnt <= n_tiers:
                    tf_i = ladder_tf[cnt - 1]
                    lv_os = rsi_os
                    lv_ob = rsi_ob
                    if tier_levels:
                        lv_os = tier_lv[0, cnt - 1]
                        lv_ob = tier_lv[1, cnt - 1]
                    add_side = side
                    if hedge_mode == 2:
                        # counter-ladder: the adds go on the other side, released by distance alone
                        add_side = -side
                        hit = True
                    elif ladder_mode == 0:
                        # live: the tier timeframe's RSI is at or beyond the level
                        if side > 0:
                            hit = rsi_now[tf_i] <= lv_os
                        else:
                            hit = rsi_now[tf_i] >= lv_ob
                    elif ladder_mode == 1:
                        # that RSI has been beyond the level since the last fill and has come back inside
                        if side > 0:
                            if rsi_now[tf_i] <= lv_os:
                                ladder_armed = True
                            hit = ladder_armed and rsi_now[tf_i] > lv_os + rsi_exit
                        else:
                            if rsi_now[tf_i] >= lv_ob:
                                ladder_armed = True
                            hit = ladder_armed and rsi_now[tf_i] < lv_ob - rsi_exit
                    elif ladder_mode == 2:
                        # the tier timeframe's MACD vote was not with the basket since the last fill and now is
                        if sgn_m[tf_i] * side <= 0:
                            ladder_armed = True
                        hit = ladder_armed and sgn_m[tf_i] * side > 0
                    elif ladder_mode == 5 or ladder_mode == 6:
                        # the tier timeframe's forming-bar MACD histogram: on the wrong side (5), or back across zero (6)
                        h5 = np.nan
                        if K[tf_i] >= 1:
                            h5, s5 = forming_macd(C, EF, ES, SG, off[tf_i], K[tf_i], b, mf, ms, msig, a_f, a_s, a_sg)
                        if ladder_mode == 5:
                            if side > 0:
                                hit = h5 <= 0.0
                            else:
                                hit = h5 >= 0.0
                        else:
                            if (side > 0 and h5 <= 0.0) or (side < 0 and h5 >= 0.0):
                                ladder_armed = True
                            hit = ladder_armed and ((side > 0 and h5 > 0.0) or (side < 0 and h5 < 0.0))
                    elif ladder_mode == 7:
                        # wait for the turn: the RSI level was reached since the last fill AND the MACD vote turned
                        if (side > 0 and rsi_now[tf_i] <= lv_os) or (side < 0 and rsi_now[tf_i] >= lv_ob):
                            ladder_armed = True
                        if sgn_m[tf_i] * side <= 0:
                            armed2 = True
                        hit = ladder_armed and armed2 and sgn_m[tf_i] * side > 0
                    elif ladder_mode == 8:
                        # a closed-bar indicator series of the tier timeframe (+1 a buy add, -1 a sell add)
                        s8 = tier_ser[cnt - 1]
                        hit = False
                        if s8 >= 0:
                            if sk[s8] == 1:
                                hit = sv[s8] * side > 0.0
                    else:
                        hit = True                      # distance alone decides (3: against, 4: in favour)
                    if hit:
                        ok_gate = add_ok
                        if add_side != side:
                            ok_gate = (open_score < ladder_s) if side > 0 else (open_score > -ladder_s)
                        blk = 0
                        if add_trend_f >= 0:
                            trd = 0
                            if K[add_trend_f] >= 1:
                                sgt2 = SG[off[add_trend_f] + K[add_trend_f] - 1]
                                if sgt2 > 0.0:
                                    trd = 1
                                elif sgt2 < 0.0:
                                    trd = -1
                            if add_side * trd * add_trend_mode <= 0:
                                blk = 1
                        if blk == 0 and aser_on:
                            if sk[SER_ADD] == 0 or (int(sv[SER_ADD]) & (1 if add_side > 0 else 2)) == 0:
                                blk = 2
                        if blk == 0 and abn_on and sk[SER_ABN_REF] == 1 and sk[SER_ABN_THR] == 1 and sv[SER_ABN_REF] > 0.0:
                            r5 = b / sv[SER_ABN_REF] - 1.0
                            if abs(r5) > sv[SER_ABN_THR] and add_side * r5 < 0.0:
                                blk = 3
                        if blk == 0 and add_blk_from >= 0:
                            mod = (tsec % 86400) // 60
                            if add_blk_from < add_blk_to:
                                if mod >= add_blk_from and mod < add_blk_to:
                                    blk = 4
                            elif mod >= add_blk_from or mod < add_blk_to:
                                blk = 4
                        if not ok_gate:
                            counters[K_LADDER_GATED] += 1
                        elif blk != 0:
                            counters[K2_ADD_BLOCK_TREND + blk - 1] += 1
                        else:
                            g_now = b_gap
                            if gap_growth != 1.0:
                                g_now = b_gap * gap_growth ** (cnt - 1)
                            gap_ok = True
                            if hedge_mode == 2:
                                if side > 0:
                                    gap_ok = g_now > 0.0 and (last_ref_b - b) >= g_now
                                else:
                                    gap_ok = g_now > 0.0 and (a - last_ref_a) >= g_now
                            elif ladder_mode == 4:
                                # judged on the quote the basket is valued at (bid for a buy, ask for a sell), so the
                                # last position really is a step in profit and a widening spread alone releases nothing
                                if side > 0:
                                    gap_ok = g_now > 0.0 and (b - last_fill_price) >= g_now
                                else:
                                    gap_ok = g_now > 0.0 and (last_fill_price - a) >= g_now
                            elif g_now > 0.0:
                                if side > 0:
                                    gap_ok = (last_fill_price - a) >= g_now
                                else:
                                    gap_ok = (b - last_fill_price) >= g_now
                            elif ladder_mode == 3:
                                gap_ok = False
                            if ladder_interval > 0 and (T - last_fill_t) < ladder_interval:
                                gap_ok = False
                            if gap_ok:
                                signal = 5 if side > 0 else 6
                                tier = tf_i
                            else:
                                counters[K_LADDER_SPACED] += 1
                else:
                    counters[K_LADDER_EXHAUSTED] += 1""")

# 11. entries: the stop-and-reverse order skips the entry rules; new entry gates
rep("                if brake:\n                    counters[K_BLOCK_BRAKE] += 1\n", """                if rev_now:
                    # a stop-and-reverse order: the entry rules do not apply, only the market can refuse it
                    if brake or in_flat or T < hole_until:
                        ok = False
                        rev_pending = 0
                        counters[K2_REV_DROP] += 1
                    elif closed_arr:
                        counters[K_BLOCK_CLOSED] += 1
                        ok = False
                        extra_wait = open_delay
                    elif arrive < reopen_until:
                        counters[K_BLOCK_REOPEN] += 1
                        ok = False
                        extra_wait = open_delay
                elif brake:
                    counters[K_BLOCK_BRAKE] += 1
""")
rep("                # 2. the order is sent. The live helper sleeps after order_send whatever the broker answers,\n",
    """                elif in_flat:
                    counters[K2_BLOCK_FLAT] += 1
                    ok = False
                elif eser_on and (sk[SER_ENTRY] == 0 or (int(sv[SER_ENTRY]) & (1 if want_side > 0 else 2)) == 0):
                    counters[K2_BLOCK_ESER] += 1
                    ok = False
                elif side_rsi_f >= 0 and ((want_side > 0 and rsi_now[side_rsi_f] >= side_hi)
                                          or (want_side < 0 and rsi_now[side_rsi_f] <= side_lo)):
                    counters[K2_BLOCK_SIDE_RSI] += 1
                    ok = False
                elif gap_f >= 0 and not (K[gap_f] >= 1 and VOL2[off[gap_f] + K[gap_f] - 1] > 0.0):
                    counters[K_BLOCK_NOVOL] += 1
                    ok = False
                elif sizing != 0 and (sk[SER_ATR] == 0 or not (sv[SER_ATR] > 0.0)):
                    counters[K_BLOCK_NOVOL] += 1
                    ok = False
                # 2. the order is sent. The live helper sleeps after order_send whatever the broker answers,
""")
rep("                if ok:\n                    lots = _round2(units * mtqty)\n", """                if ok:
                    u_open = units
                    if rev_now:
                        u_open = rev_units
                    elif sizing == 1:
                        # pre-funded: the largest unit whose full ladder, filled at least one gap apart down to the last
                        # tier and then a further pf_atr x ATR(D1), loses at most pf_risk of the balance
                        g0 = ladder_gap
                        if vol_f >= 0 and gap_vol > 0.0:
                            v0 = VOL[off[vol_f] + K[vol_f] - 1]
                            if vol_cap > 0.0 and v0 * usd_per_price > vol_cap:
                                v0 = vol_cap / usd_per_price
                            g0 = gap_vol * v0
                        if gap_f >= 0 and gap_mult > 0.0:
                            g0 = gap_mult * VOL2[off[gap_f] + K[gap_f] - 1]
                        d_last = 0.0
                        gi = g0
                        for q in range(n_tiers):
                            d_last += gi
                            gi *= gap_growth
                        d_end = d_last + pf_atr * sv[SER_ATR]
                        loss_pu = 0.0
                        dq = 0.0
                        gi = g0
                        for q in range(n_tiers + 1):
                            loss_pu += ladder_mult[q] * (d_end - dq + (a - b))
                            dq += gi
                            gi *= gap_growth
                        loss_pu *= usd_per_price
                        u_open = unit_max
                        if loss_pu > 0.0:
                            u_open = int(math.floor(pf_risk * balance / loss_pu))
                        if u_open > unit_max:
                            u_open = unit_max
                        if u_open < 1:
                            u_open = 1
                    elif sizing == 2:
                        # volatility-targeted: k x balance / (ATR(D1) x contract), rounded
                        u_open = int(math.floor(vt_k * balance / (sv[SER_ATR] * contract) + 0.5))
                        if u_open > unit_max:
                            u_open = unit_max
                        if u_open < 1:
                            u_open = 1
                    lots = _round2(u_open * mtqty)
""")
rep("                        basket_units = units\n", "                        basket_units = u_open\n")
rep("                            fills[n_fills, F_UNITS] = units\n", "                            fills[n_fills, F_UNITS] = u_open\n")
rep("                        counters[K_ENTRIES] += 1\n", """                        counters[K_ENTRIES] += 1
                        pos_side[0] = side
                        n_lad = 1
                        n_opened = 1
                        max_lad = 1
                        part_pnl = 0.0
                        n_hedge = 0
                        hedged = False
                        hedge_ever = False
                        frozen = 0.0
                        armed2 = False
                        last_ref_b = b
                        last_ref_a = a
                        is_rev = rev_now
                        if rev_now:
                            rev_pending = 0
                            counters[K2_REV_OPEN] += 1
                        b_sl_abs_on = stop_pct > 0.0
                        b_sl_abs = stop_pct / 100.0 * balance
                        if gap_f >= 0 and gap_mult > 0.0:
                            b_gap = gap_mult * VOL2[off[gap_f] + K[gap_f] - 1]
""")

# 12. adds: counter-ladder side and margin, bookkeeping
rep("""            elif signal == 5 or signal == 6:
                lots = _round2(ladder_mult[n_pos] * basket_units * mtqty)
                price = fa + slippage if side > 0 else fb - slippage
                need = lots * contract * price / leverage
""", """            elif signal == 5 or signal == 6:
                add_side = -side if hedge_mode == 2 else side
                lots = _round2(ladder_mult[n_lad] * basket_units * mtqty)
                price = fa + slippage if add_side > 0 else fb - slippage
                need = lots * contract * price / leverage
                if hedge_mode == 0:
                    margin_bad = need > equity - used_margin
                else:
                    mb = 0.0
                    msl = 0.0
                    for i in range(n_pos):
                        if pos_side[i] > 0:
                            mb += pos_lots[i] * contract * pos_price[i] / leverage
                        else:
                            msl += pos_lots[i] * contract * pos_price[i] / leverage
                    if add_side > 0:
                        mb += need
                    else:
                        msl += need
                    margin_bad = (mb if mb > msl else msl) > equity
""")
rep("                elif need > equity - used_margin or n_pos >= MAXPOS:\n",
    "                elif margin_bad or n_pos >= MAXPOS:\n")
rep("                    pos_t[n_pos] = T\n                    n_pos += 1\n", """                    pos_t[n_pos] = T
                    pos_side[n_pos] = add_side
                    n_pos += 1
                    n_lad += 1
                    n_opened += 1
                    if n_lad > max_lad:
                        max_lad = n_lad
                    last_ref_b = b
                    last_ref_a = a
                    armed2 = False
""")
rep("                        fills[n_fills, F_SIDE] = side\n                        fills[n_fills, F_LOTS] = lots\n",
    "                        fills[n_fills, F_SIDE] = add_side\n                        fills[n_fills, F_LOTS] = lots\n")

# 13. hedge legs and partial closes
rep("            elif signal == 3 or signal == 4:\n", """            elif signal == 7:
                # hedge-on-depth: one opposite position of the basket's net size (an order like any other)
                if closed_arr:
                    counters[K_BLOCK_CLOSED] += 1
                    extra_wait = open_delay
                elif arrive < reopen_until:
                    counters[K_BLOCK_REOPEN] += 1
                    extra_wait = open_delay
                else:
                    hl = 0.0
                    for i in range(n_pos):
                        if pos_side[i] == side:
                            hl += pos_lots[i]
                        else:
                            hl -= pos_lots[i]
                    hl = _round2(hl)
                    hside = -side
                    price = fa + slippage if hside > 0 else fb - slippage
                    mb = 0.0
                    msl = 0.0
                    for i in range(n_pos):
                        if pos_side[i] > 0:
                            mb += pos_lots[i] * contract * pos_price[i] / leverage
                        else:
                            msl += pos_lots[i] * contract * pos_price[i] / leverage
                    if hside > 0:
                        mb += hl * contract * price / leverage
                    else:
                        msl += hl * contract * price / leverage
                    extra_wait = open_delay
                    if hl <= 0.0 or n_pos >= MAXPOS or (mb if mb > msl else msl) > equity:
                        counters[K_MARGIN_REJECT] += 1
                    else:
                        pos_lots[n_pos] = hl
                        pos_price[n_pos] = price
                        pos_t[n_pos] = T
                        pos_side[n_pos] = hside
                        n_pos += 1
                        if not hedge_ever:
                            frozen = profit
                            hedge_ever = True
                        hedged = True
                        n_hedge += 1
                        n_opened += 1
                        basket_comm += hl * commission
                        counters[K2_HEDGE_OPEN] += 1
                        if n_fills < max_fills:
                            fills[n_fills, F_T] = T
                            fills[n_fills, F_FILL_T] = t_ms[fptr]
                            fills[n_fills, F_ACTION] = ACT_HEDGE
                            fills[n_fills, F_SIDE] = hside
                            fills[n_fills, F_LOTS] = hl
                            fills[n_fills, F_PRICE] = price
                            fills[n_fills, F_PROFIT] = 0.0
                            fills[n_fills, F_BALANCE] = balance
                            fills[n_fills, F_BASKET] = n_baskets
                            fills[n_fills, F_REASON] = 0
                            fills[n_fills, F_UNITS] = basket_units
                            fills[n_fills, F_OPEN_SCORE] = open_score
                            fills[n_fills, F_FC_SCORE] = fc_score
                            fills[n_fills, F_BOOK_SCORE] = book_score
                            fills[n_fills, F_NPOS] = n_pos
                            fills[n_fills, F_BID] = b
                            fills[n_fills, F_ASK] = a
                            fills[n_fills, F_TIER] = -1
                            fills[n_fills, F_BASKET_PROFIT] = profit
                            fills[n_fills, F_POS_OPEN_T] = T
                            fills[n_fills, F_POS_OPEN_PRICE] = price
                            n_fills += 1
                        else:
                            counters[K_FILL_OVERFLOW] += 1

            elif signal == 8 or signal == 9 or signal == 10:
                # partial closes: the hedge leg (8), the newest add (9), the newest and the oldest leg (10)
                if closed_arr:
                    counters[K_BLOCK_CLOSED] += 1
                else:
                    cp_l = fb - slippage
                    cp_s = fa + slippage
                    nclose = 2 if signal == 10 else 1
                    for c in range(nclose):
                        j = n_pos - 1 if c == 0 else 0
                        if pos_side[j] > 0:
                            p = _round2((cp_l - pos_price[j]) * pos_lots[j] * contract)
                        else:
                            p = _round2((pos_price[j] - cp_s) * pos_lots[j] * contract)
                        balance += p
                        part_pnl += p
                        basket_comm += pos_lots[j] * commission
                        if signal != 8:
                            basket_lot_units -= pos_lots[j] / mtqty
                        if n_fills < max_fills:
                            fills[n_fills, F_T] = T
                            fills[n_fills, F_FILL_T] = t_ms[fptr]
                            fills[n_fills, F_ACTION] = ACT_CLOSE
                            fills[n_fills, F_SIDE] = pos_side[j]
                            fills[n_fills, F_LOTS] = pos_lots[j]
                            fills[n_fills, F_PRICE] = cp_l if pos_side[j] > 0 else cp_s
                            fills[n_fills, F_PROFIT] = p
                            fills[n_fills, F_BALANCE] = balance
                            fills[n_fills, F_BASKET] = n_baskets
                            fills[n_fills, F_REASON] = R_UNWIND if signal == 8 else R_PARTIAL
                            fills[n_fills, F_UNITS] = basket_units
                            fills[n_fills, F_OPEN_SCORE] = open_score
                            fills[n_fills, F_FC_SCORE] = fc_score
                            fills[n_fills, F_BOOK_SCORE] = book_score
                            fills[n_fills, F_NPOS] = n_pos - 1
                            fills[n_fills, F_BID] = b
                            fills[n_fills, F_ASK] = a
                            fills[n_fills, F_TIER] = -1
                            fills[n_fills, F_BASKET_PROFIT] = profit
                            fills[n_fills, F_POS_OPEN_T] = pos_t[j]
                            fills[n_fills, F_POS_OPEN_PRICE] = pos_price[j]
                            n_fills += 1
                        else:
                            counters[K_FILL_OVERFLOW] += 1
                        for i in range(j, n_pos - 1):
                            pos_lots[i] = pos_lots[i + 1]
                            pos_price[i] = pos_price[i + 1]
                            pos_t[i] = pos_t[i + 1]
                            pos_side[i] = pos_side[i + 1]
                        n_pos -= 1
                    if signal == 8:
                        hedged = False
                        counters[K2_HEDGE_UNWIND] += 1
                    else:
                        n_lad -= nclose
                        counters[K2_PARTIAL] += 1
                        last_fill_price = pos_price[n_pos - 1]
                        ladder_armed = False
                        armed2 = False
                    extra_wait = open_delay

            elif signal == 3 or signal == 4:
""")

# 14. the close: per-position side, partial P/L, extra basket columns, reversal
rep("""                cprice = fb - slippage if side > 0 else fa + slippage
                realised = 0.0
                tot_lots = 0.0
                wsum = 0.0
                for i in range(n_pos):
                    if side > 0:
                        p = _round2((cprice - pos_price[i]) * pos_lots[i] * contract)
                    else:
                        p = _round2((pos_price[i] - cprice) * pos_lots[i] * contract)
""", """                cprice = fb - slippage if side > 0 else fa + slippage
                cp_l = fb - slippage
                cp_s = fa + slippage
                realised = 0.0
                tot_lots = 0.0
                wsum = 0.0
                for i in range(n_pos):
                    if pos_side[i] > 0:
                        p = _round2((cp_l - pos_price[i]) * pos_lots[i] * contract)
                    else:
                        p = _round2((pos_price[i] - cp_s) * pos_lots[i] * contract)
""")
rep("""                        fills[n_fills, F_ACTION] = ACT_CLOSE
                        fills[n_fills, F_SIDE] = side
                        fills[n_fills, F_LOTS] = pos_lots[i]
                        fills[n_fills, F_PRICE] = cprice
""", """                        fills[n_fills, F_ACTION] = ACT_CLOSE
                        fills[n_fills, F_SIDE] = pos_side[i]
                        fills[n_fills, F_LOTS] = pos_lots[i]
                        fills[n_fills, F_PRICE] = cp_l if pos_side[i] > 0 else cp_s
""")
rep("                basket_comm += tot_lots * commission\n",
    "                basket_comm += tot_lots * commission\n"
    "                real_all = realised + part_pnl if part_pnl != 0.0 else realised\n")
rep("                day_pnl += (realised - basket_comm) / (basket_units if basket_units > 0 else 1)\n",
    "                day_pnl += (real_all - basket_comm) / (basket_units if basket_units > 0 else 1)\n")
rep("""                    baskets[n_baskets, B_PNL] = realised - basket_comm
                    last_lost = (realised - basket_comm) < 0.0
""", """                    baskets[n_baskets, B_PNL] = real_all - basket_comm
                    last_lost = (real_all - basket_comm) < 0.0
""")
rep("                    baskets[n_baskets, B_PROFIT_SEEN] = profit\n", """                    baskets[n_baskets, B_PROFIT_SEEN] = profit
                    baskets[n_baskets, B2_N_OPENED] = n_opened
                    baskets[n_baskets, B2_MAX_LAD] = max_lad
                    baskets[n_baskets, B2_PART_PNL] = part_pnl
                    baskets[n_baskets, B2_N_HEDGE] = n_hedge
                    baskets[n_baskets, B2_IS_REV] = 1.0 if is_rev else 0.0
""")
rep("                elif reason == R_HOLE:\n                    counters[K_CLOSE_HOLE] += 1\n", """                elif reason == R_HOLE:
                    counters[K_CLOSE_HOLE] += 1
                elif reason == R_FINAL:
                    counters[K2_CLOSE_FINAL] += 1
                elif reason == R_WEEKEND:
                    counters[K2_CLOSE_WEEKEND] += 1
                elif reason == R_HEDGE_STOP:
                    counters[K2_CLOSE_HEDGE_STOP] += 1
                elif reason == R_OVERLAP:
                    counters[K2_CLOSE_OVERLAP] += 1
""")
rep("                n_pos = 0\n                side = 0\n                last_close = T\n", """                if rev_on and (not is_rev) and blown == 0 and (reason == R_STOPLOSS or reason == R_FORCE or reason == R_RSI_FC):
                    # stop-and-reverse: the opposite basket goes in at once (one reversal per original basket)
                    rev_pending = -side
                    rev_units = int(math.floor(basket_units * rev_mult + 0.5))
                    if rev_units < 1:
                        rev_units = 1
                    rev_deadline = T + 60000
                n_pos = 0
                n_lad = 0
                hedged = False
                hedge_ever = False
                part_pnl = 0.0
                side = 0
                last_close = T
""")

# 15. mark-to-market at the end, per position side
rep("            if side > 0:\n                open_profit += _round2(", "            if pos_side[i] > 0:\n                open_profit += _round2(")

HEADER = '''"""
Ladder study: a copy of ``engine.kernels.run_kernel`` with the study's new paths (generated by a script that copies
the original function verbatim and applies asserted patches; see ``backtest_results/ladder/BUILD.md``).

Every new path sits behind a slot appended after ``CI_N`` / ``CF_N`` (``CI2_*`` / ``CF2_*``) or a new input, and
is off at its default. With every new setting at its default this kernel computes exactly what ``run_kernel``
computes: the bit-identity check in ``ladder_checks`` compares the fills, baskets, counters and scalars arrays of
both kernels with ``np.array_equal``.

New paths:
  ladder triggers 5 macd_hist, 6 macd_cross, 7 rsi_macd ("wait for the turn"), 8 a closed-bar series per tier;
  per-tier RSI levels; geometric gap growth; a gap measured in another timeframe's volatility; a basket stop as %
  of the balance; a time stop only for deep baskets; break-even and shrinking targets; the original H6 final close
  (ladder full); add gates (MACD-signal trend, closed-bar series, abnormal day, UTC minutes); a weekly flat
  window; closed-bar entry gates; a D1-RSI side rule; stop-and-reverse; hedge-on-depth and a counter-ladder
  (positions carry their own side); LIFO and overlap partial closes; pre-funded and volatility-targeted units.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit

from ..engine.kernels import *  # noqa: F401,F403  (slot / column constants of the original kernel)
from ..engine.kernels import _round2, _rsi_blocks, CI_N, CF_N, K_N, B_N  # noqa: F401

# ── integer config slots appended after CI_N ──
CI2_TIER_LEVELS = CI_N + 0      # 1: per-tier RSI levels (tier_lv) instead of rsi_oversold / rsi_overbought
CI2_GAP_TF = CI_N + 1           # timeframe index whose volatility (VOL2, gap_vol_len) sets the gap (-1 off)
CI2_HOLD_MIN_ADDS = CI_N + 2    # the time stop applies only once the basket has this many adds
CI2_BE_AFTER_ADDS = CI_N + 3    # from this many adds on the target is be_spreads spreads (0 off)
CI2_TARGET_SHRINK = CI_N + 4    # 1: target = max(spread x lots, target x unit / positions)
CI2_FINAL_TF = CI_N + 5         # final close timeframe (ladder full, RSI at the extreme against; -1 off)
CI2_ADD_TREND_TF = CI_N + 6     # adds only with (mode +1) / against (-1) this timeframe's MACD-signal trend (-1 off)
CI2_ADD_TREND_MODE = CI_N + 7
CI2_ADD_BLOCK_FROM = CI_N + 8   # no adds in [from, to) minutes of the UTC day (-1 off)
CI2_ADD_BLOCK_TO = CI_N + 9
CI2_ABN_ON = CI_N + 10          # 1: no adds against today's move on an abnormal day (series SER_ABN_*)
CI2_FLAT_FROM = CI_N + 11       # weekly flat window [from, to) in minutes of the week (Monday 00:00 = 0; -1 off)
CI2_FLAT_TO = CI_N + 12
CI2_SIDE_RSI_TF = CI_N + 13     # entry side rule: this timeframe's RSI >= hi sells only, <= lo buys only (-1 off)
CI2_REVERSE = CI_N + 14         # 1: stop-and-reverse after a stop / force-close
CI2_HEDGE_MODE = CI_N + 15      # 0 off, 1 hedge-on-depth, 2 counter-ladder
CI2_PARTIAL = CI_N + 16         # 0 off, 1 LIFO, 2 overlap
CI2_SIZING = CI_N + 17          # 0 the bot's unit rule, 1 pre-funded, 2 volatility-targeted
CI2_N = CI_N + 18

# ── float config slots appended after CF_N ──
CF2_GAP_MULT = CF_N + 0
CF2_GAP_GROWTH = CF_N + 1       # add n needs gap x growth^(n-1) (1.0 = the same gap)
CF2_STOP_PCT = CF_N + 2         # basket stop at this % of the balance when the basket opened (0 off)
CF2_BE_SPREADS = CF_N + 3
CF2_SIDE_RSI_HI = CF_N + 4
CF2_SIDE_RSI_LO = CF_N + 5
CF2_REVERSE_MULT = CF_N + 6
CF2_HEDGE_STOP_MULT = CF_N + 7  # hedged basket: net stop at this multiple of the loss frozen by the first hedge
CF2_PF_RISK = CF_N + 8
CF2_PF_ATR_MULT = CF_N + 9
CF2_VT_K = CF_N + 10
CF2_N = CF_N + 11

# ── packed closed-bar series (ladder_ind): fixed slots, then one per trigger timeframe ──
SER_ENTRY = 0      # entry mask: bit 0 buys allowed, bit 1 sells allowed
SER_ADD = 1        # add mask, same bits
SER_ATR = 2        # ATR(D1) in price units (sizing)
SER_ABN_REF = 3    # the last D1 close (abnormal-day rule)
SER_ABN_THR = 4    # its threshold: mult x the mean |D1 return| (a fraction)
SER_TRIG0 = 5

# ── new reasons, actions, counters, basket columns ──
R_WEEKEND = 11
R_FINAL = 12
R_HEDGE_STOP = 13
R_PARTIAL = 14
R_UNWIND = 15
R_OVERLAP = 16
ACT_HEDGE = 4

K2_REV_OPEN = K_N + 0
K2_REV_DROP = K_N + 1
K2_HEDGE_OPEN = K_N + 2
K2_HEDGE_UNWIND = K_N + 3
K2_PARTIAL = K_N + 4
K2_CLOSE_FINAL = K_N + 5
K2_CLOSE_WEEKEND = K_N + 6
K2_CLOSE_HEDGE_STOP = K_N + 7
K2_BLOCK_FLAT = K_N + 8
K2_BLOCK_ESER = K_N + 9
K2_BLOCK_SIDE_RSI = K_N + 10
K2_ADD_BLOCK_TREND = K_N + 11
K2_ADD_BLOCK_SER = K_N + 12
K2_ADD_BLOCK_ABN = K_N + 13
K2_ADD_BLOCK_HOURS = K_N + 14
K2_CLOSE_OVERLAP = K_N + 15
K2_N = K_N + 16

B2_N_OPENED = B_N + 0     # positions opened in the basket (entry, adds, hedge legs)
B2_MAX_LAD = B_N + 1      # most ladder positions held at once
B2_PART_PNL = B_N + 2     # realised by partial closes and hedge unwinds (included in B_PNL)
B2_N_HEDGE = B_N + 3
B2_IS_REV = B_N + 4       # 1: opened by stop-and-reverse
B_N2 = B_N + 5


@njit(cache=True)
def _leg_profit(ps, price, lots, b, a, contract):
    """Floating P/L of one position as positions_get() reports it."""
    if ps > 0:
        return _round2((b - price) * lots * contract)
    return _round2((price - a) * lots * contract)


@njit(cache=True)
def _overlap_ok(pos_side, pos_price, pos_lots, n_pos, b, a, contract):
    """The newest leg's profit covers the oldest leg's loss plus one spread on both."""
    p_old = _leg_profit(pos_side[0], pos_price[0], pos_lots[0], b, a, contract)
    if p_old >= 0.0:
        return False
    p_new = _leg_profit(pos_side[n_pos - 1], pos_price[n_pos - 1], pos_lots[n_pos - 1], b, a, contract)
    cost = (a - b) * (pos_lots[0] + pos_lots[n_pos - 1]) * contract
    return p_new >= -p_old + cost


'''
out = REPO / "backtesting/research/ladder_kernels.py"
out.write_text(HEADER + body)
print("written", out, len((HEADER + body).splitlines()), "lines")
