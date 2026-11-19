# Hand traces: each new path switched on (gold, 2023-02-13 to 2023-05-13, raw ticks, loop timing seed 1)

Every fill of the quarter is checked against the path's rule with values recomputed independently (bars by pandas from the M1 store; RSI, MACD, volatility and the indicators by plain loops). Below, three baskets per path, fill by fill, with the checked quantity.
### size flat

730 rule checks, 0 failed; 1457 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.01 | 1860.492 | +0.00 |  | add 1: lots 0.01 = round2(1 x 1 x 0.01) |
| 2 | 2023-02-13 02:53:02 | close | BUY | 0.01 | 1861.611 | -0.09 | target |  |
| 3 | 2023-02-13 02:53:02 | close | BUY | 0.01 | 1861.611 | +1.12 | target |  |
| | basket 0 | **target** | | | | **+1.03** | | 2 positions opened |
| 4 | 2023-02-13 02:58:02 | open | BUY | 0.01 | 1862.287 | +0.00 |  |  |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.01 | 1860.422 | +0.00 |  | add 1: lots 0.01 = round2(1 x 1 x 0.01) |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.01 | 1859.501 | +0.00 |  | add 2: lots 0.01 = round2(1 x 1 x 0.01) |
| 7 | 2023-02-13 06:04:49 | close | BUY | 0.01 | 1861.136 | -1.15 | target |  |
| 8 | 2023-02-13 06:04:49 | close | BUY | 0.01 | 1861.136 | +0.71 | target |  |
| 9 | 2023-02-13 06:04:49 | close | BUY | 0.01 | 1861.136 | +1.63 | target |  |
| | basket 1 | **target** | | | | **+1.19** | | 3 positions opened |
| 16 | 2023-02-13 06:46:24 | open | BUY | 0.01 | 1864.939 | +0.00 |  |  |
| 17 | 2023-02-13 07:00:01 | add | BUY | 0.01 | 1862.682 | +0.00 |  | add 1: lots 0.01 = round2(1 x 1 x 0.01) |
| 18 | 2023-02-13 07:06:40 | close | BUY | 0.01 | 1864.424 | -0.52 | target |  |
| 19 | 2023-02-13 07:06:40 | close | BUY | 0.01 | 1864.424 | +1.74 | target |  |
| | basket 5 | **target** | | | | **+1.22** | | 2 positions opened |

### size +1

934 rule checks, 0 failed; 1603 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.02 | 1860.492 | +0.00 |  | add 1: lots 0.02 = round2(2 x 1 x 0.01) |
| 2 | 2023-02-13 02:51:42 | close | BUY | 0.01 | 1861.278 | -0.42 | target |  |
| 3 | 2023-02-13 02:51:42 | close | BUY | 0.02 | 1861.278 | +1.57 | target |  |
| | basket 0 | **target** | | | | **+1.15** | | 2 positions opened |
| 4 | 2023-02-13 02:56:43 | open | BUY | 0.01 | 1862.318 | +0.00 |  |  |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.02 | 1860.422 | +0.00 |  | add 1: lots 0.02 = round2(2 x 1 x 0.01) |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.03 | 1859.501 | +0.00 |  | add 2: lots 0.03 = round2(3 x 1 x 0.01) |
| 7 | 2023-02-13 06:04:15 | close | BUY | 0.01 | 1860.526 | -1.79 | target |  |
| 8 | 2023-02-13 06:04:15 | close | BUY | 0.02 | 1860.526 | +0.21 | target |  |
| 9 | 2023-02-13 06:04:15 | close | BUY | 0.03 | 1860.526 | +3.08 | target |  |
| | basket 1 | **target** | | | | **+1.50** | | 3 positions opened |
| 16 | 2023-02-13 06:46:00 | open | BUY | 0.01 | 1865.157 | +0.00 |  |  |
| 17 | 2023-02-13 07:00:01 | add | BUY | 0.02 | 1862.682 | +0.00 |  | add 1: lots 0.02 = round2(2 x 1 x 0.01) |
| 18 | 2023-02-13 07:05:55 | close | BUY | 0.01 | 1863.870 | -1.29 | target |  |
| 19 | 2023-02-13 07:05:55 | close | BUY | 0.02 | 1863.870 | +2.38 | target |  |
| | basket 5 | **target** | | | | **+1.09** | | 2 positions opened |

### size doubling

765 rule checks, 0 failed; 1161 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.02 | 1860.492 | +0.00 |  | add 1: lots 0.02 = round2(2 x 1 x 0.01) |
| 2 | 2023-02-13 02:51:42 | close | BUY | 0.01 | 1861.278 | -0.42 | target |  |
| 3 | 2023-02-13 02:51:42 | close | BUY | 0.02 | 1861.278 | +1.57 | target |  |
| | basket 0 | **target** | | | | **+1.15** | | 2 positions opened |
| 4 | 2023-02-13 02:56:43 | open | BUY | 0.01 | 1862.318 | +0.00 |  |  |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.02 | 1860.422 | +0.00 |  | add 1: lots 0.02 = round2(2 x 1 x 0.01) |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.04 | 1859.501 | +0.00 |  | add 2: lots 0.04 = round2(4 x 1 x 0.01) |
| 7 | 2023-02-13 05:44:22 | close | BUY | 0.01 | 1860.336 | -1.98 | target |  |
| 8 | 2023-02-13 05:44:22 | close | BUY | 0.02 | 1860.336 | -0.17 | target |  |
| 9 | 2023-02-13 05:44:22 | close | BUY | 0.04 | 1860.336 | +3.34 | target |  |
| | basket 1 | **target** | | | | **+1.19** | | 3 positions opened |
| 18 | 2023-02-13 06:46:21 | open | BUY | 0.01 | 1864.861 | +0.00 |  |  |
| 19 | 2023-02-13 07:00:01 | add | BUY | 0.02 | 1862.682 | +0.00 |  | add 1: lots 0.02 = round2(2 x 1 x 0.01) |
| 20 | 2023-02-13 07:05:55 | close | BUY | 0.01 | 1863.812 | -1.05 | target |  |
| 21 | 2023-02-13 07:05:55 | close | BUY | 0.02 | 1863.812 | +2.26 | target |  |
| | basket 6 | **target** | | | | **+1.21** | | 2 positions opened |

### tiers T12 M2-M20

593 rule checks, 0 failed; 835 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 03:47:57 | add | BUY | 0.02 | 1860.134 | +0.00 |  | add 1 on M2: forming RSI 34.451 <= 35 |
| 2 | 2023-02-13 03:50:30 | add | BUY | 0.03 | 1859.532 | +0.00 |  | add 2 on M4: forming RSI 34.497 <= 35 |
| 3 | 2023-02-13 03:50:32 | add | BUY | 0.05 | 1859.501 | +0.00 |  | add 3 on M6: forming RSI 33.670 <= 35 |
| 4 | 2023-02-13 03:59:38 | add | BUY | 0.08 | 1859.277 | +0.00 |  | add 4 on M10: forming RSI 34.960 <= 35 |
| 5 | 2023-02-13 05:20:26 | close | BUY | 0.01 | 1859.680 | -2.02 | target |  |
| 6 | 2023-02-13 05:20:26 | close | BUY | 0.02 | 1859.680 | -0.91 | target |  |
| 7 | 2023-02-13 05:20:26 | close | BUY | 0.03 | 1859.680 | +0.44 | target |  |
| 8 | 2023-02-13 05:20:26 | close | BUY | 0.05 | 1859.680 | +0.90 | target |  |
| 9 | 2023-02-13 05:20:26 | close | BUY | 0.08 | 1859.680 | +3.22 | target |  |
| | basket 0 | **target** | | | | **+1.63** | | 5 positions opened |
| 34 | 2023-02-13 12:00:45 | open | BUY | 0.01 | 1862.607 | +0.00 |  |  |
| 35 | 2023-02-13 12:10:07 | add | BUY | 0.02 | 1859.909 | +0.00 |  | add 1 on M2: forming RSI 33.932 <= 35 |
| 36 | 2023-02-13 12:17:07 | close | BUY | 0.01 | 1861.195 | -1.41 | target |  |
| 37 | 2023-02-13 12:17:07 | close | BUY | 0.02 | 1861.195 | +2.57 | target |  |
| | basket 13 | **target** | | | | **+1.16** | | 2 positions opened |
| 38 | 2023-02-13 12:22:08 | open | BUY | 0.01 | 1862.036 | +0.00 |  |  |
| 39 | 2023-02-13 13:20:12 | add | BUY | 0.02 | 1859.193 | +0.00 |  | add 1 on M2: forming RSI 34.897 <= 35 |
| 40 | 2023-02-13 13:21:42 | add | BUY | 0.03 | 1858.023 | +0.00 |  | add 2 on M4: forming RSI 34.580 <= 35 |
| 41 | 2023-02-13 13:24:18 | close | BUY | 0.01 | 1859.258 | -2.78 | target |  |
| 42 | 2023-02-13 13:24:18 | close | BUY | 0.02 | 1859.258 | +0.13 | target |  |
| 43 | 2023-02-13 13:24:18 | close | BUY | 0.03 | 1859.258 | +3.71 | target |  |
| | basket 14 | **target** | | | | **+1.06** | | 3 positions opened |

### tiers T13 M10-H6

495 rule checks, 0 failed; 550 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 03:59:39 | add | BUY | 0.02 | 1859.277 | +0.00 |  | add 1 on M10: forming RSI 34.960 <= 35 |
| 2 | 2023-02-13 06:04:15 | close | BUY | 0.01 | 1860.526 | -1.17 | target |  |
| 3 | 2023-02-13 06:04:15 | close | BUY | 0.02 | 1860.526 | +2.50 | target |  |
| | basket 0 | **target** | | | | **+1.33** | | 2 positions opened |
| 24 | 2023-02-13 13:00:47 | open | BUY | 0.01 | 1862.011 | +0.00 |  |  |
| 25 | 2023-02-13 13:45:54 | add | BUY | 0.02 | 1856.011 | +0.00 |  | add 1 on M10: forming RSI 34.964 <= 35 |
| 26 | 2023-02-13 14:06:14 | close | BUY | 0.01 | 1858.397 | -3.61 | target |  |
| 27 | 2023-02-13 14:06:14 | close | BUY | 0.02 | 1858.397 | +4.77 | target |  |
| | basket 11 | **target** | | | | **+1.16** | | 2 positions opened |
| 28 | 2023-02-13 14:11:14 | open | BUY | 0.01 | 1857.179 | +0.00 |  |  |
| 29 | 2023-02-13 14:33:15 | add | BUY | 0.02 | 1855.663 | +0.00 |  | add 1 on M10: forming RSI 34.662 <= 35 |
| 30 | 2023-02-13 14:34:50 | add | BUY | 0.03 | 1854.955 | +0.00 |  | add 2 on M20: forming RSI 34.869 <= 35 |
| 31 | 2023-02-13 14:37:13 | close | BUY | 0.01 | 1855.756 | -1.42 | target |  |
| 32 | 2023-02-13 14:37:13 | close | BUY | 0.02 | 1855.756 | +0.19 | target |  |
| 33 | 2023-02-13 14:37:13 | close | BUY | 0.03 | 1855.756 | +2.40 | target |  |
| | basket 12 | **target** | | | | **+1.17** | | 3 positions opened |

