# Entry filters on the bots' designs: the finalists (frozen)

Written 2026-11-28 16:30 UTC, before T1, T2 or the forward window was computed for anything. The sha256 of this file is in `FINALISTS.md.sha256`.

| Design | Finalist | Rule | Development score | Confirmed score |
|---|---|---|---|---|
| Gold V3-lite | none | no filter improved it | | |
| Gold Top 1 | `LGATE200-H1&QQE-H4` | LGATE200-H1: LGATE200 on closed H1 bars AND QQE-H4: QQE on closed H4 bars | 6.812 | 6.428 |
| Gold Top 1 | `LGATE200-H1` | LGATE200-H1: LGATE200 on closed H1 bars | 6.752 | 6.341 |
| Gold Top 2 | `SLOPE100-D1` | SLOPE100-D1: SLOPE(100) on closed D1 bars | 9.420 | 9.613 |
| Gold Top 2 | `MSD-D1` | MSD-D1: MSD on closed D1 bars | 9.274 | 9.312 |
| BTC Top 2 | `QQE-H4` | QQE-H4: QQE on closed H4 bars | 4.840 | 4.765 |
| BTC Turtle System 2 + bot votes | `SGATE200-D1&LARSI-H1` | SGATE200-D1: SGATE200 on closed D1 bars AND LARSI-H1: LARSI on closed H1 bars | 4.608 |  |
| BTC Turtle System 2 + bot votes | `SGATE200-D1` | SGATE200-D1: SGATE200 on closed D1 bars | 4.566 |  |

Code (git blob ids):

- `backtesting/research/bot_filters.py`: c764f3950866aff031cff434a639911906c555f9
- `backtesting/research/tradeiq_ind.py`: 2a6483a415eb50b9b5e067fe899f4922e085ce9f
- `backtesting/research/tradeiq_market.py`: dc784854b60c0bcb4b01b189b8a7cd5516267b04
- `backtesting/research/external.py`: 5f037a44b07e954cd0a857e677914eec42205c90
- `backtesting/research/final10.py`: 5e675ee0774ef6f7a22bca7794571503d3ee4b59
- `backtesting/engine/fast.py`: e1af1565877d0267b38a9f39c62821d115a1f3ff
- `backtesting/engine/kernels.py`: dcd7b4ed4d28ca85b47f2314e732426c840a87e3
- `backtesting/research/tradeiq2_ind_ribbon.py`: 100379b349c9d11d5f4a11f094ff1783c1ecaac8
- `backtesting/research/tradeiq2_ind_msd.py`: 6dc2ce35e979fd762b8764480fc4a8364b9b4738
- `backtesting/research/tradeiq2_ind_ha.py`: e9d1844fdbfd5c62d75eb86a525425ce50497b73
