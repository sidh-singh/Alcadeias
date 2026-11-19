# The frozen level table (PREREG_LADDER.md section 2.2), as the runner implements it

| Dimension | Code | Level |
|---|---|---|
| ENTRY | E1 | {H4,M5}, v3.9.2 force-close and agreement |
| ENTRY | E2 | pre-v3.9.0: {H4,M5}, fc {M15:4,H1:3,H4:2,D1:1}, force_close_s 12, entry_agree_s 0 |
| ENTRY | E3 | {H1,M15,D1}, entry_s 2 |
| ENTRY | E4 | {H1,M15,D1}, entry_s 4 |
| ENTRY | E5 | {H4,M5,D1}, entry_s 2 |
| ENTRY | E6 | {H4,M5,D1}, entry_s 4 |
| ENTRY | E7 | {H1} alone |
| ENTRY | E8 | {H4,H1,M15}, entry_s 4 |
| ENTRY | E9 | RSI-only votes {H1,M15} |
| ENTRY | E10 | entry_agree_s 0 |
| CONFIRM | C1 | EMA200(D1) side |
| CONFIRM | C2 | EMA50(H4) side |
| CONFIRM | C3 | Supertrend(10,3) H4 side |
| CONFIRM | C4 | ADX(14,H4) < 25 |
| CONFIRM | C5 | ADX(14,H4) >= 25: +DI/-DI side only |
| CONFIRM | C6 | Stochastic(14,3,3) H1 <= 30 buys / >= 70 sells |
| CONFIRM | C7 | CCI(20) H1 <= -100 buys / >= 100 sells |
| CONFIRM | C8 | Bollinger %B(20,2) H1 <= 0.2 buys / >= 0.8 sells |
| CONFIRM | C9 | Donchian(20) H4 breakout side |
| CONFIRM | C10 | variance ratio VR(4) < 1 on 100 H1 bars |
| CONFIRM | C11 | D1 MACD-signal trend |
| SIDE | S1 | entries with the H4 trend |
| SIDE | S2 | entries against the H4 trend |
| SIDE | S3 | entries with the D1 trend |
| SIDE | S4 | entries against the D1 trend |
| SIDE | S5 | D1 RSI reversal (>= 70 sells only, <= 30 buys only) |
| SIDE | S6 | stop-and-reverse at the stop / force-close, same size |
| SIDE | S7 | stop-and-reverse, entry size x 2 |
| SIDE | S8 | hedge-on-depth |
| SIDE | S9 | counter-ladder |
| FC | FC1 | force-close {H1:1} |
| FC | FC2 | force-close {H4:1} |
| FC | FC3 | force-close {D1:1} |
| FC | FC4 | force-close off |
| FC | FC5 | owner's RSI force-close (H1 and H4) |
| FC | FC6 | H6 RSI final close when the ladder is full |
| TARGET | TG1 | $0.5 per unit |
| TARGET | TG2 | $2 per unit |
| TARGET | TG3 | $5 per unit |
| TARGET | TG4 | $10 per unit |
| TARGET | TG5 | target 2 vol units |
| TARGET | TG6 | target 4 vol units |
| TARGET | TG7 | target 8 vol units |
| TARGET | TG8 | break-even + one spread once depth >= 3 |
| TARGET | TG9 | target_0 / positions (never below one spread) |
| STOP | ST1 | stop 4 vol units |
| STOP | ST2 | stop 8 vol units |
| STOP | ST3 | stop 12 vol units |
| STOP | ST4 | basket stop 10% of the balance |
| STOP | ST5 | basket stop 20% of the balance |
| STOP | ST6 | basket stop 30% of the balance |
| TIME | TM1 | time stop 24 h |
| TIME | TM2 | time stop 72 h |
| TIME | TM3 | time stop 168 h |
| TIME | TM4 | time stop 24 h once depth >= 3 |
| TIERS | T1 | tiers T1 ['M5', 'M15', 'H1'] |
| TIERS | T2 | tiers T2 ['M1', 'M5', 'M15'] |
| TIERS | T3 | tiers T3 ['M5', 'M15', 'H1', 'H4', 'D1'] |
| TIERS | T4 | tiers T4 ['M15', 'H1', 'H4', 'D1', 'W1'] |
| TIERS | T5 | tiers T5 ['M1', 'M5', 'M15', 'H1', 'H4', 'D1'] |
| TIERS | T6 | tiers T6 ['M1', 'M5', 'M15', 'H1', 'H4', 'D1', 'W1'] |
| TIERS | T7 | tiers T7 ['H1', 'H4', 'D1'] |
| TIERS | T8 | tiers T8 ['M5', 'M5', 'M5', 'M5', 'M5'] |
| TIERS | T9 | tiers T9 ['M15', 'M15', 'M15', 'M15', 'M15'] |
| TIERS | T10 | tiers T10 ['H1', 'H1', 'H1', 'H1', 'H1'] |
| TIERS | T11 | tiers T11 ['H4', 'H4', 'H4', 'H4', 'H4'] |
| GRAN | T12 | tiers T12 ['M2', 'M4', 'M6', 'M10', 'M20'] |
| GRAN | T13 | tiers T13 ['M10', 'M20', 'H2', 'H3', 'H6'] |
| GRAN | T14 | tiers T14 ['M30', 'H2', 'H3', 'H6', 'H8', 'H12'] |
| GRAN | T15 | tiers T15 ['M1', 'M3', 'M5', 'M10', 'M15', 'M30', 'H1', 'H2', 'H4'] |
| GRAN | T16 | tiers T16 ['M6', 'M12', 'M20', 'H3', 'H8'] |
| DEPTH | D1 | max_adds 1 |
| DEPTH | D2 | max_adds 2 |
| DEPTH | D3 | max_adds 3 |
| DEPTH | D5 | max_adds 5 |
| DEPTH | D8 | max_adds 8 |
| DEPTH | D12 | max_adds 12 |
| SIZE | flat | size flat |
| SIZE | plus1 | size plus1 |
| SIZE | double | size double |
| SIZE | fibo | size fibo |
| LEVEL | LV20 | RSI 20/80 |
| LEVEL | LV25 | RSI 25/75 |
| LEVEL | LV30 | RSI 30/70 |
| LEVEL | LV40 | RSI 40/60 |
| LEVEL | LV45 | RSI 45/55 |
| LEVEL | LVS | per tier stricter when deeper (35, 32, 29, ...) |
| LEVEL | LVL | per tier looser when deeper (35, 38, 41, ...) |
| TRIG-MACD | M1 | MACD turn (macd_turn) |
| TRIG-MACD | M2 | MACD histogram on the wrong side, forming bar |
| TRIG-MACD | M3 | MACD signal-line cross back, forming bar |
| TRIG-MACD | M4 | RSI level and MACD turn (wait for the turn) |
| TRIG-3RD | X-stoch | closed-bar stoch {'ind': 'stoch', 'n': 14, 'smooth': 3, 'lo': 20, 'hi': 80} |
| TRIG-3RD | X-willr | closed-bar willr {'ind': 'willr', 'n': 14, 'lo': -80, 'hi': -20} |
| TRIG-3RD | X-cci | closed-bar cci {'ind': 'cci', 'n': 20, 'lo': -100, 'hi': 100} |
| TRIG-3RD | X-bb | closed-bar bb {'ind': 'bb', 'n': 20, 'k': 2.0, 'lo': 0.0, 'hi': 1.0} |
| TRIG-3RD | X-emadist | closed-bar emadist {'ind': 'emadist', 'n': 20, 'atr': 14, 'lo': -2.0, 'hi': 2.0} |
| TRIG-3RD | X-rsi2 | closed-bar rsi2 {'ind': 'rsi', 'n': 2, 'lo': 10, 'hi': 90} |
| TRIG-3RD | X-rsicross | RSI cross-back (rsi_cross) |
| TRIG-3RD | X-pricestep | price step 1 vol unit (price_step) |
| GAP | G0.5 | gap 0.5 vol units |
| GAP | G1 | gap 1 vol unit |
| GAP | G2 | gap 2 vol units |
| GAP | Ggeo1.5 | gap 1 vol unit x 1.5^(n-1) |
| GAP | Ggeo2 | gap 1 vol unit x 2^(n-1) |
| GAP | GD1 | gap 0.15 D1 vol units (vol_len 14) |
| GAP | Gint300 | 300 s between fills |
| GATE | GT1 | ladder_s off |
| GATE | GT2 | adds only with the H1 trend |
| GATE | GT3 | adds only with the H4 trend |
| GATE | GT4 | adds only on the EMA200(D1) side |
| GATE | GT5 | no adds while ADX(14,H1) > 30 |
| GATE | GT6 | abnormal-day pause for adds |
| GATE | GT7 | no adds 20:30-22:30 UTC |
| GATE | GT8 | flat Friday 20:00 UTC, no new basket until Monday 01:00 |
| GATE | GT9 | no new basket while ATR(H4) > its 100-day 90th percentile |
| SIZING | Z1 | pre-funded unit (30% of the balance, 1.5 ATR(D1)) |
| SIZING | Z2 | volatility-targeted unit |
| SIZING | Z3 | fixed_units 1 |
| PARTIAL | P1 | LIFO: close the newest add at its own target |
| PARTIAL | P2 | overlap close (newest pays for oldest) |
| CONTROL | AM | anti-martingale: adds to winners 0.5 vol units, <= 3, 2 vol-unit trailing exit |