### tiers T6 +D1+W1

996 rule checks, 0 failed; 1601 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.02 | 1860.492 | +0.00 |  | add 1 on M1: forming RSI 34.666 <= 35 |
| 2 | 2023-02-13 02:51:42 | close | BUY | 0.01 | 1861.278 | -0.42 | target |  |
| 3 | 2023-02-13 02:51:42 | close | BUY | 0.02 | 1861.278 | +1.57 | target |  |
| | basket 0 | **target** | | | | **+1.15** | | 2 positions opened |
| 4 | 2023-02-13 02:56:43 | open | BUY | 0.01 | 1862.318 | +0.00 |  |  |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.02 | 1860.422 | +0.00 |  | add 1 on M1: forming RSI 34.747 <= 35 |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.03 | 1859.501 | +0.00 |  | add 2 on M5: forming RSI 34.933 <= 35 |
| 7 | 2023-02-13 06:04:15 | close | BUY | 0.01 | 1860.526 | -1.79 | target |  |
| 8 | 2023-02-13 06:04:15 | close | BUY | 0.02 | 1860.526 | +0.21 | target |  |
| 9 | 2023-02-13 06:04:15 | close | BUY | 0.03 | 1860.526 | +3.08 | target |  |
| | basket 1 | **target** | | | | **+1.50** | | 3 positions opened |
| 16 | 2023-02-13 06:46:00 | open | BUY | 0.01 | 1865.157 | +0.00 |  |  |
| 17 | 2023-02-13 07:00:01 | add | BUY | 0.02 | 1862.682 | +0.00 |  | add 1 on M1: forming RSI 32.588 <= 35 |
| 18 | 2023-02-13 07:05:55 | close | BUY | 0.01 | 1863.870 | -1.29 | target |  |
| 19 | 2023-02-13 07:05:55 | close | BUY | 0.02 | 1863.870 | +2.38 | target |  |
| | basket 5 | **target** | | | | **+1.09** | | 2 positions opened |

### per-tier stricter

604 rule checks, 0 failed; 1536 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.02 | 1860.492 | +0.00 |  | add 1 on M1: forming RSI 34.666 <= 35 |
| 2 | 2023-02-13 02:51:42 | close | BUY | 0.01 | 1861.278 | -0.42 | target |  |
| 3 | 2023-02-13 02:51:42 | close | BUY | 0.02 | 1861.278 | +1.57 | target |  |
| | basket 0 | **target** | | | | **+1.15** | | 2 positions opened |
| 4 | 2023-02-13 02:56:43 | open | BUY | 0.01 | 1862.318 | +0.00 |  |  |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.02 | 1860.422 | +0.00 |  | add 1 on M1: forming RSI 34.747 <= 35 |
| 6 | 2023-02-13 04:00:00 | add | BUY | 0.03 | 1858.980 | +0.00 |  | add 2 on M5: forming RSI 31.845 <= 32 |
| 7 | 2023-02-13 05:22:31 | close | BUY | 0.01 | 1860.185 | -2.13 | target |  |
| 8 | 2023-02-13 05:22:31 | close | BUY | 0.02 | 1860.185 | -0.47 | target |  |
| 9 | 2023-02-13 05:22:31 | close | BUY | 0.03 | 1860.185 | +3.61 | target |  |
| | basket 1 | **target** | | | | **+1.01** | | 3 positions opened |
| 18 | 2023-02-13 06:46:21 | open | BUY | 0.01 | 1864.861 | +0.00 |  |  |
| 19 | 2023-02-13 07:00:01 | add | BUY | 0.02 | 1862.682 | +0.00 |  | add 1 on M1: forming RSI 32.588 <= 35 |
| 20 | 2023-02-13 07:05:55 | close | BUY | 0.01 | 1863.812 | -1.05 | target |  |
| 21 | 2023-02-13 07:05:55 | close | BUY | 0.02 | 1863.812 | +2.26 | target |  |
| | basket 6 | **target** | | | | **+1.21** | | 2 positions opened |

### trigger macd_hist

1877 rule checks, 0 failed; 1289 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:00:46 | add | BUY | 0.02 | 1861.049 | +0.00 |  | M1 forming hist -0.0020 on the wrong side |
| 2 | 2023-02-13 02:02:28 | close | BUY | 0.01 | 1861.607 | -0.09 | target |  |
| 3 | 2023-02-13 02:02:28 | close | BUY | 0.02 | 1861.607 | +1.12 | target |  |
| | basket 0 | **target** | | | | **+1.03** | | 2 positions opened |
| 4 | 2023-02-13 02:07:29 | open | BUY | 0.01 | 1861.840 | +0.00 |  |  |
| 5 | 2023-02-13 02:08:01 | add | BUY | 0.02 | 1861.679 | +0.00 |  | M1 forming hist -0.0185 on the wrong side |
| 6 | 2023-02-13 02:12:02 | close | BUY | 0.01 | 1862.100 | +0.26 | target |  |
| 7 | 2023-02-13 02:12:02 | close | BUY | 0.02 | 1862.100 | +0.84 | target |  |
| | basket 1 | **target** | | | | **+1.10** | | 2 positions opened |
| 8 | 2023-02-13 02:17:02 | open | BUY | 0.01 | 1861.347 | +0.00 |  |  |
| 9 | 2023-02-13 02:17:03 | add | BUY | 0.02 | 1861.329 | +0.00 |  | M1 forming hist -0.1177 on the wrong side |
| 10 | 2023-02-13 02:19:01 | close | BUY | 0.01 | 1861.771 | +0.42 | target |  |
| 11 | 2023-02-13 02:19:01 | close | BUY | 0.02 | 1861.771 | +0.88 | target |  |
| | basket 2 | **target** | | | | **+1.30** | | 2 positions opened |

### trigger macd_cross

1423 rule checks, 0 failed; 1771 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:02:29 | add | BUY | 0.02 | 1861.871 | +0.00 |  | M1 hist now +0.0004, min since last fill -0.0576 |
| 2 | 2023-02-13 02:03:09 | close | BUY | 0.01 | 1862.333 | +0.63 | target |  |
| 3 | 2023-02-13 02:03:09 | close | BUY | 0.02 | 1862.333 | +0.92 | target |  |
| | basket 0 | **target** | | | | **+1.55** | | 2 positions opened |
| 4 | 2023-02-13 02:08:10 | open | BUY | 0.01 | 1861.749 | +0.00 |  |  |
| 5 | 2023-02-13 02:08:37 | add | BUY | 0.02 | 1861.972 | +0.00 |  | M1 hist now +0.0002, min since last fill -0.0144 |
| 6 | 2023-02-13 02:12:40 | close | BUY | 0.01 | 1862.315 | +0.57 | target |  |
| 7 | 2023-02-13 02:12:40 | close | BUY | 0.02 | 1862.315 | +0.69 | target |  |
| | basket 1 | **target** | | | | **+1.26** | | 2 positions opened |
| 8 | 2023-02-13 02:17:41 | open | BUY | 0.01 | 1861.519 | +0.00 |  |  |
| 9 | 2023-02-13 02:21:13 | add | BUY | 0.02 | 1861.985 | +0.00 |  | M1 hist now +0.0008, min since last fill -0.1123 |
| 10 | 2023-02-13 02:44:56 | add | BUY | 0.03 | 1860.186 | +0.00 |  | M5 hist now +0.0005, min since last fill -0.0033 |
| 11 | 2023-02-13 02:50:27 | close | BUY | 0.01 | 1861.210 | -0.31 | target |  |
| 12 | 2023-02-13 02:50:27 | close | BUY | 0.02 | 1861.210 | -1.55 | target |  |
| 13 | 2023-02-13 02:50:27 | close | BUY | 0.03 | 1861.210 | +3.07 | target |  |
| | basket 2 | **target** | | | | **+1.21** | | 3 positions opened |

### trigger rsi_macd

492 rule checks, 0 failed; 1501 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:40:00 | add | BUY | 0.02 | 1860.834 | +0.00 |  | M1 RSI reached 30.82 since the last fill (level 35); MACD vote: existing slope_sign |
| 2 | 2023-02-13 02:51:53 | close | BUY | 0.01 | 1861.470 | -0.23 | target |  |
| 3 | 2023-02-13 02:51:53 | close | BUY | 0.02 | 1861.470 | +1.27 | target |  |
| | basket 0 | **target** | | | | **+1.04** | | 2 positions opened |
| 4 | 2023-02-13 02:56:53 | open | BUY | 0.01 | 1862.296 | +0.00 |  |  |
| 5 | 2023-02-13 03:50:00 | add | BUY | 0.02 | 1860.026 | +0.00 |  | M1 RSI reached 26.51 since the last fill (level 35); MACD vote: existing slope_sign |
| 6 | 2023-02-13 04:10:01 | add | BUY | 0.03 | 1859.402 | +0.00 |  | M5 RSI reached 30.07 since the last fill (level 35); MACD vote: existing slope_sign |
| 7 | 2023-02-13 05:44:20 | close | BUY | 0.01 | 1860.269 | -2.03 | target |  |
| 8 | 2023-02-13 05:44:20 | close | BUY | 0.02 | 1860.269 | +0.49 | target |  |
| 9 | 2023-02-13 05:44:20 | close | BUY | 0.03 | 1860.269 | +2.60 | target |  |
| | basket 1 | **target** | | | | **+1.06** | | 3 positions opened |
| 18 | 2023-02-13 06:46:21 | open | BUY | 0.01 | 1864.861 | +0.00 |  |  |
| 19 | 2023-02-13 07:01:00 | add | BUY | 0.02 | 1862.699 | +0.00 |  | M1 RSI reached 30.12 since the last fill (level 35); MACD vote: existing slope_sign |
| 20 | 2023-02-13 07:05:55 | close | BUY | 0.01 | 1863.812 | -1.05 | target |  |
| 21 | 2023-02-13 07:05:55 | close | BUY | 0.02 | 1863.812 | +2.23 | target |  |
| | basket 6 | **target** | | | | **+1.18** | | 2 positions opened |

### trigger stoch

