# TradeIQ's RSI replacements: the video's claims (PREREG 9)

Written by `python -B -m backtesting.research.tradeiq claims` on 27 Nov 2026 23:52 UTC. Each claim of the video is split into the parts it states; each part is counted on the rows it is about, per symbol (DEVIATIONS 31). **The verdict is DEVIATIONS 31's: a part holds on a symbol when it holds in Development and in Validation, does not hold when it fails in both, and is mixed otherwise.** The hold-out (2024-07-01 to the data end) is a third window the selection never saw; its counts, by the same code, are for information (DEVIATIONS 37) and do not change a verdict. "Most" = more than half; "every" = all; "about half" = a median trade ratio in [0.375, 0.625]; "far fewer" = a median ratio of at most 0.5; a win = strictly more net profit at x1.0 than the RSI variant of the same row. Per 0.01 lot after Exness costs.

## The verdicts

| Claim | Part | Symbol | Development | Validation | Verdict | Hold-out (information) | In the hold-out | Note |
|---|---|---|---|---|---|---|---|---|
| 1 | half of 8 alternatives could not beat the RSI | both |  |  | **cannot be tested** |  | cannot be tested | the other four alternatives of the video are not in the grid |
| 1 | QQE beats the RSI in most of its pairs | Gold (XAUUSDm) | 31/48 | 17/48 | **mixed** | 22/48 | does not hold |  |
| 1 | QQE beats the RSI in most of its pairs | BTC (BTCUSDm) | 22/48 | 46/48 | **mixed** | 19/48 | does not hold |  |
| 1 | TSI beats the RSI in most of its pairs | Gold (XAUUSDm) | 40/54 | 51/54 | **holds** | 47/54 | holds |  |
| 1 | TSI beats the RSI in most of its pairs | BTC (BTCUSDm) | 40/54 | 47/54 | **holds** | 23/54 | does not hold |  |
| 1 | VWRSI beats the RSI in most of its pairs | Gold (XAUUSDm) | 38/54 | 30/54 | **holds** | 47/54 | holds |  |
| 1 | VWRSI beats the RSI in most of its pairs | BTC (BTCUSDm) | 29/54 | 16/54 | **mixed** | 18/54 | does not hold |  |
| 1 | LaRSI beats the RSI in most of its pairs | Gold (XAUUSDm) | 36/54 | 26/54 | **mixed** | 38/54 | holds |  |
| 1 | LaRSI beats the RSI in most of its pairs | BTC (BTCUSDm) | 37/54 | 31/54 | **holds** | 25/54 | does not hold |  |
| 1 | VWRSI-RV beats the RSI in most of its pairs | BTC (BTCUSDm) | 44/54 | 15/54 | **mixed** | 28/54 | holds |  |
| 2 | QQE takes fewer trades than the RSI in every pair | Gold (XAUUSDm) | 48/48 | 48/48 | **holds** | 48/48 | holds |  |
| 2 | QQE takes fewer trades than the RSI in every pair | BTC (BTCUSDm) | 48/48 | 48/48 | **holds** | 48/48 | holds |  |
| 2 | QQE beats the RSI in most pairs | Gold (XAUUSDm) | 31/48 | 17/48 | **mixed** | 22/48 | does not hold |  |
| 2 | QQE beats the RSI in most pairs | BTC (BTCUSDm) | 22/48 | 46/48 | **mixed** | 19/48 | does not hold |  |
| 2 | QQE has a shorter longest losing streak in most pairs | Gold (XAUUSDm) | 34/48 | 40/48 | **holds** | 42/48 | holds |  |
| 2 | QQE has a shorter longest losing streak in most pairs | BTC (BTCUSDm) | 42/48 | 48/48 | **holds** | 45/48 | holds |  |
| 3 | the zero line works: TSI R1 / R2 with F0 make money in most rows | Gold (XAUUSDm) | 8/12 | 10/12 | **holds** | 12/12 | holds |  |
| 3 | the zero line works: TSI R1 / R2 with F0 make money in most rows | BTC (BTCUSDm) | 8/12 | 10/12 | **holds** | 8/12 | holds |  |
| 3 | the signal line is a coin flip: the zero line (R1 F0) beats it in most pairs | Gold (XAUUSDm) | 2/6 | 3/6 | **does not hold** | 4/6 | holds | signal-line rows with net > 0: 4/6 (dev), 4/6 (val); hold-out: signal-line rows with net > 0: 6/6 |
| 3 | the signal line is a coin flip: the zero line (R1 F0) beats it in most pairs | BTC (BTCUSDm) | 6/6 | 5/6 | **holds** | 4/6 | holds | signal-line rows with net > 0: 1/6 (dev), 0/6 (val); hold-out: signal-line rows with net > 0: 4/6 |
| 3 | TSI takes about half the RSI's trades (median ratio in [0.375, 0.625]) | Gold (XAUUSDm) | 0.60 | 0.58 | **holds** | 0.49 | holds |  |
| 3 | TSI takes about half the RSI's trades (median ratio in [0.375, 0.625]) | BTC (BTCUSDm) | 0.57 | 0.52 | **holds** | 0.61 | holds |  |
| 4 | VWRSI's 20 / 80 reversals are no better than the RSI's (it wins at most half) | Gold (XAUUSDm) | 6/6 | 4/6 | **does not hold** | 3/6 | holds |  |
| 4 | VWRSI's 20 / 80 reversals are no better than the RSI's (it wins at most half) | BTC (BTCUSDm) | 1/6 | 2/6 | **holds** | 4/6 | does not hold |  |
| 4 | the VWRSI's trend rule on crypto; it needs real volume | Gold (XAUUSDm) |  |  | **cannot be tested** |  | cannot be tested | not a crypto market: the gold CFD has tick volume only |
| 4 | VWRSI's trend rule beats the RSI on every crypto timeframe (most pairs on each) | BTC (BTCUSDm) | 1H 0/20, 4H 16/16, 1D 12/12 | 1H 0/20, 4H 14/16, 1D 0/12 | **does not hold** | 1H 0/20, 4H 14/16, 1D 0/12 | does not hold |  |
| 4 | VWRSI-RV's trend rule beats the RSI on every crypto timeframe (most pairs on each) | BTC (BTCUSDm) | 1H 20/20, 4H 12/16, 1D 12/12 | 1H 0/20, 4H 14/16, 1D 0/12 | **mixed** | 1H 17/20, 4H 0/16, 1D 6/12 | does not hold |  |
| 4 | VWRSI-RV's 20 / 80 reversals are no better than the RSI's (it wins at most half) | BTC (BTCUSDm) | 0/6 | 1/6 | **holds** | 5/6 | does not hold |  |
| 4 | the VWRSI needs real volume: on Binance volume it beats tick volume in most rows | BTC (BTCUSDm) | 60/78 | 11/78 | **mixed** | 55/78 | holds |  |
| 5 | LaRSI beats the RSI in most pairs on every timeframe | Gold (XAUUSDm) | 1H 22/22, 4H 2/18, 1D 12/14 | 1H 7/22, 4H 16/18, 1D 3/14 | **does not hold** | 1H 22/22, 4H 2/18, 1D 14/14 | does not hold |  |
| 5 | LaRSI beats the RSI in most pairs on every timeframe | BTC (BTCUSDm) | 1H 20/22, 4H 3/18, 1D 14/14 | 1H 12/22, 4H 17/18, 1D 2/14 | **does not hold** | 1H 18/22, 4H 2/18, 1D 5/14 | does not hold |  |
| 5 | LaRSI takes far fewer trades than the RSI (median ratio <= 0.5) | Gold (XAUUSDm) | 0.42 | 0.41 | **holds** | 0.33 | holds |  |
| 5 | LaRSI takes far fewer trades than the RSI (median ratio <= 0.5) | BTC (BTCUSDm) | 0.42 | 0.34 | **holds** | 0.44 | holds |  |
| 5 | on 1H LaRSI on its own mostly did not make money (net > 0 in at most half) | Gold (XAUUSDm) | 6/6 | 4/6 | **does not hold** | 6/6 | does not hold |  |
| 5 | on 1H LaRSI on its own mostly did not make money (net > 0 in at most half) | BTC (BTCUSDm) | 0/6 | 2/6 | **holds** | 1/6 | holds |  |
| 5 | 4H and 1D are where LaRSI shines (a larger share of rows with net > 0 than on 1H) | Gold (XAUUSDm) | 1H 100%, 4H 44%, 1D 71% | 1H 82%, 4H 94%, 1D 71% | **does not hold** | 1H 100%, 4H 100%, 1D 100% | does not hold |  |
| 5 | 4H and 1D are where LaRSI shines (a larger share of rows with net > 0 than on 1H) | BTC (BTCUSDm) | 1H 18%, 4H 83%, 1D 100% | 1H 64%, 4H 100%, 1D 100% | **holds** | 1H 45%, 4H 22%, 1D 86% | does not hold |  |
| 5 | pair LaRSI with a trend filter: TSI > 0 (F3) beats no filter in most pairs | Gold (XAUUSDm) | 4/12 | 3/12 | **does not hold** | 4/12 | does not hold |  |
| 5 | pair LaRSI with a trend filter: TSI > 0 (F3) beats no filter in most pairs | BTC (BTCUSDm) | 10/12 | 5/12 | **mixed** | 7/12 | holds |  |
| 5 | pair LaRSI with a trend filter: MA200 (F1, F2) beats no filter in most pairs | Gold (XAUUSDm) | 1/24 | 13/24 | **mixed** | 13/24 | holds |  |
| 5 | pair LaRSI with a trend filter: MA200 (F1, F2) beats no filter in most pairs | BTC (BTCUSDm) | 18/24 | 15/24 | **holds** | 19/24 | holds |  |
| 6 | the four worked best on 4H and 1D (1H has the lowest share of rows with net > 0) | Gold (XAUUSDm) | 1H 60%, 4H 69%, 1D 56% | 1H 75%, 4H 81%, 1D 69% | **does not hold** | 1H 97%, 4H 97%, 1D 83% | does not hold |  |
| 6 | the four worked best on 4H and 1D (1H has the lowest share of rows with net > 0) | BTC (BTCUSDm) | 1H 8%, 4H 81%, 1D 88% | 1H 44%, 4H 76%, 1D 91% | **holds** | 1H 35%, 4H 61%, 1D 87% | holds |  |
| 6 | on 1H even the best struggled (the best 1H row earns less than the best 4H and the best 1D row) | Gold (XAUUSDm) | 1H +733, 4H +543, 1D +1,330 | 1H +353, 4H +419, 1D +525 | **mixed** | 1H +2,987, 4H +3,183, 1D +2,964 | does not hold |  |
| 6 | on 1H even the best struggled (the best 1H row earns less than the best 4H and the best 1D row) | BTC (BTCUSDm) | 1H +142, 4H +517, 1D +734 | 1H +188, 4H +365, 1D +404 | **holds** | 1H +444, 4H +505, 1D +573 | holds |  |

