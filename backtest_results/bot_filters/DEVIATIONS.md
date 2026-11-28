# Deviations from the pre-registration

Each entry is written before the result it could affect exists: the date, what changed against `PREREG.md`, why, and
which results it can move. Entries are appended, never edited.

## Readings written on 28 Nov 2026 (IST) with the study code (`bot_filters.py`), before any filter variant's result existed

They read the plan where it is silent. Only item 13 changes anything, and only the order of the runs.

1. **The profit floor when the base loses.** When the base's mean profit per quarter is 0 or below, the Development
   floor is the base's own mean (the exam's convention in PREREG 6). Every floor comparison allows 1e-9 of the base,
   because 0.9 x 100 is 90.00000000000001 in floating point.
2. **Warm-up follows Pine** (a comparison with na is false). SIDE, SLOPE, TREND, CROSS, TSI, LARSI, VWRSI, RIB, MSD
   and HA allow neither side before their first value. LGATE200 and SGATE200 keep their "always" side. QQE is gray
   (both sides allowed) before its Bollinger band exists.
3. **Filter history** starts at the store's first bar: gold 2016-01-03 (its 2016 months were downloaded for study 2),
   BTC 2018-01-01. Each row records it in `history_from`. It is warm-up only; no Development window starts before
   2021-01-01.
4. **Sessions.** SESS-KZ and SESS-LN read the poll's New York hour, with steps exactly on UTC hour boundaries and
   [start, end). On the Turtle's M1-bar model they read the fill bar's open.
5. **MSD** uses the port's `rows_for(mk)`, whose weekly row knows the data end, and its int8 label (above 0 long,
   below 0 short).
6. **The Turtle's Heikin Ashi exits.** HA-M1 exits on a colour flip against the position. HA-M4 exits on the script's
   `rareNow` (lines 209-212), computed causally from at least 50 finished streaks.
7. After an H4 Heikin Ashi exit the Turtle's orders stay cancelled until its next D1 decision. After a D1 exit that
   decision row re-arms at once.
8. **Stage 2.** "Filters that beat the base's score" means a score strictly above the base's. Ties go to the higher
   mean profit per quarter, then to the id.
9. **Multiple testing.** SPA uses a mean block of 8 weeks (in days), 5,000 resamples and seed 20261128, over singles,
   pairs and exits. The deflated Sharpe is reported for the best five-year daily Sharpe and for the best
   Development score. The exam's window score is the mean net per quarter / max(worst quarter's DD, 1).
10. **The Turtle's identity** was checked on the five-year account ($3,546.56), not on the eight-year one of PREREG 2
    ($7,814.72), because the eight-year window reads the sealed T1.
11. **BTC Top 2's tick identity** runs alone, later: at the build there were 7.52 and 8.06 GB free or inactive, below
    the 9 GB the plan asks for. `run_dev` refuses every BTC variant unless the identity holds on all 24 accounts.
12. **The Turtle's Heikin Ashi exits are kept.** They are built from `PathPlan` rows, so `external.py` is not edited.
13. **Order of the runs (study 2's hold-out).** Development runs to 2026-11-13, so it covers study 2's sealed hold-out
    (from 2024-07-01). The rows that read study 2's ports (RIB, MSD and HA on H1/H4/D1: 9 per design, and the Turtle's
    4 exits) therefore run only after study 2's `FINALISTS.md` is frozen. So do stage 2 (the pairs, chosen from all
    singles) and everything after it. The other 50 singles of each design use no study-2 indicator and run first.
    This moves no result; it only keeps study 2's hold-out unseen until its freeze.