518 rule checks, 0 failed; 677 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:34:00 | add | BUY | 0.02 | 1861.141 | +0.00 |  | M1 closed-bar stoch 16.259 <= 20 |
| 2 | 2023-02-13 02:53:15 | close | BUY | 0.01 | 1861.666 | -0.03 | target |  |
| 3 | 2023-02-13 02:53:15 | close | BUY | 0.02 | 1861.666 | +1.05 | target |  |
| | basket 0 | **target** | | | | **+1.02** | | 2 positions opened |
| 4 | 2023-02-13 02:58:15 | open | BUY | 0.01 | 1862.250 | +0.00 |  |  |
| 5 | 2023-02-13 03:07:00 | add | BUY | 0.02 | 1861.412 | +0.00 |  | M1 closed-bar stoch 19.365 <= 20 |
| 6 | 2023-02-13 03:55:00 | add | BUY | 0.03 | 1859.547 | +0.00 |  | M5 closed-bar stoch 13.790 <= 20 |
| 7 | 2023-02-13 04:30:00 | add | BUY | 0.05 | 1859.092 | +0.00 |  | M15 closed-bar stoch 12.773 <= 20 |
| 8 | 2023-02-13 05:22:16 | close | BUY | 0.01 | 1860.068 | -2.18 | target |  |
| 9 | 2023-02-13 05:22:16 | close | BUY | 0.02 | 1860.068 | -2.69 | target |  |
| 10 | 2023-02-13 05:22:16 | close | BUY | 0.03 | 1860.068 | +1.56 | target |  |
| 11 | 2023-02-13 05:22:16 | close | BUY | 0.05 | 1860.068 | +4.88 | target |  |
| | basket 1 | **target** | | | | **+1.57** | | 4 positions opened |
| 12 | 2023-02-13 05:27:17 | open | BUY | 0.01 | 1859.679 | +0.00 |  |  |
| 13 | 2023-02-13 05:33:00 | add | BUY | 0.02 | 1858.780 | +0.00 |  | M1 closed-bar stoch 15.332 <= 20 |
| 14 | 2023-02-13 05:42:40 | close | BUY | 0.01 | 1859.474 | -0.21 | target |  |
| 15 | 2023-02-13 05:42:40 | close | BUY | 0.02 | 1859.474 | +1.39 | target |  |
| | basket 2 | **target** | | | | **+1.18** | | 2 positions opened |

### trigger emadist

530 rule checks, 0 failed; 1492 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:39:00 | add | BUY | 0.02 | 1860.265 | +0.00 |  | M1 closed-bar emadist -2.522 <= -2 |
| 2 | 2023-02-13 02:49:54 | close | BUY | 0.01 | 1861.107 | -0.59 | target |  |
| 3 | 2023-02-13 02:49:54 | close | BUY | 0.02 | 1861.107 | +1.68 | target |  |
| | basket 0 | **target** | | | | **+1.09** | | 2 positions opened |
| 4 | 2023-02-13 02:54:54 | open | BUY | 0.01 | 1861.647 | +0.00 |  |  |
| 5 | 2023-02-13 03:47:00 | add | BUY | 0.02 | 1860.192 | +0.00 |  | M1 closed-bar emadist -2.264 <= -2 |
| 6 | 2023-02-13 04:00:00 | add | BUY | 0.03 | 1858.980 | +0.00 |  | M5 closed-bar emadist -2.154 <= -2 |
| 7 | 2023-02-13 05:22:07 | close | BUY | 0.01 | 1860.013 | -1.63 | target |  |
| 8 | 2023-02-13 05:22:07 | close | BUY | 0.02 | 1860.013 | -0.36 | target |  |
| 9 | 2023-02-13 05:22:07 | close | BUY | 0.03 | 1860.013 | +3.10 | target |  |
| | basket 1 | **target** | | | | **+1.11** | | 3 positions opened |
| 18 | 2023-02-13 06:46:21 | open | BUY | 0.01 | 1864.861 | +0.00 |  |  |
| 19 | 2023-02-13 07:00:00 | add | BUY | 0.02 | 1863.027 | +0.00 |  | M1 closed-bar emadist -2.162 <= -2 |
| 20 | 2023-02-13 07:06:40 | close | BUY | 0.01 | 1864.392 | -0.47 | target |  |
| 21 | 2023-02-13 07:06:40 | close | BUY | 0.02 | 1864.392 | +2.73 | target |  |
| | basket 6 | **target** | | | | **+2.26** | | 2 positions opened |

### gap geometric 1.5

314 rule checks, 0 failed; 1402 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 03:50:44 | add | BUY | 0.02 | 1859.443 | +0.00 |  | add 1: 2.255 from the last fill >= gap 2.236 |
| 2 | 2023-02-13 06:04:34 | close | BUY | 0.01 | 1860.540 | -1.16 | target |  |
| 3 | 2023-02-13 06:04:34 | close | BUY | 0.02 | 1860.540 | +2.19 | target |  |
| | basket 0 | **target** | | | | **+1.03** | | 2 positions opened |
| 10 | 2023-02-13 06:46:21 | open | BUY | 0.01 | 1864.861 | +0.00 |  |  |
| 11 | 2023-02-13 07:00:01 | add | BUY | 0.02 | 1862.649 | +0.00 |  | add 1: 2.212 from the last fill >= gap 2.084 |
| 12 | 2023-02-13 07:05:56 | close | BUY | 0.01 | 1863.746 | -1.12 | target |  |
| 13 | 2023-02-13 07:05:56 | close | BUY | 0.02 | 1863.746 | +2.19 | target |  |
| | basket 4 | **target** | | | | **+1.07** | | 2 positions opened |
| 26 | 2023-02-13 12:00:45 | open | BUY | 0.01 | 1862.607 | +0.00 |  |  |
| 27 | 2023-02-13 12:07:38 | add | BUY | 0.02 | 1860.379 | +0.00 |  | add 1: 2.228 from the last fill >= gap 2.224 |
| 28 | 2023-02-13 12:17:32 | close | BUY | 0.01 | 1861.471 | -1.14 | target |  |
| 29 | 2023-02-13 12:17:32 | close | BUY | 0.02 | 1861.471 | +2.18 | target |  |
| | basket 11 | **target** | | | | **+1.04** | | 2 positions opened |

### gap D1 0.15

466 rule checks, 0 failed; 1500 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:44:57 | add | BUY | 0.02 | 1860.108 | +0.00 |  | add 1: 1.590 from the last fill >= gap 1.536 |
| 2 | 2023-02-13 02:49:42 | close | BUY | 0.01 | 1861.060 | -0.64 | target |  |
| 3 | 2023-02-13 02:49:42 | close | BUY | 0.02 | 1861.060 | +1.90 | target |  |
| | basket 0 | **target** | | | | **+1.26** | | 2 positions opened |
| 4 | 2023-02-13 02:54:42 | open | BUY | 0.01 | 1861.750 | +0.00 |  |  |
| 5 | 2023-02-13 03:46:57 | add | BUY | 0.02 | 1860.202 | +0.00 |  | add 1: 1.548 from the last fill >= gap 1.536 |
| 6 | 2023-02-13 04:15:21 | add | BUY | 0.03 | 1858.618 | +0.00 |  | add 2: 1.584 from the last fill >= gap 1.536 |
| 7 | 2023-02-13 05:21:21 | close | BUY | 0.01 | 1859.865 | -1.88 | target |  |
| 8 | 2023-02-13 05:21:21 | close | BUY | 0.02 | 1859.865 | -0.67 | target |  |
| 9 | 2023-02-13 05:21:21 | close | BUY | 0.03 | 1859.865 | +3.74 | target |  |
| | basket 1 | **target** | | | | **+1.19** | | 3 positions opened |
| 18 | 2023-02-13 06:46:20 | open | BUY | 0.01 | 1864.861 | +0.00 |  |  |
| 19 | 2023-02-13 07:00:01 | add | BUY | 0.02 | 1862.682 | +0.00 |  | add 1: 2.179 from the last fill >= gap 1.536 |
| 20 | 2023-02-13 07:05:55 | close | BUY | 0.01 | 1863.812 | -1.05 | target |  |
| 21 | 2023-02-13 07:05:55 | close | BUY | 0.02 | 1863.812 | +2.26 | target |  |
| | basket 6 | **target** | | | | **+1.21** | | 2 positions opened |

### stop 20% balance

1605 rule checks, 0 failed; 1606 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 1640 | 2023-03-10 19:39:21 | open | SELL | 0.01 | 1861.076 | +0.00 |  |  |
| 1641 | 2023-03-10 19:55:14 | add | SELL | 0.02 | 1863.972 | +0.00 |  |  |
| 1642 | 2023-03-10 20:35:21 | add | SELL | 0.03 | 1866.424 | +0.00 |  |  |
| 1643 | 2023-03-10 20:35:23 | add | SELL | 0.05 | 1866.401 | +0.00 |  |  |
| 1644 | 2023-03-10 20:35:25 | add | SELL | 0.08 | 1866.348 | +0.00 |  |  |
| 1645 | 2023-03-10 20:35:27 | add | SELL | 0.13 | 1866.332 | +0.00 |  |  |
| 1646 | 2023-03-12 22:05:01 | close | SELL | 0.01 | 1883.812 | -22.74 | stop_loss | basket 466 stopped at -568.58 <= -383.70 (20% of 1918.52) |
| 1647 | 2023-03-12 22:05:01 | close | SELL | 0.02 | 1883.812 | -39.68 | stop_loss |  |
| 1648 | 2023-03-12 22:05:01 | close | SELL | 0.03 | 1883.812 | -52.16 | stop_loss |  |
| 1649 | 2023-03-12 22:05:01 | close | SELL | 0.05 | 1883.812 | -87.05 | stop_loss |  |
| 1650 | 2023-03-12 22:05:01 | close | SELL | 0.08 | 1883.812 | -139.71 | stop_loss |  |
| 1651 | 2023-03-12 22:05:01 | close | SELL | 0.13 | 1883.812 | -227.24 | stop_loss |  |
| | basket 466 | **stop_loss** | | | | **-568.58** | | 6 positions opened |
| 2204 | 2023-03-17 17:29:16 | open | SELL | 0.01 | 1968.529 | +0.00 |  |  |
| 2205 | 2023-03-17 17:29:17 | add | SELL | 0.02 | 1968.708 | +0.00 |  |  |
| 2206 | 2023-03-17 17:29:20 | add | SELL | 0.03 | 1968.318 | +0.00 |  |  |
| 2207 | 2023-03-17 17:29:22 | add | SELL | 0.05 | 1968.309 | +0.00 |  |  |
| 2208 | 2023-03-17 17:29:24 | add | SELL | 0.08 | 1968.185 | +0.00 |  |  |
| 2209 | 2023-03-17 17:29:26 | add | SELL | 0.13 | 1968.081 | +0.00 |  |  |
| 2210 | 2023-03-17 18:06:24 | close | SELL | 0.01 | 1977.132 | -8.60 | stop_loss | basket 626 stopped at -285.25 <= -279.76 (20% of 1398.80) |
| 2211 | 2023-03-17 18:06:24 | close | SELL | 0.02 | 1977.132 | -16.85 | stop_loss |  |
| 2212 | 2023-03-17 18:06:24 | close | SELL | 0.03 | 1977.132 | -26.44 | stop_loss |  |
| 2213 | 2023-03-17 18:06:24 | close | SELL | 0.05 | 1977.132 | -44.12 | stop_loss |  |
| 2214 | 2023-03-17 18:06:24 | close | SELL | 0.08 | 1977.132 | -71.58 | stop_loss |  |
| 2215 | 2023-03-17 18:06:24 | close | SELL | 0.13 | 1977.132 | -117.66 | stop_loss |  |
| | basket 626 | **stop_loss** | | | | **-285.25** | | 6 positions opened |
| 2562 | 2023-03-23 17:20:13 | open | SELL | 0.01 | 1991.133 | +0.00 |  |  |
| 2563 | 2023-03-23 17:32:42 | add | SELL | 0.02 | 1994.742 | +0.00 |  |  |
| 2564 | 2023-03-23 17:32:44 | add | SELL | 0.03 | 1994.958 | +0.00 |  |  |
| 2565 | 2023-03-23 17:32:47 | add | SELL | 0.05 | 1994.967 | +0.00 |  |  |
| 2566 | 2023-03-23 17:32:49 | add | SELL | 0.08 | 1995.053 | +0.00 |  |  |
| 2567 | 2023-03-23 17:32:51 | add | SELL | 0.13 | 1995.118 | +0.00 |  |  |
| 2568 | 2023-03-23 18:08:27 | close | SELL | 0.01 | 2001.668 | -10.53 | stop_loss | basket 733 stopped at -216.08 <= -216.00 (20% of 1080.01) |
| 2569 | 2023-03-23 18:08:27 | close | SELL | 0.02 | 2001.668 | -13.85 | stop_loss |  |
| 2570 | 2023-03-23 18:08:27 | close | SELL | 0.03 | 2001.668 | -20.13 | stop_loss |  |
| 2571 | 2023-03-23 18:08:27 | close | SELL | 0.05 | 2001.668 | -33.50 | stop_loss |  |
| 2572 | 2023-03-23 18:08:27 | close | SELL | 0.08 | 2001.668 | -52.92 | stop_loss |  |
| 2573 | 2023-03-23 18:08:27 | close | SELL | 0.13 | 2001.668 | -85.15 | stop_loss |  |
| | basket 733 | **stop_loss** | | | | **-216.08** | | 6 positions opened |