## In short

**Claim 1.** "Half of 8 alternatives could not beat the RSI; these four did, on most markets."

- half of 8 alternatives could not beat the RSI (both): **cannot be tested** (the other four alternatives of the video are not in the grid).
- QQE beats the RSI in most of its pairs (Gold (XAUUSDm)): **mixed**; in the hold-out: does not hold.
- QQE beats the RSI in most of its pairs (BTC (BTCUSDm)): **mixed**; in the hold-out: does not hold.
- TSI beats the RSI in most of its pairs (Gold (XAUUSDm)): **holds**; in the hold-out: holds.
- TSI beats the RSI in most of its pairs (BTC (BTCUSDm)): **holds**; in the hold-out: does not hold.
- VWRSI beats the RSI in most of its pairs (Gold (XAUUSDm)): **holds**; in the hold-out: holds.
- VWRSI beats the RSI in most of its pairs (BTC (BTCUSDm)): **mixed**; in the hold-out: does not hold.
- LaRSI beats the RSI in most of its pairs (Gold (XAUUSDm)): **mixed**; in the hold-out: holds.
- LaRSI beats the RSI in most of its pairs (BTC (BTCUSDm)): **holds**; in the hold-out: does not hold.
- VWRSI-RV beats the RSI in most of its pairs (BTC (BTCUSDm)): **mixed**; in the hold-out: holds.