### time 24h deep

1029 rule checks, 0 failed; 1133 accounting checks, 0 failed. deep baskets older than 24 h not closed by the time stop: 1

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 2204 | 2023-03-17 17:29:16 | open | SELL | 0.01 | 1968.529 | +0.00 |  |  |
| 2205 | 2023-03-17 17:29:17 | add | SELL | 0.02 | 1968.708 | +0.00 |  |  |
| 2206 | 2023-03-17 17:29:20 | add | SELL | 0.03 | 1968.318 | +0.00 |  |  |
| 2207 | 2023-03-17 17:29:22 | add | SELL | 0.05 | 1968.309 | +0.00 |  |  |
| 2208 | 2023-03-17 17:29:24 | add | SELL | 0.08 | 1968.185 | +0.00 |  |  |
| 2209 | 2023-03-17 17:29:26 | add | SELL | 0.13 | 1968.081 | +0.00 |  |  |
| 2210 | 2023-03-19 22:05:01 | close | SELL | 0.01 | 1986.156 | -17.63 | time_stop | basket 626 time stop after 5 adds, 52.6 h |
| 2211 | 2023-03-19 22:05:01 | close | SELL | 0.02 | 1986.156 | -34.90 | time_stop |  |
| 2212 | 2023-03-19 22:05:01 | close | SELL | 0.03 | 1986.156 | -53.51 | time_stop |  |
| 2213 | 2023-03-19 22:05:01 | close | SELL | 0.05 | 1986.156 | -89.23 | time_stop |  |
| 2214 | 2023-03-19 22:05:01 | close | SELL | 0.08 | 1986.156 | -143.77 | time_stop |  |
| 2215 | 2023-03-19 22:05:01 | close | SELL | 0.13 | 1986.156 | -234.98 | time_stop |  |
| | basket 626 | **time_stop** | | | | **-574.02** | | 6 positions opened |
| 3046 | 2023-03-31 20:57:29 | open | BUY | 0.01 | 1969.419 | +0.00 |  |  |
| 3047 | 2023-04-02 22:09:48 | add | BUY | 0.02 | 1965.823 | +0.00 |  |  |
| 3048 | 2023-04-02 22:09:50 | add | BUY | 0.03 | 1965.831 | +0.00 |  |  |
| 3049 | 2023-04-02 22:09:52 | add | BUY | 0.05 | 1965.832 | +0.00 |  |  |
| 3050 | 2023-04-02 22:09:54 | close | BUY | 0.01 | 1965.898 | -3.52 | time_stop | basket 894 time stop after 3 adds, 49.2 h |
| 3051 | 2023-04-02 22:09:54 | close | BUY | 0.02 | 1965.898 | +0.15 | time_stop |  |
| 3052 | 2023-04-02 22:09:54 | close | BUY | 0.03 | 1965.898 | +0.20 | time_stop |  |
| 3053 | 2023-04-02 22:09:54 | close | BUY | 0.05 | 1965.898 | +0.33 | time_stop |  |
| | basket 894 | **time_stop** | | | | **-2.84** | | 4 positions opened |

### target b/e after 3

1293 rule checks, 0 failed; 1598 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.02 | 1860.492 | +0.00 |  |  |
| 2 | 2023-02-13 02:51:42 | close | BUY | 0.01 | 1861.278 | -0.42 | target | basket 0 (2 pos) closed at 1.15 > target 1.00 |
| 3 | 2023-02-13 02:51:42 | close | BUY | 0.02 | 1861.278 | +1.57 | target |  |
| | basket 0 | **target** | | | | **+1.15** | | 2 positions opened |
| 4 | 2023-02-13 02:56:43 | open | BUY | 0.01 | 1862.318 | +0.00 |  |  |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.02 | 1860.422 | +0.00 |  |  |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.03 | 1859.501 | +0.00 |  |  |
| 7 | 2023-02-13 06:04:15 | close | BUY | 0.01 | 1860.526 | -1.79 | target | basket 1 (3 pos) closed at 1.50 > target 1.00 |
| 8 | 2023-02-13 06:04:15 | close | BUY | 0.02 | 1860.526 | +0.21 | target |  |
| 9 | 2023-02-13 06:04:15 | close | BUY | 0.03 | 1860.526 | +3.08 | target |  |
| | basket 1 | **target** | | | | **+1.50** | | 3 positions opened |
| 10 | 2023-02-13 06:09:16 | open | BUY | 0.01 | 1861.324 | +0.00 |  |  |
| 11 | 2023-02-13 06:23:03 | close | BUY | 0.01 | 1862.379 | +1.05 | target | basket 2 (1 pos) closed at 1.05 > target 1.00 |
| | basket 2 | **target** | | | | **+1.05** | | 1 positions opened |

### target shrink

1322 rule checks, 0 failed; 1621 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.02 | 1860.492 | +0.00 |  |  |
| 2 | 2023-02-13 02:49:54 | close | BUY | 0.01 | 1861.107 | -0.59 | target | basket 0 (2 pos) closed at 0.64 > target 0.60 |
| 3 | 2023-02-13 02:49:54 | close | BUY | 0.02 | 1861.107 | +1.23 | target |  |
| | basket 0 | **target** | | | | **+0.64** | | 2 positions opened |
| 4 | 2023-02-13 02:54:54 | open | BUY | 0.01 | 1861.647 | +0.00 |  |  |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.02 | 1860.422 | +0.00 |  |  |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.03 | 1859.501 | +0.00 |  |  |
| 7 | 2023-02-13 05:44:25 | close | BUY | 0.01 | 1860.377 | -1.27 | target | basket 1 (3 pos) closed at 1.27 > target 1.20 |
| 8 | 2023-02-13 05:44:25 | close | BUY | 0.02 | 1860.377 | -0.09 | target |  |
| 9 | 2023-02-13 05:44:25 | close | BUY | 0.03 | 1860.377 | +2.63 | target |  |
| | basket 1 | **target** | | | | **+1.27** | | 3 positions opened |
| 10 | 2023-02-13 05:49:25 | open | BUY | 0.01 | 1859.851 | +0.00 |  |  |
| 11 | 2023-02-13 06:04:37 | close | BUY | 0.01 | 1860.989 | +1.14 | target | basket 2 (1 pos) closed at 1.14 > target 1.00 |
| | basket 2 | **target** | | | | **+1.14** | | 1 positions opened |

### final close H6 full

58 rule checks, 0 failed; 1624 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 132 | 2023-02-14 15:44:26 | open | BUY | 0.01 | 1855.629 | +0.00 |  |  |
| 133 | 2023-02-14 15:44:27 | add | BUY | 0.02 | 1855.783 | +0.00 |  |  |
| 134 | 2023-02-14 16:40:44 | add | BUY | 0.03 | 1844.574 | +0.00 |  |  |
| 135 | 2023-02-14 16:40:46 | add | BUY | 0.05 | 1844.085 | +0.00 |  |  |
| 136 | 2023-02-14 16:40:48 | add | BUY | 0.08 | 1844.693 | +0.00 |  |  |
| 137 | 2023-02-14 16:40:51 | add | BUY | 0.13 | 1844.791 | +0.00 |  |  |
| 138 | 2023-02-14 16:40:53 | close | BUY | 0.01 | 1844.514 | -11.12 | final_close | basket 45: ladder full (6 pos), H6 RSI 33.70 |
| 139 | 2023-02-14 16:40:53 | close | BUY | 0.02 | 1844.514 | -22.54 | final_close |  |
| 140 | 2023-02-14 16:40:53 | close | BUY | 0.03 | 1844.514 | -0.18 | final_close |  |
| 141 | 2023-02-14 16:40:53 | close | BUY | 0.05 | 1844.514 | +2.14 | final_close |  |
| 142 | 2023-02-14 16:40:53 | close | BUY | 0.08 | 1844.514 | -1.43 | final_close |  |
| 143 | 2023-02-14 16:40:53 | close | BUY | 0.13 | 1844.514 | -3.60 | final_close |  |
| | basket 45 | **final_close** | | | | **-36.73** | | 6 positions opened |
| 292 | 2023-02-17 01:43:56 | open | BUY | 0.01 | 1831.977 | +0.00 |  |  |
| 293 | 2023-02-17 01:45:42 | add | BUY | 0.02 | 1830.897 | +0.00 |  |  |
| 294 | 2023-02-17 01:46:11 | add | BUY | 0.03 | 1830.542 | +0.00 |  |  |
| 295 | 2023-02-17 01:46:13 | add | BUY | 0.05 | 1830.559 | +0.00 |  |  |
| 296 | 2023-02-17 06:27:53 | add | BUY | 0.08 | 1825.472 | +0.00 |  |  |
| 297 | 2023-02-17 06:27:56 | add | BUY | 0.13 | 1825.485 | +0.00 |  |  |
| 298 | 2023-02-17 06:27:58 | close | BUY | 0.01 | 1825.269 | -6.71 | final_close | basket 96: ladder full (6 pos), H6 RSI 29.78 |
| 299 | 2023-02-17 06:27:58 | close | BUY | 0.02 | 1825.269 | -11.26 | final_close |  |
| 300 | 2023-02-17 06:27:58 | close | BUY | 0.03 | 1825.269 | -15.82 | final_close |  |
| 301 | 2023-02-17 06:27:58 | close | BUY | 0.05 | 1825.269 | -26.45 | final_close |  |
| 302 | 2023-02-17 06:27:58 | close | BUY | 0.08 | 1825.269 | -1.62 | final_close |  |
| 303 | 2023-02-17 06:27:58 | close | BUY | 0.13 | 1825.269 | -2.81 | final_close |  |
| | basket 96 | **final_close** | | | | **-64.67** | | 6 positions opened |
| 308 | 2023-02-17 07:49:45 | open | BUY | 0.01 | 1825.699 | +0.00 |  |  |
| 309 | 2023-02-17 08:01:51 | add | BUY | 0.02 | 1822.252 | +0.00 |  |  |
| 310 | 2023-02-17 08:02:42 | add | BUY | 0.03 | 1820.561 | +0.00 |  |  |
| 311 | 2023-02-17 08:02:44 | add | BUY | 0.05 | 1821.040 | +0.00 |  |  |
| 312 | 2023-02-17 08:02:46 | add | BUY | 0.08 | 1821.203 | +0.00 |  |  |
| 313 | 2023-02-17 08:02:48 | add | BUY | 0.13 | 1821.301 | +0.00 |  |  |
| 314 | 2023-02-17 08:02:51 | close | BUY | 0.01 | 1821.037 | -4.66 | final_close | basket 99: ladder full (6 pos), H6 RSI 28.04 |
| 315 | 2023-02-17 08:02:51 | close | BUY | 0.02 | 1821.037 | -2.43 | final_close |  |
| 316 | 2023-02-17 08:02:51 | close | BUY | 0.03 | 1821.037 | +1.43 | final_close |  |
| 317 | 2023-02-17 08:02:51 | close | BUY | 0.05 | 1821.037 | -0.01 | final_close |  |
| 318 | 2023-02-17 08:02:51 | close | BUY | 0.08 | 1821.037 | -1.33 | final_close |  |
| 319 | 2023-02-17 08:02:51 | close | BUY | 0.13 | 1821.037 | -3.43 | final_close |  |
| | basket 99 | **final_close** | | | | **-10.43** | | 6 positions opened |

### add gate H1 trend

83 rule checks, 0 failed; 1195 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 22 | 2023-02-13 16:09:50 | open | SELL | 0.01 | 1852.824 | +0.00 |  |  |
| 23 | 2023-02-13 16:46:49 | add | SELL | 0.02 | 1854.476 | +0.00 |  | add side -1, H1 MACD signal sign -1 |
| 24 | 2023-02-13 16:46:51 | close | SELL | 0.01 | 1854.804 | -1.98 | force_close |  |
| 25 | 2023-02-13 16:46:51 | close | SELL | 0.02 | 1854.804 | -0.66 | force_close |  |
| | basket 11 | **force_close** | | | | **-2.64** | | 2 positions opened |
| 68 | 2023-02-14 14:36:07 | open | SELL | 0.01 | 1844.785 | +0.00 |  |  |
| 69 | 2023-02-14 14:55:52 | add | SELL | 0.02 | 1854.820 | +0.00 |  | add side -1, H1 MACD signal sign -1 |
| 70 | 2023-02-14 15:00:00 | close | SELL | 0.01 | 1856.563 | -11.78 | force_close |  |
| 71 | 2023-02-14 15:00:00 | close | SELL | 0.02 | 1856.563 | -3.49 | force_close |  |
| | basket 33 | **force_close** | | | | **-15.27** | | 2 positions opened |
| 76 | 2023-02-15 04:01:37 | open | SELL | 0.01 | 1846.931 | +0.00 |  |  |
| 77 | 2023-02-15 04:27:30 | add | SELL | 0.02 | 1848.701 | +0.00 |  | add side -1, H1 MACD signal sign -1 |
| 78 | 2023-02-15 04:30:01 | close | SELL | 0.01 | 1848.511 | -1.58 | force_close |  |
| 79 | 2023-02-15 04:30:01 | close | SELL | 0.02 | 1848.511 | +0.38 | force_close |  |
| | basket 36 | **force_close** | | | | **-1.20** | | 2 positions opened |

### add gate EMA200 D1

419 rule checks, 0 failed; 1353 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.02 | 1860.492 | +0.00 |  | D1 close 1862.70 vs EMA200 1801.88, add side +1 |
| 2 | 2023-02-13 02:51:42 | close | BUY | 0.01 | 1861.278 | -0.42 | target |  |
| 3 | 2023-02-13 02:51:42 | close | BUY | 0.02 | 1861.278 | +1.57 | target |  |
| | basket 0 | **target** | | | | **+1.15** | | 2 positions opened |
| 4 | 2023-02-13 02:56:43 | open | BUY | 0.01 | 1862.318 | +0.00 |  |  |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.02 | 1860.422 | +0.00 |  | D1 close 1862.70 vs EMA200 1801.88, add side +1 |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.03 | 1859.501 | +0.00 |  | D1 close 1862.70 vs EMA200 1801.88, add side +1 |
| 7 | 2023-02-13 06:04:15 | close | BUY | 0.01 | 1860.526 | -1.79 | target |  |
| 8 | 2023-02-13 06:04:15 | close | BUY | 0.02 | 1860.526 | +0.21 | target |  |
| 9 | 2023-02-13 06:04:15 | close | BUY | 0.03 | 1860.526 | +3.08 | target |  |
| | basket 1 | **target** | | | | **+1.50** | | 3 positions opened |
| 16 | 2023-02-13 06:46:00 | open | BUY | 0.01 | 1865.157 | +0.00 |  |  |
| 17 | 2023-02-13 07:00:01 | add | BUY | 0.02 | 1862.682 | +0.00 |  | D1 close 1862.70 vs EMA200 1801.88, add side +1 |
| 18 | 2023-02-13 07:05:55 | close | BUY | 0.01 | 1863.870 | -1.29 | target |  |
| 19 | 2023-02-13 07:05:55 | close | BUY | 0.02 | 1863.870 | +2.38 | target |  |
| | basket 5 | **target** | | | | **+1.09** | | 2 positions opened |

### add gate ADX H1>30

570 rule checks, 0 failed; 1435 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.02 | 1860.492 | +0.00 |  | ADX(14, H1) 11.28 <= 30 |
| 2 | 2023-02-13 02:51:42 | close | BUY | 0.01 | 1861.278 | -0.42 | target |  |
| 3 | 2023-02-13 02:51:42 | close | BUY | 0.02 | 1861.278 | +1.57 | target |  |
| | basket 0 | **target** | | | | **+1.15** | | 2 positions opened |
| 4 | 2023-02-13 02:56:43 | open | BUY | 0.01 | 1862.318 | +0.00 |  |  |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.02 | 1860.422 | +0.00 |  | ADX(14, H1) 11.47 <= 30 |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.03 | 1859.501 | +0.00 |  | ADX(14, H1) 11.47 <= 30 |
| 7 | 2023-02-13 06:04:15 | close | BUY | 0.01 | 1860.526 | -1.79 | target |  |
| 8 | 2023-02-13 06:04:15 | close | BUY | 0.02 | 1860.526 | +0.21 | target |  |
| 9 | 2023-02-13 06:04:15 | close | BUY | 0.03 | 1860.526 | +3.08 | target |  |
| | basket 1 | **target** | | | | **+1.50** | | 3 positions opened |
| 16 | 2023-02-13 06:46:00 | open | BUY | 0.01 | 1865.157 | +0.00 |  |  |
| 17 | 2023-02-13 07:00:01 | add | BUY | 0.02 | 1862.682 | +0.00 |  | ADX(14, H1) 12.81 <= 30 |
| 18 | 2023-02-13 07:05:55 | close | BUY | 0.01 | 1863.870 | -1.29 | target |  |
| 19 | 2023-02-13 07:05:55 | close | BUY | 0.02 | 1863.870 | +2.38 | target |  |
| | basket 5 | **target** | | | | **+1.09** | | 2 positions opened |

### add gate abnormal day

770 rule checks, 0 failed; 1523 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.02 | 1860.492 | +0.00 |  | today -0.1295%, threshold 1.0499%, side +1 |
| 2 | 2023-02-13 02:51:42 | close | BUY | 0.01 | 1861.278 | -0.42 | target |  |
| 3 | 2023-02-13 02:51:42 | close | BUY | 0.02 | 1861.278 | +1.57 | target |  |
| | basket 0 | **target** | | | | **+1.15** | | 2 positions opened |
| 4 | 2023-02-13 02:56:43 | open | BUY | 0.01 | 1862.318 | +0.00 |  |  |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.02 | 1860.422 | +0.00 |  | today -0.1333%, threshold 1.0499%, side +1 |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.03 | 1859.501 | +0.00 |  | today -0.1827%, threshold 1.0499%, side +1 |
| 7 | 2023-02-13 06:04:15 | close | BUY | 0.01 | 1860.526 | -1.79 | target |  |
| 8 | 2023-02-13 06:04:15 | close | BUY | 0.02 | 1860.526 | +0.21 | target |  |
| 9 | 2023-02-13 06:04:15 | close | BUY | 0.03 | 1860.526 | +3.08 | target |  |
| | basket 1 | **target** | | | | **+1.50** | | 3 positions opened |
| 16 | 2023-02-13 06:46:00 | open | BUY | 0.01 | 1865.157 | +0.00 |  |  |
| 17 | 2023-02-13 07:00:01 | add | BUY | 0.02 | 1862.682 | +0.00 |  | today -0.0120%, threshold 1.0499%, side +1 |
| 18 | 2023-02-13 07:05:55 | close | BUY | 0.01 | 1863.870 | -1.29 | target |  |
| 19 | 2023-02-13 07:05:55 | close | BUY | 0.02 | 1863.870 | +2.38 | target |  |
| | basket 5 | **target** | | | | **+1.09** | | 2 positions opened |

### add gate 20:30-22:30

901 rule checks, 0 failed; 1592 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.02 | 1860.492 | +0.00 |  | add at 02:38 UTC |
| 2 | 2023-02-13 02:51:42 | close | BUY | 0.01 | 1861.278 | -0.42 | target |  |
| 3 | 2023-02-13 02:51:42 | close | BUY | 0.02 | 1861.278 | +1.57 | target |  |
| | basket 0 | **target** | | | | **+1.15** | | 2 positions opened |
| 4 | 2023-02-13 02:56:43 | open | BUY | 0.01 | 1862.318 | +0.00 |  |  |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.02 | 1860.422 | +0.00 |  | add at 03:45 UTC |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.03 | 1859.501 | +0.00 |  | add at 03:50 UTC |
| 7 | 2023-02-13 06:04:15 | close | BUY | 0.01 | 1860.526 | -1.79 | target |  |
| 8 | 2023-02-13 06:04:15 | close | BUY | 0.02 | 1860.526 | +0.21 | target |  |
| 9 | 2023-02-13 06:04:15 | close | BUY | 0.03 | 1860.526 | +3.08 | target |  |
| | basket 1 | **target** | | | | **+1.50** | | 3 positions opened |
| 16 | 2023-02-13 06:46:00 | open | BUY | 0.01 | 1865.157 | +0.00 |  |  |
| 17 | 2023-02-13 07:00:01 | add | BUY | 0.02 | 1862.682 | +0.00 |  | add at 07:00 UTC |
| 18 | 2023-02-13 07:05:55 | close | BUY | 0.01 | 1863.870 | -1.29 | target |  |
| 19 | 2023-02-13 07:05:55 | close | BUY | 0.02 | 1863.870 | +2.38 | target |  |
| | basket 5 | **target** | | | | **+1.09** | | 2 positions opened |