**Claim 2.** "QQE MOD takes fewer trades than the RSI on every market and timeframe, and beats it on most, with shorter losing streaks."

- QQE takes fewer trades than the RSI in every pair (Gold (XAUUSDm)): **holds**; in the hold-out: holds.
- QQE takes fewer trades than the RSI in every pair (BTC (BTCUSDm)): **holds**; in the hold-out: holds.
- QQE beats the RSI in most pairs (Gold (XAUUSDm)): **mixed**; in the hold-out: does not hold.
- QQE beats the RSI in most pairs (BTC (BTCUSDm)): **mixed**; in the hold-out: does not hold.
- QQE has a shorter longest losing streak in most pairs (Gold (XAUUSDm)): **holds**; in the hold-out: holds.
- QQE has a shorter longest losing streak in most pairs (BTC (BTCUSDm)): **holds**; in the hold-out: holds.

**Claim 3.** "TSI: the zero line works, the signal line is a coin flip; it beats the RSI on most markets with about half the trades."

- the zero line works: TSI R1 / R2 with F0 make money in most rows (Gold (XAUUSDm)): **holds**; in the hold-out: holds.
- the zero line works: TSI R1 / R2 with F0 make money in most rows (BTC (BTCUSDm)): **holds**; in the hold-out: holds.
- the signal line is a coin flip: the zero line (R1 F0) beats it in most pairs (Gold (XAUUSDm)): **does not hold**; in the hold-out: holds.
- the signal line is a coin flip: the zero line (R1 F0) beats it in most pairs (BTC (BTCUSDm)): **holds**; in the hold-out: holds.
- TSI takes about half the RSI's trades (median ratio in [0.375, 0.625]) (Gold (XAUUSDm)): **holds**; in the hold-out: holds.
- TSI takes about half the RSI's trades (median ratio in [0.375, 0.625]) (BTC (BTCUSDm)): **holds**; in the hold-out: holds.