### Friday flat

1611 rule checks, 0 failed; 1604 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  | open at minute-of-week 105 |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.02 | 1860.492 | +0.00 |  |  |
| 2 | 2023-02-13 02:51:42 | close | BUY | 0.01 | 1861.278 | -0.42 | target |  |
| 3 | 2023-02-13 02:51:42 | close | BUY | 0.02 | 1861.278 | +1.57 | target |  |
| | basket 0 | **target** | | | | **+1.15** | | 2 positions opened |
| 4 | 2023-02-13 02:56:43 | open | BUY | 0.01 | 1862.318 | +0.00 |  | open at minute-of-week 176 |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.02 | 1860.422 | +0.00 |  |  |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.03 | 1859.501 | +0.00 |  |  |
| 7 | 2023-02-13 06:04:15 | close | BUY | 0.01 | 1860.526 | -1.79 | target |  |
| 8 | 2023-02-13 06:04:15 | close | BUY | 0.02 | 1860.526 | +0.21 | target |  |
| 9 | 2023-02-13 06:04:15 | close | BUY | 0.03 | 1860.526 | +3.08 | target |  |
| | basket 1 | **target** | | | | **+1.50** | | 3 positions opened |
| 10 | 2023-02-13 06:09:16 | open | BUY | 0.01 | 1861.324 | +0.00 |  | open at minute-of-week 369 |
| 11 | 2023-02-13 06:23:03 | close | BUY | 0.01 | 1862.379 | +1.05 | target |  |
| | basket 2 | **target** | | | | **+1.05** | | 1 positions opened |

### entry gate ATR pct

1228 rule checks, 0 failed; 1229 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  | ATR(H4) 9.201 <= q90 10.707 |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.02 | 1860.492 | +0.00 |  |  |
| 2 | 2023-02-13 02:51:42 | close | BUY | 0.01 | 1861.278 | -0.42 | target |  |
| 3 | 2023-02-13 02:51:42 | close | BUY | 0.02 | 1861.278 | +1.57 | target |  |
| | basket 0 | **target** | | | | **+1.15** | | 2 positions opened |
| 4 | 2023-02-13 02:56:43 | open | BUY | 0.01 | 1862.318 | +0.00 |  | ATR(H4) 9.201 <= q90 10.707 |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.02 | 1860.422 | +0.00 |  |  |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.03 | 1859.501 | +0.00 |  |  |
| 7 | 2023-02-13 06:04:15 | close | BUY | 0.01 | 1860.526 | -1.79 | target |  |
| 8 | 2023-02-13 06:04:15 | close | BUY | 0.02 | 1860.526 | +0.21 | target |  |
| 9 | 2023-02-13 06:04:15 | close | BUY | 0.03 | 1860.526 | +3.08 | target |  |
| | basket 1 | **target** | | | | **+1.50** | | 3 positions opened |
| 10 | 2023-02-13 06:09:16 | open | BUY | 0.01 | 1861.324 | +0.00 |  | ATR(H4) 8.954 <= q90 10.707 |
| 11 | 2023-02-13 06:23:03 | close | BUY | 0.01 | 1862.379 | +1.05 | target |  |
| | basket 2 | **target** | | | | **+1.05** | | 1 positions opened |

### confirm Supertrend H4

590 rule checks, 0 failed; 591 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 09:38:01 | open | SELL | 0.01 | 1856.179 | +0.00 |  | Supertrend(H4) -1, basket side -1 |
| 1 | 2023-02-13 09:45:08 | close | SELL | 0.01 | 1855.121 | +1.06 | target |  |
| | basket 0 | **target** | | | | **+1.06** | | 1 positions opened |
| 2 | 2023-02-13 16:04:49 | open | SELL | 0.01 | 1852.737 | +0.00 |  | Supertrend(H4) -1, basket side -1 |
| 3 | 2023-02-13 16:05:42 | close | SELL | 0.01 | 1854.356 | -1.62 | force_close |  |
| | basket 1 | **force_close** | | | | **-1.62** | | 1 positions opened |
| 4 | 2023-02-13 16:11:38 | open | SELL | 0.01 | 1852.854 | +0.00 |  | Supertrend(H4) -1, basket side -1 |
| 5 | 2023-02-13 16:46:49 | add | SELL | 0.02 | 1854.476 | +0.00 |  |  |
| 6 | 2023-02-13 16:46:51 | close | SELL | 0.01 | 1854.804 | -1.95 | force_close |  |
| 7 | 2023-02-13 16:46:51 | close | SELL | 0.02 | 1854.804 | -0.66 | force_close |  |
| | basket 2 | **force_close** | | | | **-2.61** | | 2 positions opened |

### side D1 RSI

1572 rule checks, 0 failed; 1573 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  | D1 forming RSI 40.68, side +1 |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.02 | 1860.492 | +0.00 |  |  |
| 2 | 2023-02-13 02:51:42 | close | BUY | 0.01 | 1861.278 | -0.42 | target |  |
| 3 | 2023-02-13 02:51:42 | close | BUY | 0.02 | 1861.278 | +1.57 | target |  |
| | basket 0 | **target** | | | | **+1.15** | | 2 positions opened |
| 4 | 2023-02-13 02:56:43 | open | BUY | 0.01 | 1862.318 | +0.00 |  | D1 forming RSI 40.87, side +1 |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.02 | 1860.422 | +0.00 |  |  |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.03 | 1859.501 | +0.00 |  |  |
| 7 | 2023-02-13 06:04:15 | close | BUY | 0.01 | 1860.526 | -1.79 | target |  |
| 8 | 2023-02-13 06:04:15 | close | BUY | 0.02 | 1860.526 | +0.21 | target |  |
| 9 | 2023-02-13 06:04:15 | close | BUY | 0.03 | 1860.526 | +3.08 | target |  |
| | basket 1 | **target** | | | | **+1.50** | | 3 positions opened |
| 10 | 2023-02-13 06:09:16 | open | BUY | 0.01 | 1861.324 | +0.00 |  | D1 forming RSI 40.56, side +1 |
| 11 | 2023-02-13 06:23:03 | close | BUY | 0.01 | 1862.379 | +1.05 | target |  |
| | basket 2 | **target** | | | | **+1.05** | | 1 positions opened |

### stop-and-reverse x1

550 rule checks, 0 failed; 1815 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 66 | 2023-02-13 15:42:59 | open | BUY | 0.01 | 1858.266 | +0.00 |  |  |
| 67 | 2023-02-13 16:02:51 | add | BUY | 0.02 | 1854.411 | +0.00 |  |  |
| 68 | 2023-02-13 16:04:49 | close | BUY | 0.01 | 1852.802 | -5.46 | force_close | force_close: a reversal follows |
| 69 | 2023-02-13 16:04:49 | close | BUY | 0.02 | 1852.802 | -3.22 | force_close |  |
| | basket 19 | **force_close** | | | | **-8.68** | | 2 positions opened |
| 70 | 2023-02-13 16:04:50 | open | SELL | 0.01 | 1852.711 | +0.00 |  | basket 19 force_close -> reverse -1 x1 after 1.1s |
| 71 | 2023-02-13 16:05:43 | close | SELL | 0.01 | 1854.454 | -1.74 | force_close |  |
| | basket 20 | **force_close** | | | | **-1.74** | | 1 positions opened |
| 72 | 2023-02-13 16:11:38 | open | SELL | 0.01 | 1852.854 | +0.00 |  |  |
| 73 | 2023-02-13 16:46:49 | add | SELL | 0.02 | 1854.476 | +0.00 |  |  |
| 74 | 2023-02-13 16:46:51 | close | SELL | 0.01 | 1854.804 | -1.95 | force_close | force_close: a reversal follows |
| 75 | 2023-02-13 16:46:51 | close | SELL | 0.02 | 1854.804 | -0.66 | force_close |  |
| | basket 21 | **force_close** | | | | **-2.61** | | 2 positions opened |

### stop-and-reverse x2

550 rule checks, 0 failed; 1815 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 66 | 2023-02-13 15:42:59 | open | BUY | 0.01 | 1858.266 | +0.00 |  |  |
| 67 | 2023-02-13 16:02:51 | add | BUY | 0.02 | 1854.411 | +0.00 |  |  |
| 68 | 2023-02-13 16:04:49 | close | BUY | 0.01 | 1852.802 | -5.46 | force_close | force_close: a reversal follows |
| 69 | 2023-02-13 16:04:49 | close | BUY | 0.02 | 1852.802 | -3.22 | force_close |  |
| | basket 19 | **force_close** | | | | **-8.68** | | 2 positions opened |
| 70 | 2023-02-13 16:04:50 | open | SELL | 0.02 | 1852.711 | +0.00 |  | basket 19 force_close -> reverse -1 x2 after 1.1s |
| 71 | 2023-02-13 16:05:43 | close | SELL | 0.02 | 1854.454 | -3.49 | force_close |  |
| | basket 20 | **force_close** | | | | **-3.49** | | 1 positions opened |
| 72 | 2023-02-13 16:11:38 | open | SELL | 0.01 | 1852.854 | +0.00 |  |  |
| 73 | 2023-02-13 16:46:49 | add | SELL | 0.02 | 1854.476 | +0.00 |  |  |
| 74 | 2023-02-13 16:46:51 | close | SELL | 0.01 | 1854.804 | -1.95 | force_close | force_close: a reversal follows |
| 75 | 2023-02-13 16:46:51 | close | SELL | 0.02 | 1854.804 | -0.66 | force_close |  |
| | basket 21 | **force_close** | | | | **-2.61** | | 2 positions opened |

### hedge-on-depth

86 rule checks, 0 failed; 1550 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 132 | 2023-02-14 15:44:26 | open | BUY | 0.01 | 1855.629 | +0.00 |  |  |
| 133 | 2023-02-14 15:44:27 | add | BUY | 0.02 | 1855.783 | +0.00 |  |  |
| 134 | 2023-02-14 16:40:44 | add | BUY | 0.03 | 1844.574 | +0.00 |  |  |
| 135 | 2023-02-14 16:40:46 | add | BUY | 0.05 | 1844.085 | +0.00 |  |  |
| 136 | 2023-02-14 16:40:48 | add | BUY | 0.08 | 1844.693 | +0.00 |  |  |
| 137 | 2023-02-14 16:40:51 | add | BUY | 0.13 | 1844.791 | +0.00 |  |  |
| 138 | 2023-02-14 16:40:53 | hedge | SELL | 0.32 | 1844.514 | +0.00 |  | hedge 0.32 lots vs ladder 0.32, floating -36.73 (first), tier-1 RSI 25.62 |
| 139 | 2023-02-14 18:00:50 | close | SELL | 0.32 | 1850.299 | -185.12 | hedge_unwind | unwind: tier-1 RSI 65.03 |
| 140 | 2023-02-14 18:02:00 | close | BUY | 0.01 | 1851.725 | -3.90 | target |  |
| 141 | 2023-02-14 18:02:00 | close | BUY | 0.02 | 1851.725 | -8.12 | target |  |
| 142 | 2023-02-14 18:02:00 | close | BUY | 0.03 | 1851.725 | +21.45 | target |  |
| 143 | 2023-02-14 18:02:00 | close | BUY | 0.05 | 1851.725 | +38.20 | target |  |
| 144 | 2023-02-14 18:02:00 | close | BUY | 0.08 | 1851.725 | +56.26 | target |  |
| 145 | 2023-02-14 18:02:00 | close | BUY | 0.13 | 1851.725 | +90.14 | target | net target: floating 194.03 + realised -185.12 = 8.91 > 1.00 |
| | basket 45 | **target** | | | | **+8.91** | | 7 positions opened |
| 166 | 2023-02-15 04:35:01 | open | BUY | 0.01 | 1847.652 | +0.00 |  |  |
| 167 | 2023-02-15 05:01:53 | add | BUY | 0.02 | 1847.095 | +0.00 |  |  |
| 168 | 2023-02-15 05:01:55 | add | BUY | 0.03 | 1847.054 | +0.00 |  |  |
| 169 | 2023-02-15 05:01:58 | add | BUY | 0.05 | 1847.055 | +0.00 |  |  |
| 170 | 2023-02-15 05:03:43 | add | BUY | 0.08 | 1845.447 | +0.00 |  |  |
| 171 | 2023-02-15 05:03:45 | add | BUY | 0.13 | 1845.591 | +0.00 |  |  |
| 172 | 2023-02-15 05:03:47 | hedge | SELL | 0.32 | 1845.278 | +0.00 |  | hedge 0.32 lots vs ladder 0.32, floating -25.64 (first), tier-1 RSI 19.77 |
| 173 | 2023-02-15 07:28:10 | close | SELL | 0.32 | 1844.774 | +16.13 | hedge_unwind | unwind: tier-1 RSI 65.03 |
| 174 | 2023-02-15 07:28:22 | close | BUY | 0.01 | 1843.787 | -3.87 | hedge_stop |  |
| 175 | 2023-02-15 07:28:22 | close | BUY | 0.02 | 1843.787 | -6.62 | hedge_stop |  |
| 176 | 2023-02-15 07:28:22 | close | BUY | 0.03 | 1843.787 | -9.80 | hedge_stop |  |
| 177 | 2023-02-15 07:28:22 | close | BUY | 0.05 | 1843.787 | -16.34 | hedge_stop |  |
| 178 | 2023-02-15 07:28:22 | close | BUY | 0.08 | 1843.787 | -13.28 | hedge_stop |  |
| 179 | 2023-02-15 07:28:22 | close | BUY | 0.13 | 1843.787 | -23.45 | hedge_stop | net stop: floating -73.36 + realised 16.13 = -57.23 <= 2 x -25.64 |
| | basket 52 | **hedge_stop** | | | | **-57.23** | | 7 positions opened |
| 280 | 2023-02-17 01:43:56 | open | BUY | 0.01 | 1831.977 | +0.00 |  |  |
| 281 | 2023-02-17 01:45:42 | add | BUY | 0.02 | 1830.897 | +0.00 |  |  |
| 282 | 2023-02-17 01:46:11 | add | BUY | 0.03 | 1830.542 | +0.00 |  |  |
| 283 | 2023-02-17 01:46:13 | add | BUY | 0.05 | 1830.491 | +0.00 |  |  |
| 284 | 2023-02-17 06:27:54 | add | BUY | 0.08 | 1825.472 | +0.00 |  |  |
| 285 | 2023-02-17 06:27:57 | add | BUY | 0.13 | 1825.474 | +0.00 |  |  |
| 286 | 2023-02-17 06:27:59 | hedge | SELL | 0.32 | 1825.262 | +0.00 |  | hedge 0.32 lots vs ladder 0.32, floating -64.42 (first), tier-1 RSI 27.94 |
| 287 | 2023-02-17 07:23:46 | close | BUY | 0.01 | 1822.146 | -9.83 | force_close |  |
| 288 | 2023-02-17 07:23:46 | close | BUY | 0.02 | 1822.146 | -17.50 | force_close |  |
| 289 | 2023-02-17 07:23:46 | close | BUY | 0.03 | 1822.146 | -25.19 | force_close |  |
| 290 | 2023-02-17 07:23:46 | close | BUY | 0.05 | 1822.146 | -41.73 | force_close |  |
| 291 | 2023-02-17 07:23:46 | close | BUY | 0.08 | 1822.146 | -26.61 | force_close |  |
| 292 | 2023-02-17 07:23:46 | close | BUY | 0.13 | 1822.146 | -43.26 | force_close |  |
| 293 | 2023-02-17 07:23:46 | close | SELL | 0.32 | 1822.346 | +93.31 | force_close |  |
| | basket 92 | **force_close** | | | | **-70.81** | | 7 positions opened |

### counter-ladder

164 rule checks, 0 failed; 1116 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 04:41:55 | add | SELL | 0.02 | 1857.894 | +0.00 |  | add 1 on side -1 (basket +1), moved 3.604 >= 2.236, lots 0.02 |
| 2 | 2023-02-13 07:45:00 | close | BUY | 0.01 | 1863.515 | +1.82 | force_close |  |
| 3 | 2023-02-13 07:45:00 | close | SELL | 0.02 | 1863.715 | -11.64 | force_close |  |
| | basket 0 | **force_close** | | | | **-9.82** | | 2 positions opened |
| 18 | 2023-02-13 13:00:47 | open | BUY | 0.01 | 1862.078 | +0.00 |  |  |
| 19 | 2023-02-13 14:34:41 | add | SELL | 0.02 | 1854.891 | +0.00 |  | add 1 on side -1 (basket +1), moved 6.987 >= 2.192, lots 0.02 |
| 20 | 2023-02-13 16:04:50 | close | BUY | 0.01 | 1852.711 | -9.37 | force_close |  |
| 21 | 2023-02-13 16:04:50 | close | SELL | 0.02 | 1852.911 | +3.96 | force_close |  |
| | basket 8 | **force_close** | | | | **-5.41** | | 2 positions opened |
| 68 | 2023-02-14 14:36:06 | open | SELL | 0.01 | 1844.515 | +0.00 |  |  |
| 69 | 2023-02-14 14:59:16 | add | BUY | 0.02 | 1857.472 | +0.00 |  | add 1 on side +1 (basket -1), moved 12.757 >= 2.018, lots 0.02 |
| 70 | 2023-02-14 15:00:00 | close | SELL | 0.01 | 1856.819 | -12.30 | force_close |  |
| 71 | 2023-02-14 15:00:00 | close | BUY | 0.02 | 1856.619 | -1.71 | force_close |  |
| | basket 32 | **force_close** | | | | **-14.01** | | 2 positions opened |

### partial LIFO

666 rule checks, 0 failed; 863 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.02 | 1860.492 | +0.00 |  |  |
| 2 | 2023-02-13 02:49:42 | close | BUY | 0.02 | 1861.060 | +1.14 | partial | closed the newest leg (opened 02:38:12) at +1.14 > 1 |
| 3 | 2023-02-13 03:45:59 | add | BUY | 0.02 | 1860.422 | +0.00 |  |  |
| 4 | 2023-02-13 03:50:31 | add | BUY | 0.03 | 1859.501 | +0.00 |  |  |
| 5 | 2023-02-13 05:21:21 | close | BUY | 0.03 | 1859.865 | +1.09 | partial | closed the newest leg (opened 03:50:31) at +1.09 > 1 |
| 6 | 2023-02-13 06:04:37 | close | BUY | 0.02 | 1860.989 | +1.13 | partial | closed the newest leg (opened 03:45:59) at +1.13 > 1 |
| 7 | 2023-02-13 06:25:59 | close | BUY | 0.01 | 1863.066 | +1.37 | target |  |
| | basket 0 | **target** | | | | **+4.73** | | 4 positions opened |
| 12 | 2023-02-13 06:46:21 | open | BUY | 0.01 | 1864.861 | +0.00 |  |  |
| 13 | 2023-02-13 07:00:01 | add | BUY | 0.02 | 1862.682 | +0.00 |  |  |
| 14 | 2023-02-13 07:01:51 | close | BUY | 0.02 | 1863.194 | +1.02 | partial | closed the newest leg (opened 07:00:01) at +1.02 > 1 |
| 15 | 2023-02-13 07:45:00 | close | BUY | 0.01 | 1863.515 | -1.35 | force_close |  |
| | basket 3 | **force_close** | | | | **-0.33** | | 2 positions opened |
| 28 | 2023-02-13 12:00:45 | open | BUY | 0.01 | 1862.607 | +0.00 |  |  |
| 29 | 2023-02-13 12:06:18 | add | BUY | 0.02 | 1860.988 | +0.00 |  |  |
| 30 | 2023-02-13 12:17:35 | close | BUY | 0.02 | 1861.492 | +1.01 | partial | closed the newest leg (opened 12:06:18) at +1.01 > 1 |
| 31 | 2023-02-13 12:37:45 | add | BUY | 0.02 | 1860.138 | +0.00 |  |  |
| 32 | 2023-02-13 12:46:57 | close | BUY | 0.02 | 1860.643 | +1.01 | partial | closed the newest leg (opened 12:37:45) at +1.01 > 1 |
| 33 | 2023-02-13 13:13:26 | add | BUY | 0.02 | 1859.746 | +0.00 |  |  |
| 34 | 2023-02-13 13:21:42 | add | BUY | 0.03 | 1858.023 | +0.00 |  |  |
| 35 | 2023-02-13 13:22:05 | close | BUY | 0.03 | 1858.552 | +1.59 | partial | closed the newest leg (opened 13:21:42) at +1.59 > 1 |
| 36 | 2023-02-13 13:22:11 | add | BUY | 0.03 | 1858.028 | +0.00 |  |  |
| 37 | 2023-02-13 13:23:58 | close | BUY | 0.03 | 1858.406 | +1.13 | partial | closed the newest leg (opened 13:22:11) at +1.13 > 1 |
| 38 | 2023-02-13 13:26:12 | add | BUY | 0.03 | 1857.983 | +0.00 |  |  |
| 39 | 2023-02-13 13:26:43 | close | BUY | 0.03 | 1858.490 | +1.52 | partial | closed the newest leg (opened 13:26:12) at +1.52 > 1 |
| 40 | 2023-02-13 13:29:36 | add | BUY | 0.03 | 1858.090 | +0.00 |  |  |
| 41 | 2023-02-13 14:06:19 | close | BUY | 0.03 | 1858.480 | +1.17 | partial | closed the newest leg (opened 13:29:36) at +1.17 > 1 |
| 42 | 2023-02-13 14:34:52 | add | BUY | 0.03 | 1854.922 | +0.00 |  |  |
| 43 | 2023-02-13 14:34:54 | add | BUY | 0.05 | 1854.578 | +0.00 |  |  |
| 44 | 2023-02-13 14:35:03 | close | BUY | 0.05 | 1854.981 | +2.02 | partial | closed the newest leg (opened 14:34:54) at +2.02 > 1 |
| 45 | 2023-02-13 14:35:47 | add | BUY | 0.05 | 1854.561 | +0.00 |  |  |
| 46 | 2023-02-13 14:36:20 | close | BUY | 0.05 | 1854.770 | +1.05 | partial | closed the newest leg (opened 14:35:47) at +1.05 > 1 |
| 47 | 2023-02-13 14:36:23 | close | BUY | 0.03 | 1855.398 | +1.43 | partial | closed the newest leg (opened 14:34:52) at +1.43 > 1 |
| 48 | 2023-02-13 16:04:49 | close | BUY | 0.01 | 1852.675 | -9.93 | force_close |  |
| 49 | 2023-02-13 16:04:49 | close | BUY | 0.02 | 1852.675 | -14.14 | force_close |  |
| | basket 10 | **force_close** | | | | **-12.14** | | 11 positions opened |