**Claim 4.** "VWRSI: the trend rule (side of 50) beats the RSI on every crypto market and timeframe; its 20 / 80 reversals are no better than the RSI's; it needs real volume (crypto), not tick volume."

- VWRSI's 20 / 80 reversals are no better than the RSI's (it wins at most half) (Gold (XAUUSDm)): **does not hold**; in the hold-out: holds.
- VWRSI's 20 / 80 reversals are no better than the RSI's (it wins at most half) (BTC (BTCUSDm)): **holds**; in the hold-out: does not hold.
- the VWRSI's trend rule on crypto; it needs real volume (Gold (XAUUSDm)): **cannot be tested** (not a crypto market: the gold CFD has tick volume only).
- VWRSI's trend rule beats the RSI on every crypto timeframe (most pairs on each) (BTC (BTCUSDm)): **does not hold**; in the hold-out: does not hold.
- VWRSI-RV's trend rule beats the RSI on every crypto timeframe (most pairs on each) (BTC (BTCUSDm)): **mixed**; in the hold-out: does not hold.
- VWRSI-RV's 20 / 80 reversals are no better than the RSI's (it wins at most half) (BTC (BTCUSDm)): **holds**; in the hold-out: does not hold.
- the VWRSI needs real volume: on Binance volume it beats tick volume in most rows (BTC (BTCUSDm)): **mixed**; in the hold-out: holds.

**Claim 5.** "Laguerre RSI: beats the RSI on most markets on every timeframe with far fewer trades; on 1H it mostly still did not make money on its own; 4H and 1D are where it works; pair it with a trend filter (TSI > 0 or MA200)."

- LaRSI beats the RSI in most pairs on every timeframe (Gold (XAUUSDm)): **does not hold**; in the hold-out: does not hold.
- LaRSI beats the RSI in most pairs on every timeframe (BTC (BTCUSDm)): **does not hold**; in the hold-out: does not hold.
- LaRSI takes far fewer trades than the RSI (median ratio <= 0.5) (Gold (XAUUSDm)): **holds**; in the hold-out: holds.
- LaRSI takes far fewer trades than the RSI (median ratio <= 0.5) (BTC (BTCUSDm)): **holds**; in the hold-out: holds.
- on 1H LaRSI on its own mostly did not make money (net > 0 in at most half) (Gold (XAUUSDm)): **does not hold**; in the hold-out: does not hold.
- on 1H LaRSI on its own mostly did not make money (net > 0 in at most half) (BTC (BTCUSDm)): **holds**; in the hold-out: holds.
- 4H and 1D are where LaRSI shines (a larger share of rows with net > 0 than on 1H) (Gold (XAUUSDm)): **does not hold**; in the hold-out: does not hold.
- 4H and 1D are where LaRSI shines (a larger share of rows with net > 0 than on 1H) (BTC (BTCUSDm)): **holds**; in the hold-out: does not hold.
- pair LaRSI with a trend filter: TSI > 0 (F3) beats no filter in most pairs (Gold (XAUUSDm)): **does not hold**; in the hold-out: does not hold.
- pair LaRSI with a trend filter: TSI > 0 (F3) beats no filter in most pairs (BTC (BTCUSDm)): **mixed**; in the hold-out: holds.
- pair LaRSI with a trend filter: MA200 (F1, F2) beats no filter in most pairs (Gold (XAUUSDm)): **mixed**; in the hold-out: holds.
- pair LaRSI with a trend filter: MA200 (F1, F2) beats no filter in most pairs (BTC (BTCUSDm)): **holds**; in the hold-out: holds.

**Claim 6.** "All four worked best on 4H and 1D; on 1H even the best struggled."

- the four worked best on 4H and 1D (1H has the lowest share of rows with net > 0) (Gold (XAUUSDm)): **does not hold**; in the hold-out: does not hold.
- the four worked best on 4H and 1D (1H has the lowest share of rows with net > 0) (BTC (BTCUSDm)): **holds**; in the hold-out: holds.
- on 1H even the best struggled (the best 1H row earns less than the best 4H and the best 1D row) (Gold (XAUUSDm)): **mixed**; in the hold-out: does not hold.
- on 1H even the best struggled (the best 1H row earns less than the best 4H and the best 1D row) (BTC (BTCUSDm)): **holds**; in the hold-out: holds.

Count of the parts by verdict (DEVIATIONS 31):

| Symbol | holds | does not hold | mixed |
|---|---|---|---|
| Gold (XAUUSDm) | 7 | 7 | 5 |
| BTC (BTCUSDm) | 15 | 2 | 7 |

Cannot be tested: 2 part(s) (see the notes).

## Files

`claims.csv` (Development and Validation, written by `select`), `claims_all.csv` (the same with the hold-out's evidence), `results_dev_val.csv`, `results_holdout.csv`.