### partial overlap

271 rule checks, 0 failed; 1626 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  |  |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.02 | 1860.492 | +0.00 |  |  |
| 2 | 2023-02-13 02:49:54 | close | BUY | 0.01 | 1861.107 | -0.59 | overlap | newest +1.23 + oldest -0.59 >= spread cost 0.60 |
| 3 | 2023-02-13 02:49:54 | close | BUY | 0.02 | 1861.107 | +1.23 | overlap |  |
| | basket 0 | **overlap** | | | | **+0.64** | | 2 positions opened |
| 4 | 2023-02-13 02:54:54 | open | BUY | 0.01 | 1861.647 | +0.00 |  |  |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.02 | 1860.422 | +0.00 |  |  |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.03 | 1859.501 | +0.00 |  |  |
| 7 | 2023-02-13 05:44:05 | close | BUY | 0.03 | 1860.243 | +2.23 | partial | newest +2.23 + oldest -1.40 >= spread cost 0.80 |
| 8 | 2023-02-13 05:44:05 | close | BUY | 0.01 | 1860.243 | -1.40 | partial |  |
| 9 | 2023-02-13 06:04:37 | close | BUY | 0.02 | 1860.989 | +1.13 | target |  |
| | basket 1 | **target** | | | | **+1.96** | | 3 positions opened |
| 32 | 2023-02-13 12:00:45 | open | BUY | 0.01 | 1862.607 | +0.00 |  |  |
| 33 | 2023-02-13 12:06:18 | add | BUY | 0.02 | 1860.988 | +0.00 |  |  |
| 34 | 2023-02-13 12:17:45 | close | BUY | 0.01 | 1861.766 | -0.84 | overlap | newest +1.56 + oldest -0.84 >= spread cost 0.60 |
| 35 | 2023-02-13 12:17:45 | close | BUY | 0.02 | 1861.766 | +1.56 | overlap |  |
| | basket 12 | **overlap** | | | | **+0.72** | | 2 positions opened |

### sizing pre-funded

1595 rule checks, 0 failed; 1596 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  | unit 1 = formula 1 (balance 2000.00, ATR(D1) 21.930) |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.02 | 1860.492 | +0.00 |  |  |
| 2 | 2023-02-13 02:51:42 | close | BUY | 0.01 | 1861.278 | -0.42 | target |  |
| 3 | 2023-02-13 02:51:42 | close | BUY | 0.02 | 1861.278 | +1.57 | target |  |
| | basket 0 | **target** | | | | **+1.15** | | 2 positions opened |
| 4 | 2023-02-13 02:56:43 | open | BUY | 0.01 | 1862.318 | +0.00 |  | unit 1 = formula 1 (balance 2001.15, ATR(D1) 21.930) |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.02 | 1860.422 | +0.00 |  |  |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.03 | 1859.501 | +0.00 |  |  |
| 7 | 2023-02-13 06:04:15 | close | BUY | 0.01 | 1860.526 | -1.79 | target |  |
| 8 | 2023-02-13 06:04:15 | close | BUY | 0.02 | 1860.526 | +0.21 | target |  |
| 9 | 2023-02-13 06:04:15 | close | BUY | 0.03 | 1860.526 | +3.08 | target |  |
| | basket 1 | **target** | | | | **+1.50** | | 3 positions opened |
| 10 | 2023-02-13 06:09:16 | open | BUY | 0.01 | 1861.324 | +0.00 |  | unit 1 = formula 1 (balance 2002.65, ATR(D1) 21.930) |
| 11 | 2023-02-13 06:23:03 | close | BUY | 0.01 | 1862.379 | +1.05 | target |  |
| | basket 2 | **target** | | | | **+1.05** | | 1 positions opened |

### sizing vol-target

1595 rule checks, 0 failed; 1596 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.01 | 1861.698 | +0.00 |  | unit 1 = formula 1 (balance 2000.00, ATR(D1) 21.930) |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.02 | 1860.492 | +0.00 |  |  |
| 2 | 2023-02-13 02:51:42 | close | BUY | 0.01 | 1861.278 | -0.42 | target |  |
| 3 | 2023-02-13 02:51:42 | close | BUY | 0.02 | 1861.278 | +1.57 | target |  |
| | basket 0 | **target** | | | | **+1.15** | | 2 positions opened |
| 4 | 2023-02-13 02:56:43 | open | BUY | 0.01 | 1862.318 | +0.00 |  | unit 1 = formula 1 (balance 2001.15, ATR(D1) 21.930) |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.02 | 1860.422 | +0.00 |  |  |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.03 | 1859.501 | +0.00 |  |  |
| 7 | 2023-02-13 06:04:15 | close | BUY | 0.01 | 1860.526 | -1.79 | target |  |
| 8 | 2023-02-13 06:04:15 | close | BUY | 0.02 | 1860.526 | +0.21 | target |  |
| 9 | 2023-02-13 06:04:15 | close | BUY | 0.03 | 1860.526 | +3.08 | target |  |
| | basket 1 | **target** | | | | **+1.50** | | 3 positions opened |
| 10 | 2023-02-13 06:09:16 | open | BUY | 0.01 | 1861.324 | +0.00 |  | unit 1 = formula 1 (balance 2002.65, ATR(D1) 21.930) |
| 11 | 2023-02-13 06:23:03 | close | BUY | 0.01 | 1862.379 | +1.05 | target |  |
| | basket 2 | **target** | | | | **+1.05** | | 1 positions opened |

### sizing vol-target k x3

470 rule checks, 0 failed; 471 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.03 | 1861.698 | +0.00 |  | unit 3 = formula 3 (balance 2000.00, ATR(D1) 21.930) |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.06 | 1860.492 | +0.00 |  |  |
| 2 | 2023-02-13 02:51:42 | close | BUY | 0.03 | 1861.278 | -1.26 | target |  |
| 3 | 2023-02-13 02:51:42 | close | BUY | 0.06 | 1861.278 | +4.72 | target |  |
| | basket 0 | **target** | | | | **+3.46** | | 2 positions opened |
| 4 | 2023-02-13 02:56:43 | open | BUY | 0.03 | 1862.318 | +0.00 |  | unit 3 = formula 3 (balance 2003.46, ATR(D1) 21.930) |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.06 | 1860.422 | +0.00 |  |  |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.09 | 1859.501 | +0.00 |  |  |
| 7 | 2023-02-13 06:04:15 | close | BUY | 0.03 | 1860.526 | -5.38 | target |  |
| 8 | 2023-02-13 06:04:15 | close | BUY | 0.06 | 1860.526 | +0.62 | target |  |
| 9 | 2023-02-13 06:04:15 | close | BUY | 0.09 | 1860.526 | +9.23 | target |  |
| | basket 1 | **target** | | | | **+4.47** | | 3 positions opened |
| 10 | 2023-02-13 06:09:16 | open | BUY | 0.03 | 1861.324 | +0.00 |  | unit 3 = formula 3 (balance 2007.93, ATR(D1) 21.930) |
| 11 | 2023-02-13 06:23:03 | close | BUY | 0.03 | 1862.379 | +3.16 | target |  |
| | basket 2 | **target** | | | | **+3.16** | | 1 positions opened |

### sizing pre-funded $20,000

1591 rule checks, 0 failed; 1592 accounting checks, 0 failed. 

| fill | time (UTC) | action | side | lots | price | P/L | reason | check |
|---|---|---|---|---|---|---|---|---|
| 0 | 2023-02-13 01:45:00 | open | BUY | 0.05 | 1861.698 | +0.00 |  | unit 5 = formula 5 (balance 20000.00, ATR(D1) 21.930) |
| 1 | 2023-02-13 02:38:12 | add | BUY | 0.10 | 1860.492 | +0.00 |  |  |
| 2 | 2023-02-13 02:51:42 | close | BUY | 0.05 | 1861.278 | -2.10 | target |  |
| 3 | 2023-02-13 02:51:42 | close | BUY | 0.10 | 1861.278 | +7.86 | target |  |
| | basket 0 | **target** | | | | **+5.76** | | 2 positions opened |
| 4 | 2023-02-13 02:56:43 | open | BUY | 0.05 | 1862.318 | +0.00 |  | unit 5 = formula 5 (balance 20005.76, ATR(D1) 21.930) |
| 5 | 2023-02-13 03:45:59 | add | BUY | 0.10 | 1860.422 | +0.00 |  |  |
| 6 | 2023-02-13 03:50:31 | add | BUY | 0.15 | 1859.501 | +0.00 |  |  |
| 7 | 2023-02-13 06:04:15 | close | BUY | 0.05 | 1860.526 | -8.96 | target |  |
| 8 | 2023-02-13 06:04:15 | close | BUY | 0.10 | 1860.526 | +1.04 | target |  |
| 9 | 2023-02-13 06:04:15 | close | BUY | 0.15 | 1860.526 | +15.38 | target |  |
| | basket 1 | **target** | | | | **+7.46** | | 3 positions opened |
| 10 | 2023-02-13 06:09:16 | open | BUY | 0.05 | 1861.324 | +0.00 |  | unit 5 = formula 5 (balance 20013.22, ATR(D1) 21.930) |
| 11 | 2023-02-13 06:23:03 | close | BUY | 0.05 | 1862.379 | +5.27 | target |  |
| | basket 2 | **target** | | | | **+5.27** | | 1 positions opened |
