# Research hand-off: from Alcadeias (MT5 on Exness) to Ballom_Fyers (Indian options on Fyers)

Written on 16 Nov 2026, about 03:00 IST, in the Alcadeias repo (`/Users/sidharthsingh/Desktop/Alcadeias/Alcadeias`, branch `backtest_hedging`, HEAD `bed551e`). It was assembled from four drafts compiled read-only on 16 Nov 2026 and from the four maps saved in `docs/handoff/`. A fact-check then corrected it and the maps against their sources, between about 03:45 and 04:15 IST. The repository states in §0.5, §1.2, §5.7, §5.9 and §5.13 are as checked at about 03:55 IST.

**Who it is for.**
- A future assistant session opened in the Ballom_Fyers repo. That session will not see this project's memory, so everything it needs from Alcadeias is written here or linked from here.
- The owner.

**What it holds.**
- The owner's setup and rules (§1).
- The old "Live" logic, which Ballom is said to run too, and what the backtests measured when it was replayed on real ticks (§2).
- How strategies were tested here, every pitfall the reviews found, and a checklist for trusting a new backtester (§3).
- What the research found, ending with the ten most important conclusions (§4).
- The designs and their levers with exact semantics, the six demo branches, and the engineering and safety checklist from porting them (§5).
- What this means for Ballom: what transfers, what does not, the data needed, a phased plan, the questions to ask first, and the first prompts (§6).
- An index of files and commands (§7).

---

## 0. How to use this file

### 0.1 Reading order

1. Read §0, §1 and §6 first: the rules, and the plan for Ballom.
2. Read §2 before mapping Ballom. It is the logic Ballom is said to run.
3. Read §3 to §5 when you build the backtester, measure the old logic, and port anything.
4. Open the maps in `docs/handoff/` when you need line-level detail:

| Map | What it gives |
|---|---|
| `docs/handoff/live_loop_map.md` | The live MT5 loop of v3.9.2, line by line: start-up, one poll, votes, scores, exits, ladder, sizing, execution, every constant and who reads it, and where each design lever would land in the live code |
| `docs/handoff/levers_map.md` | Every backtest lever of the demo designs: live default, kernel code, the poll and the bar it is read on, port traps, effective parameter sets, basket statistics, expected values for a port's tests |
| `docs/handoff/turtle_map.md` | The two BTC Turtle rows: data, N, channels, the System 1 filter, order and stop execution on M1 bars, the vote gate, sizing, results, and what a live port needs |
| `docs/handoff/parity_map.md` | The parity harness: the reference replay of a branch's own `app.py` against a simulated broker, what is compared and with which tolerances, cost, the port rules that keep parity reachable, the smallest reliable check |

Each map starts with a note saying when it was written, which commit it describes, and which of its statements are out of date. The fact-check corrected those notes: the first version said the scratch files the maps name were gone, but they still existed at about 03:50 IST on 16 Nov 2026. They were then copied into this repo's git-ignored `data/archive/session_2026-11-16/` (§0.6).

### 0.2 Reaching this repo from the Ballom session

- Give the Ballom session read access to this repo: `/add-dir /Users/sidharthsingh/Desktop/Alcadeias/Alcadeias`. No branch switch is needed; the working tree is on `backtest_hedging` [MEM ballom].
- Read other branches without checking them out:
  - `git -C /Users/sidharthsingh/Desktop/Alcadeias/Alcadeias show <branch>:<path>`
  - `git -C ... log --oneline <branch>`
  - `git -C ... diff --stat <branchA> <branchB>`
- To replay a branch's code, export only its code files, never its credentials:
  `git archive <branch> app.py strategy.py indicator.py mt5_helper.py constants.py symbols.json | tar -x -C <dir>` [MP §7].
  - **On the Turtle branches** (`demo_hedging_btcusd6`, `btcusd7`) add `turtle.py`. Their `app.py` runs `T = _turtle_rules()` at import, which loads `turtle.py` from its own folder (`app.py:45-55` there), so the six-file export cannot even be imported. Add `tests_demo/` as well to run the branch's own tests.
  - `app.py` loads `turtle.py` by path because a bare `import turtle` can resolve to Python's own turtle-graphics module. The general lesson: do not give a module a name that the standard library already uses.
- Never `git checkout` or `git switch` in this repo. Other sessions and worktrees may be using it.

### 0.3 Labels used in this file

- **Measured.** Measured in this repo on Exness CFD data (gold and BTC; US30 and USTEC in the Balke study). Sections 2 to 5 are measured unless a statement is marked otherwise. Every number carries a source tag.
- **Hypothesis.** An untested expectation for Ballom's Indian options. Section 6 is hypotheses unless a statement is marked otherwise.
- **To confirm.** A fact about Indian markets, Fyers or Ballom that was not checked here. This file was written without web access, and the Ballom repo was not opened.
- **Computed.** A number calculated for this hand-off from the named file. It is not printed in any report.

Nothing in this file was tested on options, on Indian markets or on Fyers data.

### 0.4 Source tags

Paths are relative to the repo root.

| Tag | Source |
|---|---|
| [LC] | `LOGIC_CHANGELOG.md`: every logic change and result, newest first |
| [IM] | `IMPROVEMENT.md`: rounds 1 and 2 |
| [BT] | `BACKTEST.md`: the live hedging logic, baseline, live-code findings |
| [BTN] | `git show backtest_netting:BACKTEST.md`: the live netting logic, baseline |
| [RM] | `backtesting/README.md` |
| [OPT] | `backtesting/OPTIMISER.md`; [OPT2] `backtest_results/optimise/v3_XAUUSDm/report.md` (round 2); [OPT4] `backtest_results/optimise/v4_{XAUUSDm,BTCUSDm}/report.md` (round 4) |
| [F10] | `backtest_results/final10/FINAL10.md` (§ = its section); [F10r] its `results.csv` |
| [BK] | `backtest_results/balke/BALKE.md` and its `results.csv`, `years_<symbol>.csv` |
| [EXT] | `backtest_results/improve/external_strategies.md` and its CSVs |
| [REC] | `backtest_results/improve/recovery_mechanisms.md` |
| [SR] | `backtest_results/improve/sr_study.md`, `sr_trades.md` |
| [EDGE] | `backtest_results/improve/edge_screen_{XAUUSDm,BTCUSDm}.txt` |
| [R2] [R3] [R4] | `backtest_results/improve/round2/`, `round3/`, `round4/` (file named where it matters) |
| [DP] | `backtest_results/demo_parity/DEMO_PARITY.md` (untracked, partly stale: §0.5) |
| [PAR] | `backtest_results/parity/*.json`: the 7 hedging parity reports |
| [MLL] [ML] [MT] [MP] | the maps `docs/handoff/live_loop_map.md`, `levers_map.md`, `turtle_map.md`, `parity_map.md` |
| [CL] | `CHANGELOG.md`: the live bot's own release notes (identical on the live branches) |
| [CLd] | `CHANGELOG.md` on the demo branches: v3.9.2-demo.1 and demo.3 on all six; demo.2 (the Turtle) only on `demo_hedging_btcusd6` and `btcusd7`; demo.4 on all six, pushed on 16 Nov 2026 at 03:56 IST (§0.5) |
| [RMd] | `README.md` on each demo branch |
| [J-audit] [J-balke] [J-port] [J-fix1] [J-fix2] | review journals outside the repo (§0.6): the original live-code audit (`wf_285378d0-a0a`), the Balke code review (`wf_c9b9a4c0-2f4`), the demo port (`wf_3ebd063f-c01`), the first fix round and re-review (`wf_c0f3ff36-384`), the second fix round (`wf_ea170a6c-975`) |
| [MEM] | the owner's memory notes for the Alcadeias project (outside the repo; a Ballom session cannot see them) |
| [git X] | the message of commit X |
| a bare code file name | that file under `backtesting/`, e.g. [store.py] = `backtesting/data/store.py`, [kernels.py] = `backtesting/engine/kernels.py` |

### 0.5 State of the repos when this was written

- **`backtest_hedging`.** Local HEAD `bed551e` when this was written, 2 commits ahead of `origin/backtest_hedging` (`0ae5794`): `c61c998` (the demo-parity harness) and `bed551e` (the re-stamped parity reports).
- **Committed on 16 Nov 2026:** this file and `docs/handoff/`, in `ed4fdba` on top of `bed551e` ("docs(handoff): the Alcadeias research hand-off for the next repository (Ballom_Fyers)"), then a follow-up commit (the scratch files archived in `data/archive/`, §0.6, and this status). Pushed with `c61c998` and `bed551e` on 16 Nov 2026, about 04:25 IST.
- **Not committed:** `backtest_results/demo_parity/DEMO_PARITY.md`.
- **`DEMO_PARITY.md` is partly stale.** It quotes 69 / 105 demo tests; after the first fix round there were 107 / 147 [J-fix1], and after the second fix round 124 / 168 on the local heads [J-fix2]. It says there is no broker-side stop; the first fix round added broker-side backstops (§5.9).
- **Live branches.** Unchanged since 13 Nov 2026: `origin/hedging_xauusd6` at `1ed2d6c`, `origin/hedging_btcusd6` at `cef581a`. The live files at the root of `backtest_hedging` are byte-identical to `origin/hedging_xauusd6` (checked with `git hash-object` on 16 Nov 2026).
- **Demo branches on origin** (pushed 16 Nov 2026, 03:56 IST): `demo_hedging_xauusd6` `18e422d`, `xauusd7` `fdf8553`, `xauusd8` `effac75`, `btcusd6` `5eca621`, `btcusd7` `68915b5`, `btcusd8` `b3a557e`. Before that push they were at `766a523`, `d6f9b48`, `843b442`, `b082312`, `9696c00`, `1393693`.
- **The second fix round (v3.9.2-demo.4) is on all six demo branches, pushed on 16 Nov 2026 at 03:56 IST** (§5.13) [J-fix2; before the push: the six branches' upstreams were their own `origin/demo_hedging_*`, they held only demo commits and only the `demo` credentials block, and every other branch on origin was unchanged after it]:
  - `demo_hedging_xauusd6`: six commits, 02:29 – 02:52 IST (`87a7f71`, `ed1594e`, `8c8f5ad`, `d77c323`, `9101642`, `18e422d`).
  - `demo_hedging_btcusd6`: eight commits, 02:55 – 03:06 IST (`bc7cab0` … `5eca621`): the five code fixes cherry-picked, two Turtle-only fixes (`659703d`, the account read again right after the Turtle's positions read; `6c43e1a`, a leg closed beyond the stop ends the trade) and the demo.4 docs commit.
  - 03:26 – 03:29 IST: cherry-picked onto the other four. `xauusd7` `fdf8553`, `xauusd8` `effac75` and `btcusd8` `b3a557e` are each 6 commits ahead of origin; `btcusd7` `68915b5` is 8 ahead.
  - Full test suites on the six local heads, in parallel: 124 passed on each basket branch and 168 on each Turtle branch, 20 – 22 minutes each. The demo parity replay after the fixes ran on `xauusd6` only (V3-lite, 2026-06-30 00:00 – 07-01 14:00 UTC): PASS, 133,228 polls, $1,853.57 as before.
  - The six local branches are checked out in scratch worktrees of another session. Check `git log origin/demo_hedging_<x>` for the final state.

### 0.6 What exists only outside the repo

- **The review journals**, under `~/.claude/projects/-Users-sidharthsingh-Desktop-Alcadeias-Alcadeias/210c2577-eab3-4001-bc50-2408e8c4d100/subagents/workflows/<id>/journal.jsonl`. They hold each reviewer's full result. Their findings are written out in §3.7 and §5.9.
- **The parity recordings and the scratch files the maps name**: `parity_final/*.ref.pkl` (14 files: 7 hedging, 7 netting; 109 MB), the re-check script `parity_final.py`, the probe scripts in `map_parity_check/` and `turtle_probe/`, `levers_*.py` and the parity queue scripts. They were made in the session's temporary scratch folder, which a reboot or a clean-up can delete. On 16 Nov 2026 they were copied into **`data/archive/session_2026-11-16/`** of this repo, which is git-ignored (local to this machine, never committed or pushed). Its `README.md` lists what is there and how to re-check the recordings.
  - The copy includes `netting_live/`, the netting live code the 7 netting windows replay, rebuilt from `origin/netting_xauusd6` with `git archive` (byte-identical to the scratch snapshot). `devclone/` was not copied: its six live code files are byte-identical to `origin/hedging_xauusd6`. The re-check run from the archive on 16 Nov 2026 (`parity_final.py recheck`, code at `ed4fdba`): 14 windows, 711,376 live polls, all identical.
  - Without the recordings, the stored live traces can only be rebuilt by re-running the reference replays: about 16.5 – 17 minutes per 24 h window in one process, 24 – 34 minutes with three in parallel [MP §5].
- **The owner's memory notes.** Everything in them that matters for Ballom is in §1 and §6.

---

## 1. The owner's setup and rules

### 1.1 The two bots

| | Alcadeias (this repo) | Ballom_Fyers |
|---|---|---|
| Location | `/Users/sidharthsingh/Desktop/Alcadeias/Alcadeias` | `/Users/sidharthsingh/Desktop/Ballom` [MEM ballom] |
| Broker and platform | Exness, MetaTrader 5, Python `MetaTrader5` package on Windows | Fyers, through its API [MEM ballom] |
| Instruments | `XAUUSDm` (gold CFD) and `BTCUSDm` (bitcoin CFD), Exness Standard account symbols | CE/PE option pairs on the Nifty index, GoldM and SilverM [MEM ballom; to confirm] |
| Logic | the "Live" logic v3.9.2 on the live branches; tuned designs on six demo branches | "the same old Live logic" [MEM ballom]; version and details to confirm |
| Forward testing | MT5 demo accounts | paper trading, on the memory note's assumption that Fyers has no MT5-style demo [MEM ballom]. To confirm: does Fyers offer a sandbox, test or paper-trading environment for its API? |
| State of the work | backtester, research and demo port done (§3 to §5) | nothing done yet; on 16 Nov 2026 the owner asked only for a plan [MEM ballom] |

### 1.2 Alcadeias branches

| Branches | Count | Status |
|---|---|---|
| `hedging_{xauusd,btcusd}{1..10}` | 20 | **live money**. Profit exit: the +$1 × unit basket target |
| `netting_{xauusd,btcusd}{1..10}` | 20 | **live money**. Profit exit: an M15 slope "book" |
| `dev_{btcusd,xauusd}{1..10}_v2` | 20 | named "all 20 live-money fleet branches" in the live bot's own maintenance policy [CL lines 10-16]; an older line, at v1.7.0 (§2.1). Whether they still trade was not checked. **Treat as live money** |
| `rsimacd_xauusd1_wd_exp_h`, `rsimacd_btcusd1_wd_exp_h`, `rsimacd_h6_xauusd1_wd_exp_h`, `rsimacd_h6_btcusd1_wd_exp_h` | 4 | on origin only; v3.8.0 grey-fill commits of 30 Oct 2026. The live CHANGELOG's v3.9.1 entry calls them "the rsimacd `_h` sources" and excludes them [CL lines 45-50]. Status unknown: never push to them |
| `backtest_hedging` | 1 | the backtesting suite and all research; made from `hedging_xauusd10` on 14 Nov 2026 [MEM] |
| `backtest_netting` | 1 | the netting baseline; made from `netting_xauusd10` [MEM] |
| `demo_hedging_{xauusd,btcusd}{6,7,8}` | 6 | demo accounts (§5.7); change only when the owner asks |
| `dev` | 1 | the default branch; last changed 17 Sep 2026 |
| local `hedging_xauusd10` | 1 | a local copy that **tracks the live `origin/hedging_xauusd10`**: a plain `git push` from it goes to live money (§1.4). Never check it out, commit on it or push from it |
| local `dev_btcusd1_v2`, `dev_btcusd2_v2`, `dev_xauusd1_v2`, `dev_xauusd2_v2`, `dev_xauusd3_v2` | 5 | local copies tracking their live origin branches (all but `dev_btcusd2_v2` 8 – 9 commits behind). The same rule |
| local `dev_btcusd`, `dev_btcusd1` … `8`, `dev_xauusd1` … `5`, `dev_eurusd1` … `3`, `dev_eurchf4`, `dev_gbpusd7`, `dev_usdcad6`, `dev_usdjpy5` | 21 | old local branches (last commits May – Jul 2026) whose upstreams no longer exist on origin ("gone"); not used by the research |
| `wip_demo_parity` | 1 | local only, at `bed551e`; checked out in a scratch worktree |
| `wip_dash_basket`, `wip_dash_turtle` | 2 | local only, no upstream: dashboard and text-log work on the demo code, 16 Nov 2026. `wip_dash_basket` `81a8294` (01:23 IST, "demo(dash): the bot writes the dashboard's data and a detailed text log", on the `xauusd6` head `39a80a8`); `wip_dash_turtle` was `65b74b3` at 02:32 IST and `a291a9a` at 03:54 IST, still moving (on the `btcusd6` head `e2c576d`). Both are checked out in scratch worktrees of another session |

- The table was checked on 16 Nov 2026 with `git for-each-ref` (names, upstreams, dates): 20 `hedging_`, 20 `netting_`, 20 `dev_*_v2` and 6 `demo_hedging_` branches on origin.
- Branches with the same prefix differ only in `mt5_credentials.json`. A slot number is an account, not different code [MLL §0.2; MEM].
- "Hedging" and "netting" name two strategy variants. They are not MT5 account modes [MEM; BT].

### 1.3 How the live bot is deployed

[MLL §0 – §1]
- **Machine.** Windows VPS with an MT5 terminal. `start_job.bat [demo|live]` runs `app.py <mode> --symbol XAUUSDm` (or `BTCUSDm`) once, with Python 3.11. The mode picks the `demo` or `live` block of `mt5_credentials.json`.
- **No restart loop.** When `app.py` exits, nothing relaunches it.
- **One process per symbol**, one poll about every second.
- **Outputs.** JSON files, logs and daily trades go to `C:\Alcadeias`, which every bot on the machine shares. `dashboard.py` serves them on port 8050.
- **Change policy.** Every change is propagated to all fleet branches by cherry-pick, never force-pushed [CL lines 10-16]. The policy text names the 20 `dev_*_v2` branches as the fleet; the "Branches:" lines of the v3.9.x entries name the 40 `netting_` / `hedging_` branches.

### 1.4 Rules for any assistant session

1. **Never push to, commit on, check out or rebase a live-money branch:** `hedging_*`, `netting_*`, `dev_*_v2`. A push changes a live account's code [MEM].
2. **Work only on `backtest_*` branches or branches the owner names.** On backtest branches leave the live files unmodified: `app.py`, `strategy.py`, `indicator.py`, `mt5_helper.py`, `constants.py`, `dashboard.py`, `symbols.json`, `mt5_credentials.json` [MEM].
3. **A branch made from a live branch tracks it.** After `git checkout -b X origin/hedging_...`, X's upstream is the live branch.
   - `push.default` is not set in this repo or globally, so Git's default `simple` applies: a plain `git push` from X is refused, because its upstream has another name ("The upstream branch of your current branch does not match the name of your current branch"; reproduced in a scratch repo on 16 Nov 2026).
   - It does reach the live branch in three cases: with `push.default=upstream`; with `git push origin HEAD:<live branch>`, which Git's own error message suggests; or from a local branch that carries the live name. This repo has such branches: `hedging_xauusd10` and five `dev_*_v2` copies (§1.2).
   - So create such a branch with `--no-track` (or run `git branch --unset-upstream`), push with `git push -u origin X`, and check with `git rev-parse --abbrev-ref X@{upstream}` [MEM; DP].
4. **Commit and push only when the owner asks.**
5. **Record every logic change and its result** in `LOGIC_CHANGELOG.md`, newest first, with a status: live, backtest-only, in progress or rejected [LC; MEM].
6. **Do not call further tuning on 2018 – 2026 "tested on unseen data".** Every year has been read. The next honest test is a forward run [MEM; F10 §10].
7. **Write as the documents here are written:** plain, short sentences; exact numbers with their units and windows; the source of every number.
8. **Keep runs compact.** The owner hit a usage limit on 15 Nov 2026. This is an inference from that event, not the owner's instruction [MEM].

### 1.5 Credentials and privacy

- **`mt5_credentials.json` holds the account logins.** It is tracked in git on every deployment branch, and also on `backtest_hedging` (`git ls-files`, names only). Never open, print, copy or quote it. Tests must not read it [MEM].
- **Export code with `git archive` of the named code files only** (§0.2).
- **Do not repeat one practice of the demo branches.** Their last commit subjects and their READMEs name the demo account's server and login. Keep account numbers, client IDs, app IDs, tokens and passwords out of commit messages, READMEs, logs and dashboards.
- **For Ballom:** check, by file names only, whether a credentials or token file is tracked in git. If one is, tell the owner and never print it. Keep the Fyers app ID, secret, access token and any login seed in environment variables or an untracked file.

---

## 2. The old "Live" logic (v3.9.2) and its fate

All of §2 is **measured** or read in the code. It describes the bot that the live branches run, exactly as coded, and what happened when the bot's own decisions were replayed on the broker's real ticks.
- Code locations `file:line` are in the live files of `origin/hedging_xauusd6` (`1ed2d6c`). `origin/hedging_btcusd6` (`cef581a`) has the same line numbers. Line-level detail is in [MLL].
- The code facts come from the original live-code audit [J-audit], each re-read in the code for the drafts of this file, and from [BT] "Live-code findings", each checked by a second reviewer.

### 2.0 Summary

- **What it is.** A once-a-second loop. It opens a basket on RSI and MACD "pivot-slope" votes read on the still-forming H1 and M15 bars. It closes the whole basket at **+$1 per unit**, or when the M15 votes turn against it. It averages down with a **Fibonacci ladder** of up to 5 adds (1, 2, 3, 5, 8, 13 units: 32 units in all), released by RSI levels on M1, M5, M15, H1 and H4. It has **no stop** of any kind.
- **What it did.** It **wiped a $2,000 account in every window of a year or longer**, on both symbols:
  - 8 years from 13 Nov 2018: gold on 21 May 2019, BTC on 26 Jun 2019 [F10r];
  - 5 years from 13 Nov 2021: gold on 15 Mar 2022, BTC on 21 Dec 2021 [F10r];
  - the last year from 13 Nov 2025: gold in all 8 loop timings (2 Feb – 23 Mar 2026); BTC in 5 of 8 (16 May – 20 Aug 2026), the other three ending at $673.96, $0.73 and $571.01 [`final10/timings_1y_*.csv`];
  - four more one-account windows of 15 months to almost 4 years (§2.12.2).
- **Fresh $2,000 accounts per quarter** (23 quarters between Jan 2021 and Nov 2026, listed in §2.12.3; 8 loop timings each): gold lost money in 172 of 184 runs and was wiped in 27; BTC lost in 174 of 184 and was wiped in 97 [R4 `top3_v4_holdout_*.csv`, `top3_v4_dev_*.csv`; computed].
- **Why.** The entry has no edge, so each basket is a coin flip that pays the spread. The win is capped at about $1 per unit; the loss is not capped at all. The ladder multiplies the stake by 32 at almost one price, and the only exit for a loser waits for an M15 momentum pivot. In 22 of 23 quarters on each symbol it won less often than it needed to break even (§2.12.3).
- **Two ways to die.**
  - *Bleed:* many medium losses at a win rate below break-even. Gold in 2018-19, 2021-22 and Aug – Nov 2025; BTC almost everywhere.
  - *Tail:* one or two full-ladder baskets lose $1,237 – $1,944 each. Gold from Nov 2025 on.
- **Patching one part does not save it.** Removing the ladder, adding a stop alone and retuning the timeframes (432 combinations) all still lost. The owner's RSI rules plus the H1 trend and a 4 h pause made +$9 a quarter on gold over the 15 fresh quarters of Feb 2023 – Nov 2026 (BTC −$125), but lost in 2021-22 (gold −$131, BTC −$191 a quarter) and were destroyed in the continuous 8-year accounts (§2.14).

### 2.1 Version and where the code is

- **Files that decide trades:** `app.py` (1,018 lines; the loop is `process_symbol`, `app.py:440-844`), `strategy.py` (327; `calculate_signal`, `strategy.py:163-327`), `indicator.py` (333), `mt5_helper.py` (756), `constants.py` (147), `symbols.json` (19; like `app.py`, its last line has no trailing newline, so `wc -l` gives 18) [MLL §0.1].
- **Gold and BTC run the same rules, in different trading windows.** Besides a few literal strings (the symbol, the launcher name, a server-time fallback list at `mt5_helper.py:720`, help strings, a missing trailing newline in BTC's `constants.py`), the branches differ in the trading window of `symbols.json`, which changes behaviour: gold Monday 01:00 – Friday 22:00, BTC Monday 00:00 – Sunday 23:59 [MLL §0.3; `git diff origin/hedging_xauusd6 origin/hedging_btcusd6 -- symbols.json`].
- **What one unit means** (`backtesting/config.py:62-70`): gold 1 lot = 100 oz, so 0.01 lot = 1 oz and $1 of basket P/L is a $1 move. BTC 1 lot = 1 BTC, so 0.01 lot = 0.01 BTC and $1 of P/L is a $100 move.
- **Trading window** (server time; Exness server time is UTC, `backtesting/config.py:25`): gold Monday 01:00 to Friday 22:00; BTC Monday 00:00 to Sunday 23:59.
- **Lineage** [CL]:
  - v1.0.0 already described an "RSI multi-timeframe mean-reversion DCA basket (Fibo lot ladder gated by M1/M5/M15/H1/H4 RSI, H6 forced close, `+$unit` basket profit target, balance-stepped unit sizing). No tail-risk stop." (`CHANGELOG.md:1422-1425`). **The oldest parts are the ones that fail.**
  - v2.0.0 (10 Oct 2026) introduced the RSI + MACD pivot-slope votes (`CHANGELOG.md:913`).
  - v3.9.0 (12 Nov 2026) moved the entry votes from H4 + M5 to **H1 + M15**, and the force-close from M15 / H1 / H4 / D1 (weights 4/3/2/1, threshold 12) to **M15 only, threshold 1** (`CHANGELOG.md:80-107`).
  - v3.9.1 (13 Nov 2026) raised `ENTRY_AGREE_S` from 0 to **2** against open-then-instant-close "vibration" (`CHANGELOG.md:47-76`).
  - v3.9.2 (13 Nov 2026) changed only the dashboard.
  - The H6 forced close is gone: `RSI_FINAL_CLOSE_TIMEFRAME = 'TIMEFRAME_H6'` is fetched (`app.py:577`) but no rule reads it.
- **The older `dev_*_v2` line** runs v1.x. A basket opens "when SHA signal+trend agree AND no MTF RSI is extreme" (`CHANGELOG.md:1219`), SHA being a Smoothed Heiken Ashi pair (signal TEMA 10, trend DEMA 20); then "the DCA ladder (M1/M5/M15/H1/H4 adds), RSI adds, `+$unit` profit close and H6 forced close" manage it (`CHANGELOG.md:993-995`).
  - **Its heads are at v1.7.0** (25 Oct 2026), "SHA base candle timeframe M15 → M5": `CANDLE_TIMEFRAME = 'TIMEFRAME_M5'`, the SHA lengths unchanged (`git show origin/dev_xauusd1_v2:CHANGELOG.md` lines 20-42; its `constants.py:29`). The "lagging trend pair (TEMA10/DEMA20 on M15)" wording at `CHANGELOG.md:1006` here is from the v1.6.0 entry and is out of date for these heads.
  - They also carry v1.6.0's regime entry filter (ADX + ATR spike), shipped off: `REGIME_FILTER_ENABLED = False`, `REGIME_FILTER_SHADOW = True` (`constants.py:90-91`). The v1.7.0 entry names the 20 branches "all 20 live-money fleet branches".
  - Last commits: `origin/dev_xauusd1_v2` `0be35a7` and `origin/dev_btcusd1_v2` `9938bd8` (25 Oct 2026). Several slots were rebuilt from those baselines on 10 Nov 2026, keeping their own credentials (e.g. `origin/dev_xauusd10_v2` `2bc4120`).
  - Its code was not read, and every backtest here covers only v3.9.2.
- **For Ballom:** its copy may descend from either line and from any version. Map which one before assuming v3.9.2. The research found that the failure comes from the structure (ladder, $1 target, no stop), not from the timeframes (§2.14).

### 2.2 One pass of the loop

- **Start-up.** `execute_job()` tries `_init_cycle()` up to 3 times, 5 s apart. It loads credentials and `symbols.json`, then calls `mt5.initialize` and `mt5.login` once (`app.py:231-297, 909-985`). **Nothing in the loop ever reconnects** [MLL §1.2].
- **The only state kept between polls** is a set of process locals (`app.py:466-477`): `units` (starts at 1), `_last_close_time` (starts at 0.0) and two save timers. `Strategy` is stateless. Everything else, the basket included, is re-read from MT5 every poll: count, total profit and total volume of **all** positions on the symbol.
- **Timing.** `while True` with `time.sleep(max(brake, 1))` at the end, always 1 s (`app.py:479, 834`). Each order adds 0.1 s (`mt5_helper.py:510, 528`); a ladder add adds 1 s more (`ORDER_COOLDOWN_SECONDS`, `app.py:751, 791`). So polls are **not on a fixed grid**. Exceptions are printed and swallowed: print, sleep 1 s, continue (`app.py:840-844`).
- **What is read every poll:**

| Read | Call | Used for |
|---|---|---|
| M15 "source" feed, 300 bars | `get_rates(sym, M15, 300)` (`app.py:488`) | only to know that data exists; **no decision reads it** |
| Market liveness | `get_market_status(sym, M1, 3 min)` (`mt5_helper.py:372-452`) | "live" if the newer of the last M1 bar time and the last tick time is within 3 minutes of the **VPS clock** |
| Positions, account, server time | `app.py:493-497` | the basket, the balance for the unit, the trading window (server time = last tick time) |
| Indicator bars, 7 timeframes × 500 | `copy_rates_from_pos(sym, tf, 0, 500)` (`app.py:580-584`; `mt5_helper.py:271-277`) | RSI on all 7; MACD and pivot slopes on H1 and M15 only |

- **The 7 timeframes** are M1, M5, M15, M30, H1, H4, H6. M30 and H6 feed no decision [MLL §2.3].
- **Every bar series includes the bar still forming.** Position 0 of `copy_rates_from_pos` is the forming bar, so its close is the current bid. Every RSI, MACD and pivot value the rules read is an intrabar value.
- **If the market is not live, nothing is decided.** `calculate_signal` is not called (`app.py:558, 659-660`): no target, no force-close, no ladder. An open basket is frozen through every closure.

### 2.3 Indicators and votes

- **RSI(14)**, Wilder's RMA (alpha 1/14), SMA-seeded (`indicator.py:13-53, 86-111`). NaN is filled with 100 (`indicator.py:110`), so warm-up bars and a zero-loss stretch read 100. A failed fetch gives 50.0 (`app.py:639-640`).
- **MACD(12, 26, 9)** with SMA-seeded EMAs; `hist = macd − signal` (`indicator.py:113-140`).
- **The pivot-slope vote**, `latest_pivot_slope` (`indicator.py:142-224`):
  1. It scans bars from `n−1−width` back to `max(width, n−lookback)`, with lookback 20 and width 2. With 500 bars, candidate pivots are 2 to 19 bars old.
  2. The newest bar strictly above both of its 2 left and 2 right neighbours is a high; strictly below them, a low. The newest candidate's second right neighbour is the forming bar, so **a pivot can appear and vanish within a bar**.
  3. An RSI high counts only at ≥ 60, an RSI low only at ≤ 40.
  4. For the MACD histogram, the **forming bar's signal line** picks the side: above zero only highs count, below zero only lows (`app.py:606-611`).
  5. The vote is the sign of `(current − pivot) / bars_ago`, where `current` is the forming bar's value. No pivot gives 0, the "grey" vote.
- **What the votes mean.** Both measure from the last extreme, so both are votes to fade it. Over 13 Aug 2025 – 13 Nov 2026 the M15 MACD vote pointed against its own signal-line trend on 80% of gold's M15 bars and 79% of BTC's; 88% of gold's RSI up-votes (91% of BTC's) came after an oversold low [BT §6].
- **They do not predict direction.** After both M15 votes pointed up, gold was higher four M15 bars later 50.8% of the time, against 50.8% for any bar. After both pointed down it was lower 49.9% of the time, against 49.2%. BTC: 51.5% against 50.0%, and 50.8% against 50.0% [BT §6].
- **Repainting.** Forming-bar votes are not what a closed-bar backtest sees. A TradingView or MT5 strategy-tester run on bar closes will not reproduce the live trades [BT].

### 2.4 Scores and the entry rule

```python
open_score = Σ_{tf in {H1:1, M15:1}} w·(rsi_sign + macd_sign)   # grey-fill on    strategy.py:234; constants.py:91
fc_score   = rsi_sign_M15 + macd_sign_M15                       # raw signs       strategy.py:235; constants.py:92
```

- **Grey-fill (open score only).** If exactly one of a timeframe's two signs is 0, it borrows the other's sign (`strategy.py:98-102`). Each timeframe contributes −2, 0 or +2, so `open_score` is −4, −2, 0, +2 or +4. `fc_score` keeps raw signs, −2 to +2.

| Constant (`constants.py`) | Value | Rule |
|---|---|---|
| `ENTRY_S` (67) | 2 | open needs `open_score ≥ +2` (BUY) or `≤ −2` (SELL) |
| `ENTRY_AGREE_S` (69) | 2 | open also needs `fc_score ≥ +2` (BUY) or `≤ −2` (SELL): both M15 votes with the trade |
| `LADDER_S` (75) | 2 | a BUY add needs `open_score > −2`; a SELL add `< +2` |
| `FORCE_CLOSE_S` (77) | 1 | a BUY closes at `fc_score ≤ −1`; a SELL at `≥ +1` |

- **The M15 force-close score is also the entry agreement gate.**
- **A BUY opens when all of these hold:** the symbol is flat (no buy and no sell position); at least 300 s since the last close (`app.py:646`); both M15 votes are +1; H1 is not net against the trade, i.e. its grey-filled votes do not sum to −2; the market is live; the brake is off and the trading window is open (`app.py:516-517, 725-726`). A SELL is the mirror image.
- **H1 is a veto, not a confirmation.** Of the 81 combinations of the four H1 / M15 signs, 6 open a BUY, 6 open a SELL and 69 wait [J-audit, checked on the real code].
- **A failed fetch reads as 0.** A failed H1 fetch removes the veto; a failed M15 fetch blocks entries and force-closes (`strategy.py:68-74`; `app.py:585, 639-640`).
- **The order** is a market order of units × 0.01 lot (`app.py:728, 768`).
- **Re-entry is a state, not an event.** No fresh signal is needed after a close. After a **target** close, the next basket opened on the **same side within 305 s** in 85.8% of 1,257 cases (gold, 8 years), 87.2% of 1,638 (gold, 5 years), 89.9% of 3,060 (gold, last year), 87.3% of 526 (BTC, 8 years), 90.3% of 607 (BTC, 5 years) and 88.4% of 4,509 (BTC, last year) [`final10/trades_*_ticks.csv.gz`, label `Live`; computed]. It re-buys the same swing every five minutes, at a worse price each time, until the swing turns.

### 2.5 Exits

Checked in this order on every live poll while a basket is open (`strategy.py:268-310`).

- **Target: +$1 per unit for the whole basket.** `buy_profit > close_threshold` (strict), with `close_threshold = units` (`strategy.py:271`; `app.py:650`).
  - It does not grow with the basket. A 1-position basket at unit 1 (0.01 lot) needs a $1 gold move; a full 6-position basket (0.32 lots) needs only $0.03 per ounce beyond break-even [BT].
  - `buy_profit` is `round(sum(pos.profit), 2)` over every buy position on the symbol, excluding swap and commission (`mt5_helper.py:62, 72`).
  - It is a snapshot taken before the close orders; the legs are then closed one by one at market [BT].
- **Force-close: the M15 votes turn.** A BUY basket closes when M15 is (−,−), (−,0) or (0,−): 27 of the 81 sign states, whatever H1 says (`strategy.py:256, 274`). It is read on the forming M15 bar at the first poll that sees it, with no confirmation and no minimum hold. It watches momentum pivots, not price or money: in a steady adverse move the M15 votes can stay neutral or supportive [BT §5; J-audit].
- **What does not exist:**
  - **No stop at the broker.** `RISK_REWARD_RATIO = [1, 1]` (`constants.py:121`) makes `_build_request` (`mt5_helper.py:471-481`) send a BUY with `sl = 0` (MT5 reads 0 as "no stop") and `tp = 2 × ask`, and a SELL with `sl = 2 × ask` and `tp = 0`. Neither is ever reached.
  - **No stop in the loop:** no price, money, equity, drawdown or time stop.
  - No H6 final close; `PROFIT_PROTECT_MIN_USD = 0.0` is read by nothing; no daily loss limit, no pause after a loss, no limit on basket size in money.
- **Both sides open.** If buy and sell positions exist on the symbol at once (a manual trade, another bot), no branch of `calculate_signal` matches. Nothing happens: no target, no force-close, no adds and no log line [BT].

### 2.6 The Fibonacci RSI ladder

| Positions open | Tier timeframe | BUY add if forming-bar RSI | SELL add if | Lots added at unit 1 |
|---|---|---|---|---|
| 1 | M1 | ≤ 35 | ≥ 65 | 0.02 |
| 2 | M5 | ≤ 35 | ≥ 65 | 0.03 |
| 3 | M15 | ≤ 35 | ≥ 65 | 0.05 |
| 4 | H1 | ≤ 35 | ≥ 65 | 0.08 |
| 5 | H4 | ≤ 35 | ≥ 65 | 0.13 |
| 6 | – | no further add | – | total 0.32 |

- **The tiers are hard-coded by position count** (`strategy.py:279-310`). Changing `RSI_DCA_LADDER_TIMEFRAMES` changes only what is fetched.
- **The trigger is a level, a state**, not a cross or an event. In a strong move M1 to H4 are all beyond 35 / 65 at once, so **the tiers fire on consecutive polls**.
- **The gate is weaker than the entry gate:** `open_score > −2`. Of the 54 sign states with no force-close, an add is allowed in 45. The bot will add 0.13 lots in states where it would refuse to open 0.01 [J-audit].
- **No spacing:** no price gap, no time gap, only the 1.1 s of sleeps after each add.
- **Size:** `_get_next_fibo_volume` returns the next Fibonacci element × units ÷ 100 (`strategy.py:39-65`). The `/100` hard-codes 0.01 lot per unit. The tier comes from the ticket count, the size from the summed volume; they stay in step only while the open positions are exactly the bot's own ladder [BT].
- **Maximum:** 5 adds, 6 positions, 32 units: 0.32 lot per unit, 3.2 lots at unit 10.
- **The brake and the trading window do not apply to adds** (`app.py:725-726, 765-766` against `738-751, 778-791`). On gold this matters only after the Sunday reopen [computed from the 144 Friday-to-Sunday gaps in `data/store/XAUUSDm/2024_01` – `2026_11/m1.npz`]:
  - Gold's last M1 bar before a weekend opens at 20:56 – 20:57 or 21:56 – 21:57 UTC (140 of 144 weekends; 4 closed earlier, 16:44 – 18:29), before the window ends at 22:00. After the last quote every poll is dead within 3 minutes (`mt5_helper.py:426-431`) and every order is refused as "market closed" (the broker rule both engines model, §3.2), so nothing, adds included, happens after Friday 22:00.
  - The first bar after the weekend opens on Sunday at 22:01 – 22:13 or 23:01 – 23:09 UTC (137 of 144 by five past the hour). From then to Monday 01:00 UTC, when the window opens, an open basket's adds, target and force-close all run, while fresh entries are braked (`app.py:516-517`).
- **In practice the ladder is one clip, not an average-down.** Gold, 13 Aug – 13 Nov 2026, share of each tier's adds that came within 10 s of the previous fill [BT §4]:

| Tier | Within 10 s | Median gap | Median distance |
|---|---|---|---|
| M1 | 12% | 453 s | $4.82 |
| M5 | 43% | 44 s | $1.26 |
| M15 | 85% | 2 s | $0.28 |
| H1 | 97% | 2 s | $0.24 |
| H4 | 100% | 2 s | $0.24 |

  The median quote spread of that quarter was $0.24, and $0.26 at the ladder's entries. So **26 of the 32 units of a full ladder go in at one price**. BTC shows the same: 79 – 98% of the last three tiers' adds within 10 s [BT §4].

### 2.7 Sizing: the unit rule

```python
if _buy_ct == 0 and _sell_ct == 0 and account_info:          # app.py:505  only while flat
    units = int(balance // step_up_balance) + 1               # app.py:508  step_up_balance = 2500
units = max(1, min(units, max_limit))                         # app.py:511  unit_max_limit = 10
```

- A balance under $2,500 gives unit 1, $2,500 – $4,999 unit 2, and so on up to 10. An open basket keeps its unit. Entry lot = units × 0.01; ladder lots = Fibonacci × units × 0.01; target = $1 × units.
- **Exposure of a full ladder** (computed from `app.py:505-511`, `strategy.py:39-65` and the contract sizes; spread and margin ignored). The move columns are the adverse move from the average entry that takes the equity to zero:

| Unit | Balance | Full-ladder lots | Gold $ per $1 move | Gold move to zero | BTC move to zero |
|---|---|---|---|---|---|
| 1 | $2,000 (start) | 0.32 | $32 | $62.50 | $6,250 |
| 2 | $2,500 (just stepped up) | 0.64 | $64 | $39.06 | $3,906 |
| 3 | $5,000 | 0.96 | $96 | $52.08 | $5,208 |
| 10 | $22,500 | 3.20 | $320 | $70.31 | $7,031 |

  The account is most fragile just after each step-up. The $62.50 and $6,250 figures are also in [BT].

### 2.8 Execution and position accounting

- **Orders** (`_build_request`, `mt5_helper.py:454-493`): `TRADE_ACTION_DEAL` at `price = ask` for both buys and sells, IOC, GTC. **No magic number, no comment, no deviation.** The return code is not checked: `BUY_EXECUTED` is logged either way [MLL §2.6].
- **Closes** (`close_by_type`, `mt5_helper.py:531-621`): one opposite deal per leg, at the bid (closing a buy) or the ask, deviation 20. A failed leg is counted and left open. The caller ignores the failure count and starts the 300 s pause anyway.
- **Position reads** (`mt5_helper.py:31-127`) take **every** position on the symbol, with no magic or comment filter. Manual trades and other bots become part of "the basket": added to its profit, used to size the next add, and closed by the bot.

### 2.9 Operational defects of the live code

Each was checked by a second reviewer [BT, "Live-code findings"]; several are demonstrated by `tests/test_live_fault_injection.py`. **Check each one when mapping Ballom.**

1. **A restart forgets the unit and the pause** (`app.py:468, 477, 505-511`). After a restart with a basket open, `units` is 1 until the symbol is flat: remaining adds are mis-sized (0.44× to 1.27× of the intended ladder on an account above $2,500) and the target drops from $N to $1. The 300 s pause is forgotten. Changing any constant needs such a restart.
2. **A dead MT5 connection is swallowed.** Every read returns "no data": positions read as flat and the market as closed. No signal, no close. The loop never reconnects, exits or alerts. With no broker stop, an open basket is unmanaged.
3. **A failed position read is taken as "no positions"** (`mt5_helper.py:52-53, 101-102`). The bot thinks it is flat, re-derives the unit and can open a second basket on top of the first.
4. **Open and add orders are never checked.** A refused order is logged as executed and re-sent on every loop.
5. **A basket close is several independent orders, never retried.** A leftover leg stays open until a close condition fires again.
6. **No magic number and no instance lock.** Any position on the symbol counts as the bot's. With positions on both sides the strategy freezes (§2.5).
7. **The liveness gate compares the VPS clock with broker tick time.** A VPS clock more than 3 minutes fast makes an open market look closed, and exits stop. The bars that drive decisions are not age-checked.
8. **On an MT5 netting-mode account** the ticket count would stay at 1, and the M1 tier would re-fire every ~2 s with growing Fibonacci lots: 2.31 lots after nine adds. The code never checks the margin mode.
9. **RSI = 100 on short history.** A fetch of 14 bars or fewer gives RSI 100, which passes the SELL tier test; possible right after a terminal restart [J-audit].
10. **Decisions on the forming bar** about once a second, so a closed-bar backtest cannot reproduce them (§2.3).
11. **The brake and the trading window block only the first order of a basket** (§2.6).
12. **The +$1 target is a snapshot taken before the close orders** (§2.5).
13. **Housekeeping.** `mt5_credentials.json` and `__pycache__/*.pyc` are tracked in git (§1.5).

### 2.10 The decision constants at a glance

`constants.py`, v3.9.2. The full table of every constant and who reads it is [MLL §3].

| Constant | Line | Value | Read at |
|---|---|---|---|
| `RSI_LENGTH`, `RSI_MA_TYPE` | 26-27 | 14, `'RMA'` | `app.py:587` |
| `RSI_CANDLE_COUNT` | 31 | 500 | `app.py:583` |
| `RSI_OVERSOLD` / `RSI_OVERBOUGHT` | 32-33 | 35 / 65 | `strategy.py:279-310` (ladder) |
| `MACD_FAST/SLOW/SIGNAL` | 56-58 | 12 / 26 / 9 | `app.py:595` |
| `ENTRY_S`, `ENTRY_AGREE_S`, `LADDER_S`, `FORCE_CLOSE_S` | 67, 69, 75, 77 | 2, 2, 2, 1 | `strategy.py:119-122, 243, 249-258` |
| `OPEN_SCORE_WEIGHTS` | 91 | `{'H1': 1, 'M15': 1}` | `strategy.py:234` |
| `FORCE_CLOSE_SCORE_WEIGHTS` | 92 | `{'M15': 1}` | `strategy.py:235` |
| `SLOPE_TIMEFRAMES` | 100-102 | derived: H1, M15 | `app.py:576, 593` |
| `PEAK_LOOKBACK`, `PIVOT_WIDTH` | 103-104 | 20, 2 | `app.py:600, 609` |
| `RSI_PEAK_OB` / `RSI_PEAK_OS` | 108-109 | 60 / 40 | `app.py:601` |
| `REENTRY_COOLDOWN_SECONDS` | 113 | 300 | `app.py:646` |
| `RISK_REWARD_RATIO` | 121 | [1, 1] | `mt5_helper.py:24, 471-481` |
| `ORDER_COOLDOWN_SECONDS` | 140 | 1 | `app.py:751, 791` |
| `MARKET_LOOKBACK_MINUTES` | 19 | 3 | `app.py:490` |
| `symbols.json` | – | `mtqty` 0.01, `step_up_balance` 2500, `unit_max_limit` 10, `brake` 0 | `app.py:452, 466-469` |

`dashboard.py` imports five of these constants (`dashboard.py:15-24`); renaming one breaks the dashboard.

### 2.11 The netting variant

- **One difference.** The 20 `netting_*` branches run the same loop, votes, ladder and sizing. They replace the +$1 target with a profit "book": once the basket's profit exceeds $1 per unit, book when the grey-filled M15 score turns (≤ −1 for a buy) [BTN; netting `constants.py` and `strategy.py`].
- **The book changes nothing.** It fires in exactly the M15 states where the force-close fires, so it only relabels exits [J-audit].
- **Measured** (13 Aug 2025 – 13 Nov 2026, fresh $2,000 per quarter, 8 timings each) [BTN]: gold 40 of 40 quarter-runs lost and **all 40 were wiped**; BTC 37 of 40 lost and 22 were wiped. One continuous account from 13 Aug 2025: gold wiped on 23 Sep 2025 (day 41), BTC on 14 Oct 2025 (day 63).
- **Not studied further** [IM; F10 §10].

### 2.12 Measured fate of the hedging variant

#### 2.12.1 How it was measured

- **Data:** the broker's own tick archive for `XAUUSDm` and `BTCUSDm`, bid and ask per tick, UTC [F10 §1.3].
- **Engine:** the fast engine re-implements the loop poll by poll on forming bars. The reference engine runs the real `app.py` against a simulated MT5 terminal. In 7 hedging windows the two made identical decisions on **373,614 live polls** [BT; F10 §1.4; PAR].
- **Account:** a fresh $2,000 per window and the bot's unit rule. Leverage 1:2000 for gold and 1:400 for BTC. Stop-out at 0% margin level, checked every poll. No swap, no commission [RM].
- **Loop timing:** the long windows replay each second's last quote with one fixed timing. The last year and the quarter runs replay every raw tick eight times, each pass 0 – 0.2 s longer at random [F10 §1.4; BT].
- **"Wiped"** means the broker stop-out closed the account. A drawdown above 100% means the equity went below zero before the stop-out fired [F10 §1.4].
- **Not simulated:** requotes, partial fills, outages, restarts, manual intervention, swap [RM]. The live bot faces these on top (§2.9).
- **Cost sensitivity**, gold, 13 Aug – 13 Nov 2026, median of 4 timings [BT, "How fragile"]: baseline −$69.78; spread × 1.5 −$1,320; spread × 2 −$2,000; 0.1 adverse slippage per fill −$2,000; 1,000 ms latency −$1,415.

#### 2.12.2 Every one-account window

| Window (one fresh $2,000 account) | Gold | BTC | Source |
|---|---|---|---|
| 8 years, from 13 Nov 2018 | wiped **21 May 2019**, after 1,938 baskets | wiped **26 Jun 2019**, after 1,997 baskets | [F10 §2; F10r] |
| Fair test, 13 Nov 2018 – 31 Dec 2020 (same path) | wiped 21 May 2019 | wiped 26 Jun 2019 | [F10 §3] |
| 2021 – 2022 (untouched hold-out) | wiped **17 Jun 2021**, 2,907 baskets | wiped **27 Jan 2021**, 758 baskets | [R4 `equity_top3.csv`] |
| 5 years, from 13 Nov 2021 | wiped **15 Mar 2022**, 2,063 baskets | wiped **21 Dec 2021**, 828 baskets | [F10 §4; F10r] |
| 2023 – Nov 2026 | wiped **17 Mar 2023**, 1,358 baskets | wiped **11 Apr 2023**, 1,380 baskets | [R4 `equity_top3.csv`] |
| Jan 2024 – Jun 2025 | wiped **19 Jul 2024**, 4,148 baskets | wiped **28 Feb 2024**, 1,243 baskets | [R3] |
| 13 Aug 2025 – 13 Nov 2026 | wiped **14 Oct 2025** (day 62 of 457) | wiped **6 Feb 2026** (day 177 of 457) | [R3; BT] |
| Last year, from 13 Nov 2025, 8 raw-tick timings | **8 of 8 wiped:** 2 Feb 2026 (4 runs), 3 Mar, 19 Mar, 23 Mar (2 runs) | **5 of 8 wiped:** 16 May 2026 (3 runs), 2 Jun, 20 Aug; the others ended at $673.96, $0.73 and $571.01 | [`final10/timings_1y_*.csv`] |
| 13 Aug – 13 Nov 2026 only (fixed 1 s grid) | not wiped: −$793, max drawdown $3,380 (95%) | +$316 | [BT] |

The last row flatters the strategy: it was the best of the five quarters of Aug 2025 – Nov 2026 for both symbols [BT §1].

#### 2.12.3 Fresh $2,000 every quarter, 8 loop timings each

Per period [IM; LC round 4; R4 `top3_v4_holdout_*.csv` and `top3_v4_dev_*.csv`, rows `design = Live`; counts computed]:

| Period | Quarters | Gold: average per quarter; runs lost; runs wiped | BTC: the same |
|---|---|---|---|
| 2021 – 2022 | 8 | −$1,154; 64 of 64; 0 | −$1,767; 64 of 64; 48 |
| Feb – Dec 2023 | 4 | −$666; 24 of 32; 0 | −$1,194; 32 of 32; 3 |
| Jan 2024 – Jun 2025 | 6 | −$675; 47 of 48; 0 | −$1,995; 48 of 48; 46 |
| 13 Aug 2025 – 13 Nov 2026 | 5 | −$1,480; 37 of 40; 27 | −$585; 30 of 40; 0 |
| **All** | **23** | **172 of 184 lost; 27 wiped** | **174 of 184 lost; 97 wiped** |

Quarter by quarter, as ranges over the quarters of each period. "Won" is the median win rate of the 8 runs; "needed" is the median break-even win rate |avg loss| ÷ (avg win + |avg loss|); "net" is the median net of the 8 runs; "worst" is the worst basket of all runs. A wiped run's figures cover the days up to its wipe. All computed from the same round-4 files.

| Symbol, period | Net per quarter | Won | Needed | Avg loss | Worst basket |
|---|---|---|---|---|---|
| Gold 2021 – 22 | −$880 to −$1,642 | 75.7 – 82.3% | 84.8 – 89.8% | −$7.14 to −$11.30 | −$435.87 |
| Gold 2023 | +$261 to −$1,418 | 73.0 – 81.8% | 78.8 – 88.0% | −$4.47 to −$9.22 | −$570.22 |
| Gold 2024 – Jun 2025 | −$301 to −$1,150 | 78.5 – 93.1% | 85.7 – 94.0% | −$7.55 to −$22.34 | −$653.42 |
| Gold Aug 2025 – Nov 2026 | −$351 to −$2,000 | 88.8 – 96.0% | 93.7 – 97.7% | −$21.52 to −$72.48 | −$1,944.06 |
| BTC 2021 – 22 | −$1,050 to −$2,000 | 55.4 – 80.1% | 77.7 – 93.7% | −$3.58 to −$17.99 | −$627.25 |
| BTC 2023 | −$292 to −$1,965 | 55.8 – 69.7% | 75.5 – 83.3% | −$3.45 to −$5.43 | −$401.76 |
| BTC 2024 – Jun 2025 | −$2,000 in all 6 | 71.6 – 84.7% | 87.7 – 91.2% | −$8.83 to −$13.11 | −$1,156.67 |
| BTC Aug 2025 – Nov 2026 | +$282 to −$1,407 | 80.5 – 85.7% | 79.7 – 89.6% | −$4.86 to −$11.35 | −$810.90 |

- **The win rate was below break-even in 22 of 23 quarters on each symbol.** The exceptions, gold May – Jul 2023 (+$261) and BTC 13 Aug – 13 Nov 2026 (+$282), are the only quarters with a positive median.
- Average wins were $1.03 – $2.07 per basket in every quarter.
- **Many BTC accounts bled to zero with no single large loss.** In Jan 2024 – Jun 2025, 46 of 48 runs were wiped, yet the worst basket of all 48 runs was −$1,156.67, less than the $2,000 start.
- On the final-ten yardstick (median of 8 timings per quarter) the live logic averaged, per quarter: gold 2021 −$1,113.7, 2022 −$1,189.7, 2023 −$669.5, 2024-25 −$702.4, 2025-26 −$1,525.6; BTC −$2,000.0, −$1,532.8, −$1,184.0, −$2,000.0, −$593.8 [`final10/selection.json`, `references`].

#### 2.12.4 How the accounts died

Exits of the live accounts of the final ten; for the last year, the middle run of the eight [`final10/trades_*_ticks.csv.gz`, label `Live`; computed]:

| Account | Baskets | Target closes | M15 force-closes | Final stop-out | 6-position baskets | 1-position baskets |
|---|---|---|---|---|---|---|
| Gold, 8 years | 1,938 | 1,257: +$1,453.23 | 680: −$3,417.01 | 21 May 2019, −$37.78 | 112: −$1,651.71 | 1,034: +$411.25 |
| Gold, 5 years | 2,063 | 1,638: +$2,079.07 | 424: −$3,791.10 | 15 Mar 2022, −$288.04 | 83: −$1,056.84 | 1,374: +$795.98 |
| Gold, last year | 3,243 | 3,060: +$6,321.12 | 182: −$6,447.12 | 2 Feb 2026, −$1,932.19 | 60: −$3,483.94 | 2,658: +$3,230.57 |
| BTC, 8 years | 1,997 | 526: +$577.68 | 1,470: −$2,482.99 | 26 Jun 2019, −$94.94 | 170: −$1,327.31 | 931: −$26.49 |
| BTC, 5 years | 828 | 607: +$723.74 | 220: −$2,672.32 | 21 Dec 2021, −$67.02 | 16: −$616.36 | 554: +$92.50 |
| BTC, last year | 5,414 | 4,509: +$5,759.84 | 903: −$7,596.26 | 16 May 2026, −$164.95 | 159: −$2,078.79 | 3,798: +$2,619.95 |

The BTC last-year account also closed 1 basket at a data hole (opened 30 Nov 2025 18:14 UTC, −$0.95): 4,509 + 903 + 1 + 1 = 5,414 [same file; computed]. The other five accounts had no data-hole close.

- **Bleed** (gold 8 and 5 years, all three BTC accounts): no single basket came near $2,000. The worst baskets were −$243.93 (gold, 8 years), −$288.04 (gold, 5 years), −$96.07 (BTC, 8 years) and −$322.11 (BTC, 5 years) [F10r]. The force-closes simply took more than the targets brought in. Gold's 8-year equity, month-end marks: $2,000 (13 Nov 2018) → $1,953 → $1,359 → $1,328 → $1,013 → $402 (31 Mar 2019) → $191 → $60 (21 May 2019) [`final10/equity_XAUUSDm_ticks.csv.gz`].
- **Tail** (gold from Nov 2025): the win rate rose to 92 – 96%, but in the last year's middle run 8 of 3,243 baskets lost more than $100 each and together lost $5,504.06: 66% of all losses ($8,379.61) and 87% of all wins ($6,321.42).
  - 22 Jan 2026: at unit 2, after the account peaked at $3,191, a 6-position **SELL of 0.64 lots** opened at 21:07 UTC at 4,917.84. The M15 force-close fired only at 23:47, at 4,952.62, for **−$1,590.35**.
  - Monday 2 Feb 2026: the window opened at 01:00; a BUY hit its target at 01:02:05 (+$3.02). The pause ended at 01:07:05 and a new BUY opened at **01:07:06 at 4,739.76**. It held **all six positions (0.32 lots)** when the stop-out closed it at **01:10:12 at 4,635.79, for −$1,932.19**: the whole account in 3 minutes 6 seconds.
  - In the other seven timings the worst basket lost $1,237.39 to $1,944.06 [`final10/timings_1y_XAUUSDm.csv`].
- **The worst gold basket of 13 Aug – 13 Nov 2026** [BT §5]: a BUY of 0.64 lots opened on 22 Oct 2026 at 4,037.27, held 7.3 hours while gold moved $28.45 against its average entry, closed at −$1,821. In that quarter 67% of losing baskets closed within 10% of their worst point, 28% had been in profit before, and one basket that ended as a winner had been $1,003 under water.

#### 2.12.5 Why short live trials look fine

The same live settings on fresh $2,000 accounts [BT, "How fragile"]:
- **Weeks:** in the 13 weeks of 13 Aug – 13 Nov 2026, gold was positive in 9 (median +$60.91) and stopped out in none.
- **Months:** in the 14 calendar months Sep 2025 – Oct 2026, gold was positive in 4 and stopped out in 4 (median −$361).
- **Days resampled** 5,000 times: 65% of draws ended below the start and 29% wiped.
- **High win rates hide it:** 93.5% of 3,620 gold baskets won in that quarter, against 94.1% needed; average win +$2.22, average loss −$35.15. One loss cancelled 16 wins [BT §2].

So a week or a month of live or demo trading says almost nothing, and neither does a win rate above 90%.

### 2.13 Why it fails: the mechanism

1. **A small fixed win against an open-ended loss.** The target closes at about $1 per unit; nothing caps the loss. The strategy needed a 75.5 – 97.7% win rate to break even and fell short in 22 of 23 quarters on each symbol (§2.12.3).
2. **The entry has no edge, and every basket pays the spread.**
   - Twenty entry signals were screened on every closed M15 bar over 15 months: the bot's votes, RSI extremes, divergence, day high / low bounces and breaks, momentum, time of day. **None was statistically reliable on either symbol** [IM round 1; LC "Entry ideas screened"; EDGE].
   - The bot's gold entries against the H4 trend lost about $1.44 per 0.01 lot over the next four hours; entries with it were flat [IM round 1].
   - Gold's median spread at entry was $0.26 against a $1 target. Gold paid $2,945 of spread in 13 Aug – 13 Nov 2026, 39% of the winners' gross profit: +$2,157 before spread, −$788 after [BT §7].
   - BTC's spread was far wider in the past: 0.215% of the price in 2018, 0.139% in 2021, 0.052% in 2024, 0.017% in 2026 [BK §5.3]. At the Nov 2021 price of about $64,100 [F10 §4], 0.139% is about $89, i.e. about $0.89 of every $1 target per 0.01 lot (computed).
3. **The ladder fires as one block** (§2.6). In 13 Aug – 13 Nov 2026, gold baskets that never added made +$4,251 and baskets that added lost $5,040; the 40 baskets that reached six positions netted −$1,839, losing $567 on average when they lost; BTC +$1,191 without adds, −$874 with [BT §4]. Read with care: a basket adds only when price moves against it, so this is partly selection.
4. **The only loss exit watches M15 pivots, not money.** It can stay silent for hours: 7.3 h and −$1,821 on 22 Oct 2026; 2 h 40 min and −$1,590.35 on 22 Jan 2026. Nothing stands behind it, and when the bot is blind (market closed, terminal dead, a failed read) nothing closes the basket.
5. **Re-entry is a state** (§2.4): 86 – 90% of next baskets after a target opened on the same side within 305 s.
6. **The unit step-up raises the stake after small wins.** Gold, 13 Aug – 13 Nov 2026: at unit 1, 1,607 baskets made +$124 (worst −$295); at unit 2, 2,013 baskets lost $912 (worst −$1,821) [BT §8]. Right after a step-up, a $39.06 gold move against a full ladder takes the equity to zero (§2.7).
7. **The same $1 is a different bet in different years.** The target is fixed in account dollars, not in price or volatility. Median H1 volatility unit (the average H1 close-to-close move, per 0.01 lot) at V3-lite's basket opens [LC, V3-lite entry; ÷ 8 computed]:

| Year | Gold, $ per 0.01 lot | BTC, $ per 0.01 lot |
|---|---|---|
| 2023 | $2.00 | $0.75 |
| 2024 | $2.88 | $2.25 |
| 2025 | $4.88 | $2.88 |
| 2026 | $9.38 | $2.00 |

   - Where the $1 target is far (BTC 2023: 1.3 H1 moves), the bot wins only 55 – 70% of baskets and bleeds through force-closes.
   - Where it is near (gold 2026: a ninth of an H1 move), it wins 92 – 96% but each loss is bigger (−$33 to −$72 on average).
   - **For Ballom (hypothesis):** a fixed rupee target per lot will behave just as differently across instruments, premium levels and volatility regimes.

**The chain in one paragraph.** The votes fade the last extreme and do not predict direction, so each basket starts as a coin flip that pays the spread. If price goes the right way, the basket closes at about $1 per unit. If it goes the wrong way, the RSI tiers fire together and the stake grows to 32 units at almost one price. The basket then waits, with no stop, for an M15 momentum pivot that a steady move does not produce. When the bot is flat again, it re-enters the same swing five minutes later. A good run raises the unit, and the next bad basket is taken at double size. Where the target is far in price terms the account bleeds; where it is near, it dies in one or two full-ladder baskets. Either way it reached zero in every window of a year or longer from 2018 to 2026, on both symbols (BTC's last year: 5 of 8 timings, the others left with $673.96 or less).

### 2.14 Changing one part does not save it

- **No ladder**, everything else live (fresh $2,000 per quarter, 8 timings, 13 Aug 2025 – 13 Nov 2026): gold 40 of 40 runs lost, −$701 a quarter, worst basket −$217, none wiped; BTC 39 of 40 lost, −$184 a quarter [BT, candidate table, "live timeframes · no ladder"]. Removing the ladder ends the wipe-outs, not the losses.
- **A stop alone, ladder kept** (one fixed 0.01-lot unit, three 2026 quarters): gold with a $20-per-unit stop −$5,107 against −$4,359 live, worst basket −$166, the account still wiped. "A stop alone turns a rare large loss into frequent medium ones; the ladder is what makes the large loss large" [BT §10].
- **Timeframes:** 432 combinations of OPEN and FORCE-CLOSE timeframes on five quarters. The 12 gold settings profitable in all three analysed quarters without a wipe: none profitable in both hold-out quarters, 75% wiped the account in one. No setting on either symbol was profitable in all five quarters without a wipe [BT §9].
- **Exit and filter levers** (191 designs, 5 quarters, fixed 0.01-lot unit, average over the designs with each setting): $1 target → $10 target and $20 stop with force-close off, gold −$280 → −$55; no trend filter → H1 trend, gold −$423 → +$6 [IM round 1 §2].
- **The owner's rules on top** (ladder and $1 target kept; no entry while the H1 or H4 RSI is beyond 35 / 65; an H1 / H4 RSI force-close; the H1 trend; a 4 h pause after a loss): +$9 a quarter on gold and −$125 on BTC over 15 quarters [LC round 3], but over 8 years **gold destroyed ($1 left) and BTC wiped on 31 Oct 2021**; over 5 years BTC wiped on 25 Nov 2024 [F10 §2, §4].
- **The M15 force-close itself hurt:** across the 400 settings sampled per symbol in round 4 it made results worse on both symbols [LC round 4; OPT4] (§4.3).

### 2.15 What removed the wipe-outs (details in §4 and §5)

- **Kept:** the H1 trend filter (sign of the H1 MACD signal line on the last closed bar); a stop and a target on the whole basket in volatility units (8 / 8); a long pause after a losing basket; **no ladder**; the M15 force-close off [LC, final exam].
- **Rejected:** the live Fibonacci ladder; support and resistance; all 42 recovery mechanisms tested on 32,553 entries [IM round 2; REC].
- **Result:** gold V3-lite $2,000 → $11,957 over 8 years (max drawdown 33.0%) and +17.0% on the never-read Nov 2018 – Dec 2020. On BTC only the Turtle breakout made real money [F10].

### 2.16 For the Ballom session: what to check first in its copy

These are questions, not facts about Ballom; its code was not read for this file.
1. **Which version is it?** Compare its constants with §2.10 and the lineage in §2.1: entry weights, `ENTRY_AGREE_S`, the force-close set and threshold, the RSI levels, the tier map, the Fibonacci sizes, the target per unit, the 300 s pause, the unit rule. An older copy may still have the H6 forced close or SHA entries.
2. **Hedging-style target or netting-style book?** (§2.5, §2.11.)
3. **What is one unit?** How many option lots, and what is the rupee target per unit? Set that target against the round-trip cost per lot (the option's bid-ask spread plus every fee and tax) and against the premium's typical move. Gold's $1 target was only about four spreads wide, and the spread took 39% of the winners' gross profit (§2.13).
4. **Does it ladder?** Are its tiers level tests that fire together (§2.6)? A 1, 2, 3, 5, 8, 13 ladder means 32 lots at full depth.
5. **Is there any stop,** at the broker or in the loop? Is there an equivalent of `RISK_REWARD_RATIO = [1, 1]` that sends no usable stop (§2.5)?
6. **Which prices drive the votes and the ladder:** the underlying (index or future) or the option premium? Forming bars or closed bars?
7. **Which positions count as its basket?** Does it tag its orders and filter by the tag? Does a failed read look like "flat" (§2.8, §2.9)?
8. **What happens to an open basket at the session end and at expiry?** The MT5 bot holds through every closure and decides nothing while the market is closed (§2.2).
9. **What does a CE / PE "pair" mean in its state machine?** The MT5 logic has no branch for positions on both sides and freezes (§2.5).
10. **Restarts.** Does it keep the unit, the pause and the basket across a restart? Does it reconnect, and refresh its API token?
11. **Pin it before changing it.** Two test files here are templates: `tests/test_live_strategy_characterization.py` (21 tests that pin what the live `strategy.py` decides, including an exhaustive decision table and the Fibonacci lots through six positions) and `tests/test_live_fault_injection.py` (3 tests that replay the real `app.py` against a simulated terminal: a failed position read treated as flat, a restart that forgets the pause, a refused open logged as executed and re-sent every loop).

---

## 3. How we test

All of §3 is **measured** or describes code in this repo. Times are UTC; a window `[start, end)` includes its start and excludes its end; money is USD.

### 3.1 The data

- **The archive.** Exness publishes every tick of every symbol, account suffix included, as one ZIP per symbol and month [exness.py]:
  `https://ticks.ex2archive.com/ticks/<SYMBOL>/<YYYY>/<MM>/Exness_<SYMBOL>_<YYYY>_<MM>.zip`
  - A CSV with the columns `"Exness","Symbol","Timestamp","Bid","Ask"`; UTC timestamps with milliseconds [store.py].
  - The current month is re-published daily; the downloader fetches it again when the remote size or Last-Modified changes. It uses only the Python standard library and sends a generic User-Agent [exness.py].
  - The archive starts in January 2016 for gold, January 2018 for BTC [F10 §1.3], and June 2020 for US30m and USTECm [BK §3].
  - **Why this source:** it is the broker's own bid/ask stream for the exact account symbols, so the spreads, session breaks and gaps are the ones the live account saw. Exness MT5 server time is UTC, so bars bucket on plain UTC boundaries, as the terminal builds them from the bid [RM].
- **The store.** `python -m backtesting data --symbols ... --from YYYY-MM --to YYYY-MM` writes raw ZIPs to `data/raw/` and the store to `data/store/<SYMBOL>/<YYYY>_<MM>/`; both are git-ignored; `ALCADEIAS_STORE_DIR` moves the store [RM]. Three files per month [store.py]:

| File | Holds | Used for |
|---|---|---|
| `ticks.npz` | every tick: `t_ms` (int64, UTC ms), bid, ask | high-fidelity runs, parity with the live code, timing tests |
| `sec.npz` | the last tick of every second, plus the last tick stamped exactly on a whole second | sweeps: a 1 s poll on whole seconds sees exactly these quotes; about 5 times smaller than raw ticks |
| `m1.npz` | M1 bars from the **bid**: open, high, low, close, ask at the closing tick, mean and max spread, tick count | indicator warm-up, charts, the M1-bar simulator |

- **Cleaning is conservative.** Only rows that cannot be quotes are dropped (non-finite or non-positive prices, ask below bid); out-of-order rows are sorted with a stable sort; both counts are reported [store.py]. In Aug 2025 – Nov 2026 both symbols had 0 of each [BT]. Bars exist only where ticks exist.
- **Held on 16 Nov 2026:** XAUUSDm 119 months (Jan 2017 – Nov 2026), BTCUSDm 107 months (Jan 2018 – Nov 2026), US30m and USTECm 78 months each (Jun 2020 – Nov 2026); 11 GB raw, 22 GB store (listing and `du` of `data/`).
- **Quality checks before any result.** `python -m backtesting quality` reports coverage, every silence over three minutes by kind, the spread by hour, and the largest one-second moves [RM]. On BTC, which trades around the clock, a silence of 3 h or more is a hole in the archive; up to 1 h is a maintenance pause. On gold a silence is classed by length and clock time: weekend, daily break (0.8 – 1.3 h whose start hour is 20, 21 or 22, i.e. starting 20:00 – 22:59 UTC), holiday, early close, short pause [quality.py]. For 13 Aug 2025 – 12 Nov 2026 [BT]:

| | Gold | BTC |
|---|---|---|
| Ticks | 121,848,115 | 70,060,891 |
| Spread median / p99 / max | 0.24 / 0.36 / 4.00 | 14.00 / 21.60 / 413.89 |
| Silences over 3 min | 335: 250 daily break, 64 weekend, 10 short pause, 7 early close, 3 holiday, 1 other | 72: 69 maintenance pauses, 3 holes |

  The largest moves were real events (the crypto liquidation of 10 Oct 2025, gold on US data releases), not bad ticks [RM].
- **Holes in the history.** The BTC tick store has 11 silences of 3 h or more, Jan 2018 – Nov 2026 [computed from the `t_ms` gaps in `data/store/BTCUSDm/*/ticks.npz`; the price changes from BT; F10 §1.3]:
  - 26 Oct 2018 18:35 → 27 Oct 00:00 (5.4 h, before the 8-year window) and 30 May 2020 10:17 → 16:04 (5.8 h);
  - 2 Mar 2021 13:22 → 4 Mar 00:00 (34.6 h);
  - 2, 5, 12 and 17 Apr 2024, each from about 19:00 – 20:00 to 00:00 (3.9 – 5.0 h);
  - 27 Apr 2025 23:59 → 29 Apr 00:00 (24.0 h);
  - 29 Aug 2025 23:59 → 31 Aug 00:00 (24.0 h, price +0.4% across it), 30 Nov 2025 18:29 → 1 Dec 00:00 (5.5 h, −1.1%), 29 Mar 2026 23:59 → 1 Apr 00:00 (48.0 h, +3.4%).
  - 10 of the 11 fall inside the 8-year window and 8 inside the 5-year window.
  - **The first naive replay was wrong:** the bot froze for the missing hours, and its open basket was handed the whole move in one jump [git 2702af2].
  - **The rule now:** the open basket is closed at the last quote before the hole (reason `data_hole`); no new basket opens for a quarantine of **38 H4 bars (6.3 days)**, the peak lookback 20 + 2 × pivot width 2 + RSI length 14 bars of the slowest timeframe the live settings read. It is the same length for every configuration, so every row of a sweep sits out the same days. Gold, which has real closures, never uses it [config.py; RM; git c126ac2].
  - **Effect:** 6 – 7 baskets per design over 8 years were closed at a hole [ML §7].
- **Costs change inside the data.** BTC median spread as a share of the price: 0.215% (2018), 0.211%, 0.128%, 0.139%, 0.095%, 0.066%, 0.052%, 0.021%, 0.017% (2026) [BK §5.3]. Index spreads fell in 2025: US30 0.020% (2024) to 0.006% (2025), USTEC 0.029% to 0.009% [BK §6]. Gold's quarterly median moved between 0.16 and 0.28 in Aug 2025 – Nov 2026 [BT].
  - **Effect on one result:** Balke's BTC Range Breakout, his sizing on $10,000, 8 years: $5,536 at Exness's real spreads, $168,113 with every bar's spread set to 0.02% [BK §5].
  - **Rule:** a long backtest mixes cost regimes. Report results per year, and run a constant-cost scenario next to the real one.

### 3.2 The engines

```
BacktestConfig ──┬── engine/reference.py   the real app.py loop on a simulated MT5 terminal   (truth, slow)
                 └── engine/fast.py        numba re-implementation of the same loop           (seconds per run)
                              ▲
                     engine/parity.py checks them against each other, poll by poll

research/external.py   M1-bar simulator for published strategies (no live code)
research/balke.py      multi_account: the M1-bar simulator with overlapping positions
```

- **`BacktestConfig`** [config.py] has a field for every number the live bot hard-codes in `constants.py` and `symbols.json`; `BacktestConfig.live(symbol, repo_root)` reads a branch's own files. **Every experimental lever is off by default**, so a default run is the live bot [RM].
- **The reference engine: the live code itself** [RM; MP §1]:
  - It imports the branch's own `app.py`, `strategy.py`, `indicator.py`, `mt5_helper.py` and `constants.py`, with `sys.modules["MetaTrader5"]` replaced by **`SimMT5`**, an in-memory terminal fed with real ticks. The untouched `MT5TradingBot.process_symbol` runs; a hook records one trace row per pass.
  - **The clock is simulated:** time advances only through the loop's own `time.sleep` calls; work takes no simulated time. Since `c61c998`, every reading of `time` and `datetime` in every live module is simulated.
  - `SimMT5` grows bars of all 14 timeframes tick by tick from the bid, forming bar included, seeded with 600 bars resampled from M1 history (about 2.8 years before the window).
  - It applies the broker's rules: "market closed" (an order more than 1 s after the last quote before a silence of 30 min or more), "close-only" for 90 s after a silence of 30 min or more and 210 s after one of a day or more, and "no money".
  - **The rule depends only on the data, on both symbols.** BTC has such silences too: about 80 of 30 min to 3 h in 2018 – 2025 (38 in 2018, about 10 in 2022, about 25 in 2024, 2 in 2025), e.g. 2-hour weekend pauses in 2018 and 141 min on 5 Feb 2022. So both engines apply these refusals to BTC there [kernels.py L238, L806-810, L835; reference.py L463-465, L771-781; computed from the M1-bar gaps in `data/store/BTCUSDm`, 81 – 84 by the counting rule]. The "up to ~45 minutes" in `config.py`'s BTC comment understates them.
  - Ending and restarts use `BaseException` subclasses, because `process_symbol` swallows every `Exception`.
  - **Cost:** 11.9 ms per live poll in one process, about 16.5 minutes per 24 h of gold [MP §5]; about 17 ms per poll with six replays in parallel [J-port].
- **The fast tick engine** [RM; ML §2]:
  - A numba kernel re-implements the loop. At every poll it takes the latest tick, updates the **forming** bar of each timeframe, computes RSI, MACD and the pivot slopes on it, applies the rules of `strategy.py` and keeps the account.
  - About 15 s of numba compile once, then 0.01 s per 20 minutes of ticks; three months of one-second polls take 1 – 3 s [MP §5; RM].
  - Warm-up of up to 600 bars per timeframe, where the live bot fetches 500; with the live lengths they agree to nine decimals [RM].
  - Two modes: `sec` (the per-second series, one poll on every whole second; it cannot represent the live 0.1 s sleep after an order) for sweeps and long windows, and `ticks` (every tick, with the 0.1 s sleep) for baselines, timing and cost tables. They agree until the first order [RM].
  - Memory: an 8-year per-second prepare needs about 7.5 GB of RAM for BTC and 4.2 GB for gold, so long windows run one at a time on the 16 GB machine [MEM]. Eight years of raw ticks do not fit in memory [F10 §1.4].

| Aspect | Model in the fast engine [RM, "What is simulated"] |
|---|---|
| Loop | one pass per second; 1 s more after an add, filled or refused; 0.1 s more after every entry or add only in raw-tick runs (`open_order_delay_ms` = 100), never in per-second runs, which keep every pass on a whole second (§5.2); optional random jitter |
| Indicators | recomputed on the forming bar at every poll, same seeds and comparisons as `indicator.py` |
| Fill | market order at the quote of the tick the decision saw: ask for a buy, bid for a sell; `latency_ms` delays the fill quote |
| P/L | price difference × lots × contract size, rounded to cents per position, as MT5 reports it |
| Costs | the recorded spread; no commission; no swap |
| Sizing | the unit rule, re-derived only while flat |
| Margin | gold at 1:2000; BTC at Exness's former fixed 1:400; an order the free margin cannot carry is refused |
| Stop-out | all positions closed when equity ≤ 0 (Exness Standard stop-out 0%) |
| Sessions | no decision while the last tick is older than 3 minutes; entries only in the trading window; market-closed and close-only refusals |
| Not modelled | requotes, partial fills, other refusals, terminal or VPS outages, bot restarts, manual intervention, swaps, temporary broker margin increases |

- **Parity: does the fast engine make the live code's decisions?** `python -m backtesting parity --symbol X --start ... --end ... [--live-root DIR] --out f.json` [MP §3]. At every live poll these must match:
  - the poll time (exact milliseconds; after the first cadence difference nothing else is compared);
  - the signal; the open, force-close and book scores (tolerance 1e-9); the ladder RSIs (1e-6);
  - the signed position count, the floating profit (within $0.0051) and the unit;
  - every fill: in or out, side, volume, price (1e-9), P/L (within $0.0051), decision time (within 1.5 s);
  - the final balance, and no error line from the live code.
- **The recorded windows: 14 (7 hedging, 7 netting), 711,376 live polls, all identical** [git 48933e6; git bed551e], with **763 fills** (607 hedging + 156 netting; computed from the `fills_ref` of the 14 parity JSONs in the scratch folder, §0.6). Hedging: 373,614 polls, 607 fills, largest RSI difference 6.4e-14 [PAR]. The 7 hedging windows:

| Window (UTC) | Settings | Live polls | Fills | Broker refusals |
|---|---|---|---|---|
| BTC 2026-09-22 00:00 → 12:00 | other settings: open H4 + M5, force-close M15/H1/H4/D1, other indicator lengths, 60 s pause | 43,159 | 131 | none |
| BTC 2026-10-10 00:00 → 10-11 00:00 | live | 86,359 | 45 | none |
| BTC 2026-09-15 00:00 → 09-16 00:00 | live | 86,375 | 108 | none |
| BTC 2026-08-20 00:00 → 12:00 | live, $5,200 start (unit 3) | 43,159 | 128 | none |
| Gold 2026-02-02 00:50 → 01:40 (crash) | live, $1,000,000 start, unit capped at 1 | 2,998 | 16 | none |
| Gold 2026-10-14 00:00 → 10-15 00:00 | live | 82,800 | 154 | 1 market closed, 34 close-only |
| Gold 2026-10-16 18:00 → 10-19 03:00 (weekend) | live | 28,764 | 25 | none |

  - After every engine change the recorded live traces are compared again with the current fast engine in seconds (`parity_final.py recheck`); they must stay "ALL IDENTICAL" [MP §4]. The recordings are outside the repo (§0.6).
  - In the test suite, `tests/fixtures/store` holds an hour of real BTC ticks and 45 minutes of real gold ticks with warm-up history; `tests/test_parity.py` replays them; full-window replays are marked `slow` [RM].
  - **What parity does not cover:** the stop-out (unit tests only); the handling of holes; a loop that does not take exactly 1 s per pass; the 90 s and 210 s close-only durations themselves (taken from Exness's published behaviour, not measured); broker-side SL/TP (stored, never executed); pending orders; terminal failures such as reconnects, a wrong account, failed or slow position reads [BT; RM; J-fix1].
  - **Parity proves equal code, not a profitable strategy** [MP §8.4].
- **Parity of the demo branches and the Turtle replay** (details in §5.8). `python -m backtesting.engine.demo_parity <branch dir> <SYMBOL> "<design>" "<start>" "<end>"` builds the design from `top3_v4_<SYMBOL>_designs.json`, checks that the branch's `constants.py` and `symbols.json` hold it, and replays the branch's `app.py` against the fast engine, by default on a shared $10,000 account with other positions and other bots' trades [git c61c998]. 8 real-parameter windows, two per design, **842,216 live polls in total**, all passed with 0 signal, score and fill mismatches [DP; total computed]. The Turtle has no fast-engine counterpart, so it was checked at the level of decisions against the simulator's trade list [DP].
  - **A tool trap:** with `--set` or `--initial-balance`, `demo_parity` still checks the branch's constants against the unmodified design row ("--initial-balance / --set only change the replay", `demo_parity.py:337-338`). If the branch's constants differ from that row, for example a work-in-progress branch still at the live defaults, the verdict is FAIL even when parity passes. A branch that holds its design passes the static check; the scaled-down replays on the committed branches did [J-port].
- **The M1-bar simulator for published strategies** [external.py docstring; EXT; F10 §1.4; BK §3]. It does not run the live code.
  - M1 bid bars; ask = bid + the bar's **mean** spread, so a spread spike inside a minute is not seen [BK §11].
  - Strategy bars on UTC boundaries; a UTC day with fewer than 360 M1 bars (six hours) is merged into the next day.
  - Signals on **closed** bars, filled at the next M1 open (a buy at the ask). Intraday rules decide at fixed clock times and need a quote within 3 minutes.
  - Stops, targets, trailing stops, pyramid adds and stop entries are checked on every M1 bar: a gap at the open first, then the unfavourable extreme before the favourable one, so a bar that reaches both is a stop. A stop entry filled inside a bar may be stopped in that bar but cannot reach its target there. A buy's stop is on the bid, a sell's on the ask; a buy-stop entry triggers on the ask, a sell-stop on the bid.
  - One position per strategy (the Turtle may pyramid to 4 units); every period is its own account; what is open at the end is closed at the last close.
  - **Checks:** 67 tests in `tests/test_external.py`, including no-look-ahead tests that cut the history, or replace it by a +50% jump or a −40% crash, 1 – 4 minutes after each decision. 15 deliberate look-ahead bugs were injected first; the tests caught all 15 [EXT]. An independent reviewer recomputed the top three gold rows to the cent [EXT]. The final-ten runner reproduced all 51 published accounts to the cent [F10 §1.5].
  - **Calibration against the tick engine**, votes on closed bars in both: on gold in Q2 2024, 13 of the engine's 14 baskets are in the bar-level list on the same side, 12 in the same minute, all fills within $0.41 [EXT]. V3-lite on gold over 8 years: $2,300 (tick engine) against $2,480 (simulator), within $290 in every window [F10 §7].
  - `multi_account` [balke.py] holds overlapping positions; after the review fixes it reproduces the single-position kernel to the cent on trades that never overlap [LC; BK §3].
  - `fast.run(cfg, prep, regime=(times_ms, values))` lets the tick engine run a bar-level trend filter computed outside the kernel; off by default, tested in `tests/test_regime_filter.py` [RM; F10 §7].
- **The largest model effect: votes on the forming bar or on closed bars.** V3-lite on gold over 8 years made **$11,957 with forming-bar votes** on the tick engine, **$2,300 with closed-bar votes** on the same engine, and $2,480 on the M1-bar simulator [F10 §7]. The V3-lite hybrids had been chosen on the simulator and were re-run on the tick engine "as the bot would run them", after the pre-registration and labelled so [F10 §7]. **Rule for any port: test the bar reading the live code uses.** The Turtle backtest used closed M15 bars, so its port must too [MT §13].

### 3.3 How a strategy was measured

- **Accounts** [F10 §1.4; RM]:
  - A real $2,000 account, the bot's unit rule, nothing withdrawn. Leverage 1:2000 (Exness caps BTC at 1:400). Stop-out at 0% margin level. No swap.
  - A fresh account per window. For selection, a fresh $2,000 per quarter and the average profit per quarter, the bot's own test format; for our designs, the median of eight loop timings per quarter.
  - **Why fresh accounts:** a stopped-out account ends its run, and one continuous account depends on its start day. Gold live settings, the same quarter started up to 14 days later: −$836 to −$202 [BT, "How fragile"].
  - **Final equity** is the balance plus any open position at the last price. **Drawdown** is the deepest fall from a previous equity peak; the tick engine marks every second or tick; the simulator takes peaks at minute closes and troughs at the worst price inside each minute. A drawdown above 100% means the equity went below zero before the stop-out [F10 §1.4].
  - **Rankings** in each window: highest final equity, lowest maximum drawdown, and CAGR ÷ maximum drawdown. A row that skipped most of its signals is not ranked on drawdown [F10 §1.4].
- **The unit rule and other sizing:**
  - unit = floor(balance ÷ 2,500) + 1, at most 10; each unit is 0.01 lot; re-derived only while flat [F10 §1.4; MLL §2.2].
  - **It raises the stake after a good run.** Gold, one quarter: unit 1, 1,607 baskets, +$124; unit 2, 2,013 baskets, −$912 [BT finding 8].
  - **Year percentages do not compare across years:** a unit is 0.01 lot at any price, so its dollar exposure grew about 3.6 times for gold and 14 times for BTC from Nov 2018 to the end of 2025 [F10 §6].
  - **Sweeps** trade one fixed 0.01-lot unit on a balance too large to stop out, so every setting is measured over the whole window. The same baskets are then replayed on a $2,000 account with the unit rule (`metrics.replay_account`), and that replay decides "wiped". A basket still open at the end counts with its worst floating loss [RM; git c126ac2].
  - **Risk-sized strategies** are rounded down to 0.01 lot; a signal that cannot buy 0.01 lot is skipped and counted. At 2026 prices on $2,000, the 1%-risk London breakout needed a median $2,617 account and the noise-area rule $3,104; they skipped 221 of 224 and 228 of 251 signals in the last year [F10 §5; `signal_sizes.csv`]. Balke's gold rules need a balance at least equal to the gold price, about $3,900 [BK §10].
  - **Start-date effect:** the 1%-risk Turtle made $113,722 over 8 years from a 2018 start; started in Nov 2021 it made about what the unit-sized Turtle made [F10 §4].
  - Published strategies were run on their own sizing and on the bot's unit rule [F10; BK].
- **Costs:**
  - Charged: the recorded spread on every fill. Not charged: commission (Exness Standard has none) and swap (taken as zero; neither was read from a real account) [BT].
  - The gold live settings paid $2,945 of spread in one quarter, 39% of the winners' gross profit [BT finding 7].
  - Sensitivity, gold live settings, one quarter, median of 4 timings [BT, "How fragile"]: spread × 1 −$69.78, × 1.25 −$471, × 1.5 −$1,320, × 2 −$2,000; latency 300 ms −$313, 1,000 ms −$1,415; adverse slippage of 0.02 per fill −$454, 0.1 −$2,000.
  - **Breakout fills on bars are kind.** A third-party real-tick test of a breakout EA found that 84% of gold stop entries filled worse and none better; the 1-minute model overstated profit by 6.6% on gold and 16% on USDJPY [BK, "Read this first"].
  - **Swap matters for long holds:** Turtle trades last a median of about 10 days, up to 69 days (System 1) or 179 days (System 2) [MT §13].
- **Loop-timing ensembles** [robustness.py; RM; BT; git 48933e6]:
  - **Why:** the live loop sleeps 1 s, then spends a varying time on its terminal calls, plus 0.1 s after an order and 1.1 s after a ladder add. Which tick a poll lands on decides whether the bot is inside a basket when a sharp move starts, and a few large baskets decide a quarter [BT finding 3].
  - **How:** one "timing" is the live cadence with every pass a random 0 – 200 ms longer, from a reproducible seed; seeds 1 – 8 per quarter (`live_timing`, `ENSEMBLE_JITTER_MS = 200`).
  - **Fixed phase offsets do not work.** The grid moves by 0.1 s with every order, so runs started half a second apart fall onto the same grid. The early "eight timings" were at most three distinct paths; the adversarial review found this [git 48933e6].
  - **Size of the effect:** gold live settings, 13 Aug – 13 Nov 2026: −$2,000 to +$58 over eight timings (median −$351), −$793 on the fixed grid [BT finding 3]. At one fixed unit a gold quarter moved by $2,197 at the median and up to $3,516 [BT]. The final ten's last year: the timings spanned about 8% of the median for V3-lite and 21% for Top 3 ($3,708 – $4,674) [F10 §5, §11].
  - The 8-year, 5-year and 2018 – 2020 windows used one fixed timing, so differences smaller than the timing spread are not rankings [F10 §11].
- **The robustness battery** [robustness.py; BT]: a slower loop (1.0 – 2.0 s per pass); order latency (0 – 1,000 ms); a wider spread (× 1.25 – × 3) and adverse slippage; the start date moved up to 14 days; each month and each week on a fresh $2,000; a bootstrap of whole trading days (5,000 draws, baskets re-sized by the unit rule). Gold live settings: 65% of bootstrap draws ended below the start and 29% wiped [BT].
- **Figures that mislead:**
  - **A high win rate:** gold live, 93.5% of 3,620 baskets won, 94.1% needed [BT finding 2].
  - **One run is one path** (above).
  - **In-sample windows:** the final ten's 5-year and 1-year windows lie inside the selection data; only Nov 2018 – Dec 2020 was a fair test [F10].
  - **A single strong year:** more than half of V3-lite's 8-year profit on gold, $6,070 of $9,957, came in 2026 [F10].

### 3.4 Windows, pre-registration and hold-outs

| Stage (2026) | Windows (UTC) | Source |
|---|---|---|
| First pipeline (14 Nov) | IS 13 Aug → 13 Nov 2026; OOS1 and OOS2, the two quarters before; HO2 and HO1, 13 Aug 2025 → 13 Feb 2026 (hold-out); one 15-month run 13 Aug 2025 → 13 Nov 2026 | [RM; BT] |
| Round 1, V2 (14 Nov) | the same five quarters; chosen on the three 2026 quarters | [IM] |
| Round 2, V3-lite (14 – 15 Nov) | DEV 13 Aug 2025 → 13 Nov 2026 (5 quarters); CONFIRM Jan 2024 → Jun 2025 (6 quarters); FINAL Feb → Dec 2023 (January 2023 only warms the indicators) | [LC; IM] |
| Optimiser defaults | development 1 Jul 2025 → 13 Nov 2026; confirmation 1 Jan 2024 → 1 Jul 2025; reserved before 1 Jan 2024 | [OPT] |
| Round 3, owner's rules (15 Nov) | 15 quarters, Feb 2023 → Nov 2026, all seen before | [LC] |
| Round 4 (15 Nov) | search on 1 Jan 2023 → 13 Nov 2026 in 16 quarter blocks; published strategies on 2023, 2024-25 and 2025-26; hold-out 2021 – 2022 | [LC; `round4/top3_v4.py`; F10 §1.2] |
| Final ten (15 Nov) | 8 years 13 Nov 2018 → 13 Nov 2026; 5 years from 13 Nov 2021; fair test 13 Nov 2018 → 1 Jan 2021; last year from 13 Nov 2025; indicator history from 1 Jan 2017 (gold) and 1 Jan 2018 (BTC) | [final10.py; F10] |
| Balke (15 Nov) | the final ten's windows; Jul 2020 → Nov 2026 for the indices | [BK §3] |

**How each hold-out was used up:**
1. **HO1 and HO2** (13 Aug 2025 → 13 Feb 2026). In the first pipeline, of the 12 gold timeframe settings profitable in all three analysed quarters without a wipe, 0% were profitable in both hold-out quarters and 75% wiped the account in one; rank correlation between the periods +0.30 gold, +0.37 BTC [BT]. Round 1 then used the same two quarters as V2's hold-out (positive in both) [IM]. From round 2 on they were part of DEV.
2. **CONFIRM** (Jan 2024 → Jun 2025): run once by the round-2 studies on what DEV had fixed, then merged with DEV to choose the designs for the final exam [OPT; SR; REC; LC].
3. **FINAL 2023:** the designs and the choosing rule were written down before any 2023 result was seen, then run once. V3-lite on gold made +$106 a quarter there, against +$404 on DEV [LC; IM].
4. **2021 – 2022:** downloaded in round 4, left unread while everything was fixed, then run once [LC round 4].
5. **Nov 2018 → Dec 2020:** never read by any study. The selection rule and protocol were pushed in commit `5d1e10e` before any strategy ran on it; then it was run once [F10]. A correction followed: the warm re-check (§3.5) chose some new rows on 2021 – 2026 evidence and ran them on this window; it read no 2018 – 2020 result to choose them, but it came after the pre-registered results were known [F10 §8]. Turtle System 2 + bot votes, now a demo strategy, entered this way.
6. **Balke:** no new hold-out data; every year since 2018 had been read [BK §10].

**Mechanics:**
- **The strongest form** (the final ten): the rule, windows, engines and account were frozen in code and in `selection.json`, committed and pushed (`5d1e10e`) before the data was read; `python -m backtesting.research.final10 select` reproduces `selection.json` exactly [F10 §12].
- **Weaker forms earlier:** the 2023 exam had a pre-registered entry in `LOGIC_CHANGELOG.md`, but entry and result arrived in the same commit (`4a9215f`), so the order cannot be shown from git; 2021 – 2022 was "kept untouched" with no freezing commit before the run (`7611e01`). **For Ballom, push the freeze before every hold-out run.**
- **After a final run** nothing is changed once the numbers are seen; whatever they show is reported [LC].
- **Guards in the optimiser:** it refuses to start before 1 Jan 2024 without `--allow-reserved`; `holdout_looks.json` counts how often a hold-out has been shown, and the report says so from the second time on [OPT].

**What is left unread:** nothing older for BTC (the archive starts in Jan 2018). For gold, Jan – Dec 2016 was never downloaded; Jan 2017 – 12 Nov 2018 was read only to warm indicators [F10 §1.3; MEM]. **So the next honest test of these designs is a demo-account forward run** [LC; F10 §10]. **For Ballom, every year of Indian data is still unread: fix DEV, CONFIRM and FINAL before reading any of it.**

### 3.5 The warm-up lesson

- **What went wrong.** The published-strategy study read nothing before 1 Dec 2022 for 2023 – 2026, and nothing before Jan 2021 for 2021 – 2022 [F10 §8; external.py `EARLIEST`]. Slow filters therefore started cold: the 12-month momentum sign needs a year of history, the 200-day average about ten months. Until a filter was defined, its row opened nothing, and those idle months counted as small profits or as the one losing period the rule allows [F10 §8].
- **Found by** an independent reviewer, after the final runs.
- **The re-check:** every published row ran again with history from 2017 (gold) and 2018 (BTC) under the same rule (`selection_warm.json`). 7 of the 17 rows of the original study changed, all in their first period. Gold's two slow-filter hybrids lost in 2021 and 2023 once warm and dropped out of the ten; on BTC four rows changed and Turtle System 2 + bot votes came in [F10 §1.5, §8].
- **Rules adopted:** give every indicator its full history before the first scored period. A row that cannot trade must not count as profitable. Count "no trades" explicitly [F10; MEM].
- **Other warm-up facts:** the volatility unit needs about 300 closed H1 bars (100 bars are up to 12% off on BTC) [ML §3.6]; the Turtle's N needs about 270 D1 bars to agree to 1e-6 and its System 1 filter about 50 [MT §13]; the live code fills RSI warm-up NaNs with 100, so too short a fetch gives false extremes [MLL §2.3]; the optimiser recomputes a block if the history its warm-up reads has changed, about six months back for H4 and almost three years for D1 [OPT].

### 3.6 Multiple testing

- **How much was tried:** 20 entry signals on every closed M15 bar over 15 months [EDGE]; 432 timeframe combinations × 5 quarters [BT]; 191 designs × 5 quarters in round 1 [IM]; more than 1,200 designs by the 2023 exam plus several hundred support/resistance and recovery variants [IM]; optimiser v3 on gold, 645 settings of 1,555,200 combinations [OPT2]; round 4, 476 (gold) and 490 (BTC) settings of 9,216 combinations [OPT4]; about 80 published-strategy rows per symbol [EXT]; the final ten's pool of 165 rows [F10]; 42 recovery mechanisms on 32,553 identical entries, 468 comparisons [REC].
- **How the results shrank:** V3-lite on gold, average per quarter, DEV +$404 → CONFIRM +$152 → FINAL 2023 +$106; V3 with one add +$453 → +$180 → +$58 [IM]. Round 4's chosen gold settings made +47.9 a month on their own selection months, but re-optimising after every block from past data only made +14.1 a month (walk-forward) [OPT4]. The search's gold Top 1 and Top 2, best on 2023 – 2026, made +11.3% and −4.5% on the fair test, against V3-lite's +17.0% [F10 §3].
- **The tools** [OPT]:
  - **Objective `lcb`:** the mean monthly net minus one standard error, so steady beats lucky.
  - **Eligibility:** not wiped in any block, and never more than a set amount below the start ($600 in round 4).
  - **The haircut:** each setting's mean is removed, the months are resampled 2,000 times and the search's pick is repeated, which shows what the best of N yields with no edge. Round 4 gold: an edgeless best would show about +41.5 a month (below +85.5 in 95% of searches) [OPT4].
  - **The probability of backtest overfitting** (CSCV; Bailey, Borwein, López de Prado, Zhu): choose on one half of the blocks, rank on the other, over all splits; 50% is noise. Round 4: 35% on gold and 17% on BTC over 12,870 splits [OPT4].
  - **Walk-forward, neighbours** (plateau or spike?), **average by parameter value, rank carry-over.**
  - **Validation of the short list on raw ticks:** a real $2,000 account under eight loop timings per block.
  - **Verdicts in words:** "No edge", "Probably overfitted", "Not proven", "Holds up on the months it was chosen on", "Holds up on every test run here". All three stored searches ended "Not proven" [OPT2; OPT4].
- **Other controls:** placebo levels for support and resistance ("control prices") [SR]; exit and recovery mechanisms compared on identical entries, so rows differ only in the mechanism: of 468 comparisons, 68 were more than two standard errors on the losing side and 9 on the winning side, where chance gives about 11 each way, and none of the 9 repeated in both periods [REC]; at most two rows per published strategy [F10 §1.2]; round 4's picks had to differ in at least two parameters [`round4/top3_v4.py`]; a pattern positive across related rules and periods counts more than the top row [EXT; IM].

### 3.7 Pitfalls found by the reviews

Each item: what went wrong and how it was fixed. All were fixed unless stated. The port defects are in §5.9.

**Engine fidelity** (adversarial reviews of 14 Nov) [git 48933e6; git c126ac2; git 2702af2; git 4a9215f]:
1. A refused order costs the same sleeps as a filled one in the live helper; without this the fast engine drifted onto a different poll grid after a refusal.
2. Stale quotes: the bot counts the market as live for 3 minutes after the last tick, so an order sent more than 1 s after a session's last quote must be refused ("market closed").
3. Broker rules must sit in the simulated terminal too (market closed, close-only, margin), so parity covers what the live code does after a refusal.
4. A run that starts just after a break or a hole inherits the close-only period or the quarantine.
5. Phase offsets made at most three paths out of "eight" (§3.3); random jitter seeds fixed it.
6. "Wiped" had meant "$2,000 down at one fixed unit"; it now means the baskets replayed on a real $2,000 account with the unit rule.
7. Cost and latency tables now give the median and range over several timings; the bootstrap re-sizes baskets by the unit rule.
8. A window that ends inside a market closure looks up the time, never the price, of the next quote.
9. With latency, the broker judges an order when it arrives, not when it was decided.
10. The hole quarantine became one fixed length for all configurations.
11. A basket still open at the end counts with its worst floating loss.
12. **Build stamps:** every output carries fingerprints of the code that decides its numbers, the live rules and the tick data; `reproduce` stops rather than stamp a result if those files change during the run [git c126ac2]. Before that, `48933e6` had added the engine and live-rule stamps; later, `25828c2` made the data fingerprint cover only the months the pipeline reads.
13. Round 2 fixes: a spread-cap tolerance; adding to winners judged on the valuation quote; the volatility unit known only after enough bars; input validation; a look-ahead test that shocks every price not yet known with the levers on [git 4a9215f].

**The parity harness** [MP; J-port; git c61c998]:
1. **Stale guards gave possible false passes.** `_apply_config` silently accepted `trend_tf`, `loss_cooldown_s`, the volatility levers, `ladder_trigger` and others that the live code did not have. On a window where such a lever never binds, parity would report OK for a rule the live code lacks. Branches with the demo contract now get every lever pushed in, or refused; for the old live root the silent acceptance remains [J-port].
2. **The comparison had two defects:** ladder RSIs compared for every tier although the kernel writes only as many as there are adds (`max_adds = 0` failed every poll); a repeated tier timeframe crashed it on duplicate columns. Fixed in `c61c998`.
3. **Where a gate sits decides whether the signals can match.** The kernel writes its trace signal before its execution-time entry gates; the live trace records the strategy's wish. A gate placed inside `strategy.py` shows "signal mismatches" even when the fills agree [MP §0].
4. **Silent failures inside the live loop.** The loop catches every exception and prints it; an unpatched clock or a broker call the simulator lacks raises inside it, and the replay then simply never trades [MP §1.2].
5. Only six module names were isolated; a new live module would leak into a second replay. Fixed in `c61c998`.
6. Fixture windows too short for real designs: use scaled-down parameters [MP §7].
7. `BacktestConfig.live()` ignores new constants and hard-codes the hedging target at $1 × unit, so `--live-root <demo branch>` would have silently tested the live levers. Fixed through `reference.contract_overrides` [MP §2; J-port].
8. **A silent fallback:** if `symbols.json` lacks the symbol, sizing falls back to the first entry and a built-in window; that is how the BTC parity windows ran against the gold checkout [MP §2].
9. Scores are rounded to one decimal by the live code, exact only for integer or half weights [MP §1.6].
10. A re-check tests the engine, not a new branch: the stored traces come from the old `app.py` [MP §4].
11. **The simulated terminal is too kind for the failure paths:** it lists positions at once, never fails a read, never switches account, and stores SL/TP without executing them. Several port defects (§5.9) were invisible to parity for this reason [J-fix1].

**Research code** [J-balke; LC; EXT]:
1. **A one-minute look-ahead** (Turnaround Tuesday): the rule decided with the close of the M1 bar that opens at 01:05, known at 01:06, and filled at that bar's open. The truncation tests cut 3 minutes before the decision, so they could not see it. Effect, gold, unit rule, 8 years: $1,923.93 (166 trades) before, $1,910 (169 trades) after. Fix: use the first price at or after the decision time; add tests that cut inside the decision minute.
2. **A daylight-saving gap dropped sessions:** 09:00 server time is 02:00 New York on the US spring-forward Sunday, a time that does not exist; the conversion returned NaT and the session was silently removed. 9 sessions lost in 2018 – 2026; BTC Range Breakout, his sizing, $10,000, 8 years: $5,018 → $5,536 (+10.3%). Fix: map a skipped time forward (`nonexistent='shift_forward'`) and test the DST days.
3. **A sizing label that did not match the computation:** a combination compounded daily returns as if size scaled smoothly, while the text said "the bot's unit rule". Replayed per 0.01 lot, the 8-year "half each" account is $15,092 (DD 14.5%), not $11,411 (16.0%).
4. **Money columns at the wrong scale:** `years_*.csv` stored every $10,000 account in $2,000 units.
5. **Three edge cases in the multi-position kernel:** the running peak included an open trade's profit but not a same-bar realised loss; a trade entering on a bar was sized before that bar's exits were booked; a wipe-out booked every open trade at the worst price. None changed a published number once fixed.
6. **Vacuous tests:** a no-look-ahead case made 0 decisions and passed by comparing empty arrays. Five mutants passed all 33 tests; making bearish candles buy gave $58,081 instead of $19,126. Fix: assert that every case makes decisions before the cut, and kill mutants (about 45 were run).
7. **A test that never exercised the ask:** on real data the ask alone blocks the buy side in 89 gold and 337 BTC sessions; a bid-only mutant turned gold Range Breakout's $22,995 into $27,467.
8. **Untested kernel paths:** an exit at the open while other trades stay open, and the unit step-up. Mutants moved gold ATR on the unit rule from $4,281 to $3,225 and $3,679.
9. **A silent partial portfolio:** `portfolio()` skipped every instance without a result curve. It kept only 3 of the 8 (gold Range Breakout, gold ATR Breakout, BTC Range Breakout) and silently dropped the 5 index instances, which had no runs yet, while the text said 8. With those 3 the review measured +23.3% a year, DD 60.4%, last year +114.2%. Fix: raise when an instance is missing.
10. An always-in reversal after a gap waited for the next decision before opening the new side (worth $0.37 in the one period it changed) [EXT].
11. **Session clocks are assumptions.** Exness reopens US index CFDs at 18:30 New York in US summer time, Balke's broker at 18:00 [BK §6]. The London rules use New York + 7 h as "server time"; on the UTC clock the same hours lose [EXT].

**Selection and write-ups** [F10 §1.2, §8, §12; git 63d64c0]:
1. The cold-start selection evidence (§3.5).
2. Imbalances the final ten named itself: our Top 1 – 3 were tuned on 15 of their 23 evidence quarters while the published strategies ran untuned; our designs were not capped at two rows; the published rows' 2021 starts on 1 Feb, ours on 1 Jan [F10 §1.2].
3. Four evidence cells were rounded twice; the selection did not change.
4. The first fact-check of FINAL10 found wrong or loose statements (the fidelity poll count, the regression count, tick density, a timing-range superlative, the falling-market list, the meaning of final equity).
5. **Generated documents:** `FINAL10.md` and `BALKE.md` are built from templates by code that fills every table from the result files ("Edit the template, not FINAL10.md"); a missing result raises an error instead of printing a wrong row [F10 header; J-balke].
6. **"Off" values and units must be stated exactly:** `entry_agree_s = 0` still filters (a buy needs the M15 score ≥ 0); `vol_cap_usd_per_unit` is USD per 0.01 lot (for BTC, 12 means $1,200 of price and never binds); the volatility unit is an EWMA of absolute H1 close changes, not an ATR and not a 24-bar mean [ML §7].

**The working environment:**
- numba (`cache=True`) and Python wrote cache files into the git-ignored `__pycache__` folders. Later runs set `NUMBA_CACHE_DIR` to a scratch folder and `PYTHONDONTWRITEBYTECODE=1`, and ran pytest with `-p no:cacheprovider` [J-balke; J-fix1].
- Never edit the engine, analysis or live files during `reproduce`: workers import whatever is on disk; the run stops rather than stamp a mixed build [MEM; RM].
- **Any engine change makes every stamped result stale**, even a lever that is off by default: check `stale_outputs(Path('backtest_results'))`, rerun `reproduce`, refresh the parity reports, then `docs` [MEM].
- Several sessions changed the same files while reviews ran; reviewers re-read the current files and dated their findings [J-balke].

### 3.8 Tools and what they cost

Owner's M1 Mac, 8 cores, 16 GB.

| Command | What it does | Cost |
|---|---|---|
| `python -m backtesting data --symbols S --from YYYY-MM --to YYYY-MM` | download and build the store | about 2 GB of downloads for Jul 2025 – Nov 2026 [RM] |
| `python -m backtesting quality --symbol S` | data-quality report | seconds |
| `python -m backtesting run --symbol S --start .. --end .. [--mode ticks] [--set k=v] [--live-root DIR]` | one backtest → `report.html`, `baskets.csv`, `fills.csv`, `equity.csv.gz`, `summary.json` | 1 – 3 s for 3 months per-second [RM] |
| `python -m backtesting parity ... --out f.json` | reference replay against the fast engine | about 12 ms per live poll, 16 – 17 min per 24 h [MP §5] |
| `python -m backtesting sweep` / `robust` | timeframe grids; timing, latency, cost, start-date, segments, bootstrap | minutes |
| `python -m backtesting reproduce [--jobs 7]` | the whole pipeline behind `backtest_results/` | 63 – 64 min [git 63d64c0; git 3a2370c] |
| `python -m backtesting docs` | rebuild `index.html`, the PNGs and `BACKTEST.md` | needs Chrome for PNGs [RM] |
| `python -m backtesting studio` | replay the bot tick by tick in a browser | – |
| `python -m backtesting optimise --space S --symbol X ...` | search with hold-out, haircut, PBO, walk-forward, validation | one gold setting on one 3-month block 1.5 – 3 s; 200 settings × 6 blocks 30 – 60 min; about 0.6 GB per worker [OPT] |
| `python -m backtesting.research.final10 select / run / supplement / warm / checks / report` | the final ten | `run` about an hour [F10 §12] |
| `python -m backtesting.research.external run / tables` | the published strategies | – |
| `python -m backtesting.research.balke run / report` | Balke's strategies | – |
| `python -m backtesting.engine.demo_parity <branch dir> S "<design>" "<start>" "<end>"` | a demo branch against the fast engine (options `--plain`, `--strict-gates`, `--initial-balance`, `--set`, `--json`) | about 13 ms per poll [J-port] |
| `python -m pytest tests -q` (`-m slow` for full-window parity) | the test suite | 470 test functions on 16 Nov 2026 (grep count); 936 tests passed at `369c75c` [git 369c75c] |

- **Environment variables:** `ALCADEIAS_STORE_DIR` (store location), `ALCADEIAS_LIVE_ROOT` (run the tests against another checkout), `NUMBA_CACHE_DIR`, `PYTHONDONTWRITEBYTECODE` [RM; MEM].
- **Software:** Python 3.10 with numpy, pandas below 3, numba, plotly below 6, dash and pytest. The `MetaTrader5` package is Windows-only and not needed [MEM].
- **What the tests cover** [RM]: indicator kernels against `indicator.py`; characterisation of the live `strategy.py`; parity with the real loop; engine invariants (the account adds up, determinism, no look-ahead, per-second series = raw ticks); fault injection into the live loop; every lever inert at its off value and doing what it says; store, config, reports and studio.

### 3.9 How the work was organised

- **The live files were never modified** on the backtest branch; every lever is a backtest setting, off by default [RM].
- **Every logic change and result** went into `LOGIC_CHANGELOG.md`, newest first, with a status [LC].
- **Independent reviewers, in parallel and read-only,** checked every study before publication: one fact-checked every figure against the result files; one tried to break the method and the code; one recomputed every account, table and median from the raw files; one read the draft as the owner would. A second round checked that every finding was fixed [F10 §12].
- **Each finding was verified by a second agent** who reproduced it before anything was changed. Severities moved both ways [J-balke].
- **Ports followed the same chain:** port, harness, verify, review, fix, spread to the other branches, re-verify, re-review [J-port; J-fix1; J-fix2].
- **Probes** ran read-only from a scratch folder, with the numba cache redirected and no bytecode written, and `git status` compared before and after [ML].
- **Credentials were never opened.** To replay a branch, only its code files were exported with `git archive` [MP §7].

### 3.10 The trust checklist: what a new backtester needs before it is trusted

Items marked **(new)** were not needed in Alcadeias but follow from trading Indian options on Fyers; they are reminders to check, not facts from this repo.

**Data**
- [ ] The exchange's or broker's own data for the exact instruments traded, with bid and ask where the bot trades on them; timestamps in one stated time zone; a reproducible downloader; cleaning that drops only impossible rows and counts them.
- [ ] **(new)** Option premiums for every strike and expiry the bot could pick, alongside the underlying it reads (Nifty spot or futures, GoldM and SilverM futures).
- [ ] Stored resolutions that match the uses: quotes for parity and timing tests, a per-second or per-minute series for sweeps, bars for warm-up, built from the same price the live code reads.
- [ ] A quality report run before any result: coverage, every silence classified (session close, holiday, halt, hole), spreads by hour and by year, large moves checked against real events.
- [ ] **(new)** A calendar: holidays, special sessions, session hours and their changes, expiry dates and changes of the expiry weekday, lot-size changes, contract specifications.
- [ ] A rule for holes in the data: close at the last quote, quarantine new entries, the same length for every configuration, tested with an artificial hole.
- [ ] A cost model with its history: every charge per order and per contract, and how each changed over the years; spreads from the data; a constant-cost scenario next to the real one.

**Engine**
- [ ] A reference replay of the bot's own unmodified code against a simulated broker API (here: Fyers), with the simulated clock patched into every module that reads time, and every exception the loop swallows recorded.
- [ ] A fast engine of the same loop, checked against the reference poll by poll on recorded windows that include a session break, a broker refusal and a crash. Report the number of polls compared. Keep the recordings somewhere durable.
- [ ] Explicit tolerances; guards that refuse any setting the live code does not implement, so a lever cannot pass silently.
- [ ] The same bar reading as the live code (forming or closed), with indicator values tested against the live functions.
- [ ] The loop's cadence: sleeps after orders, refused orders included; loop-timing ensembles with random jitter, never fixed offsets.
- [ ] Broker rules in both engines: market closed, opening or close-only periods, margin refusals. **(new)** The broker's and exchange's risk rules for options, such as margins for sold options and forced square-off, confirmed from Fyers and the exchange.
- [ ] A fill model that is not kind: market orders at bid and ask, stop orders pessimistic or tick-tested, latency and slippage tests. **(new)** Wide spreads and thin books on far strikes and near expiry.
- [ ] Accounts: margin, stop-out, a fresh account per window, a fixed unit for sweeps with a replay on the real account, and the minimum lot checked against the account size.
- [ ] A written list of what the engine does not model.

**Tests**
- [ ] Characterisation tests of the live rules, so an accidental edit is caught.
- [ ] Engine invariants: the account adds up, runs are deterministic, coarse and fine series agree.
- [ ] No-look-ahead tests that cut or shock the history just after each decision, also inside the decision minute; every case must make decisions before the cut; deliberate look-ahead bugs must all be caught.
- [ ] Mutation tests of the important rules, on both sides (buy and sell, bid and ask).
- [ ] Time-zone and daylight-saving tests; holiday tests; **(new)** expiry-day tests.
- [ ] Fault injection on the live loop: failed reads, rejected orders, restarts, reconnects, slow position listing, a wrong account, **(new)** an expired API token.
- [ ] Fixture windows in which every rule fires (scaled-down parameters if needed).

**Protocol**
- [ ] The live logic measured first and shown as a reference row in every table.
- [ ] DEV, CONFIRM and FINAL windows fixed before any data is read; a pre-registration commit (rule, protocol, code) pushed before each hold-out is read; each hold-out run once; whatever it shows reported.
- [ ] Full warm-up history before every scored period; "no trades" counted as such, never as a profit.
- [ ] Every setting tried counted; `lcb`, haircut, overfitting probability, walk-forward and neighbours reported; families of results preferred over a single row.
- [ ] Equal sizing for comparisons, plus each strategy's own sizing; results per calendar year; start-date and cost-regime checks.
- [ ] Results stamped with fingerprints of code, rules and data; stale outputs detected; documents generated from result files.
- [ ] Independent reviews (fact-check, method attack, recompute, owner read), each finding verified before it is fixed.
- [ ] A port checked by parity, then a forward test: paper trading, unless Fyers offers a sandbox or test environment for its API. The memory note's "Fyers has no MT5-style demo" is an unchecked assumption, to confirm [MEM ballom]. Compare the forward test's deals with the backtest of the same weeks [BT, recommendation 9].

---

## 4. What we found

All of §4 is **measured** on Exness CFDs with spread-only costs, no swap, and a $2,000 account in 0.01-lot steps. **None of these numbers carries over to options; only the patterns may (§6).**

### 4.0 How to read the numbers

- **The account:** a fresh $2,000 per strategy and window, nothing withdrawn, leverage 1:2000 (BTC 1:400), stop-out at 0% margin level [F10 §1.4]. **The unit rule:** unit = floor(balance ÷ 2,500) + 1, at most 10; one unit is 0.01 lot; re-derived only while flat. Per 0.01 lot, gold pays $1 for each $1 of price and BTC $0.01 [EXT]. **Risk-sized / his sizing:** the size the strategy's own source prescribes, rounded down to whole 0.01 lots.
- **Metrics:** final equity = balance plus any open position at the window's end; max DD = the deepest fall from an earlier equity peak, in %; growth / yr = CAGR; growth ÷ DD = CAGR ÷ max DD.
- **"Per quarter"** for our designs (rounds 1 – 4) is the average net profit of a fresh $2,000 account in each quarter, each quarter run 8 times with random loop timing; "(7 of 40)" means 7 of the 40 runs lost money. In [EXT] (published strategies) it means one continuous $2,000 account per period, its net divided by the period's length in quarters.
- **Engines:** our designs ran on the tick engine (§3.2), the published strategies, the V3-lite hybrids and Balke's rules on the M1-bar simulator. The 8-year, 5-year and fair-test windows replay one quote per second with one timing; the last year replays every raw tick 8 times, and our designs' figure is the median [F10 §1.4].

| Window | Dates (UTC) | How it was used |
|---|---|---|
| DEV | 13 Aug 2025 → 13 Nov 2026 (5 quarters) | explore and tune (rounds 1 and 2) |
| CONFIRM | Jan 2024 → Jun 2025 (6 quarters) | run once to confirm (round 2) |
| FINAL | Feb → Dec 2023 (4 blocks; January is warm-up) | the round-2 exam, run once |
| 2021-22 | Jan 2021 → Dec 2022 (8 quarters) | the round-4 hold-out, run once |
| 8 years | 13 Nov 2018 → 13 Nov 2026 | final ten; about 6 of the 8 years are in-sample |
| 5 years | 13 Nov 2021 → 13 Nov 2026 | final ten; in-sample |
| **Fair test** | 13 Nov 2018 → 31 Dec 2020 (2.1 years) | final ten; the only window no study had read before the selection |
| Last year | 13 Nov 2025 → 13 Nov 2026 | final ten; in-sample |

- **The markets** [F10 §5, §10, §11]: gold rose from $1,202 to $3,881 over the 8 years, peaked at $5,595 on 29 Jan 2026 and then fell 31%; its other large fall was −22% (Aug 2020 – Sep 2022). BTC rose from $6,367 to $71,361, with falls of −51% (late 2018), −72% (Jun 2019 – Mar 2020), −55% (spring 2021), −78% (Nov 2021 – Nov 2022) and −44% (the last year). Most of every trend follower's profit came from the rising stretches.

### 4.1 The live logic

See §2. In one line: wiped in every window of a year or longer on both symbols; on fresh quarterly accounts gold lost $666 – $1,480 a quarter and BTC $585 – $1,995 a quarter, depending on the period [IM; LC round 4]; the netting variant did worse [BTN].

### 4.2 Our designs (the bot's own machinery, on the tick engine)

All keep the bot's RSI / MACD votes, read on the forming bar, and the unit rule. None uses the Fibonacci ladder or the M15 force-close [F10 §9].

**Round 1 (14 Nov 2026): V2** [IM round 1]
- Rules: entries only with the H1 trend (the sign of the H1 MACD signal line on the last closed H1 bar); no ladder; target $20 and stop $20 per 0.01 lot on the whole basket; M15 force-close off; a 4 h pause after a losing basket. Chosen from 191 designs on the three 2026 quarters; the two earlier quarters then agreed.

| DEV, Aug 2025 – Nov 2026 | Live, gold | V2, gold | Live, BTC | V2, BTC |
|---|---|---|---|---|
| Average per quarter | −$1,480 | +$251 | −$585 | +$159 |
| Runs that lost | 37 of 40 | 7 of 40 | 30 of 40 | 7 of 40 |
| Runs wiped | 27 of 40 | 0 | 0 | 0 |
| Max DD, median / worst run | 100% / 102% | 9% / 13% | 27% / 95% | 6% / 9% |
| Worst basket | −$1,944 | −$34 | −$811 | −$22 |
| Baskets per quarter | 2,427 | 116 | 2,615 | 46 |

- Edge per basket: gold about +$2 on $20 of risk, BTC about +$3.50. Later: CONFIRM gold +$71, BTC −$7; FINAL 2023 gold +$30, BTC −$17 [IM].

**Round 2 (14 – 15 Nov 2026): V3, V3-lite and the 2023 exam.** The designs were frozen before 2023 was run [LC "Final exam on 2023 — designs frozen"]:
- **V3:** the live votes (H1 + M15), both M15 votes must agree, the H1 trend; target 8 and stop 8 volatility units on the whole basket; one equal-sized add released when the M5 MACD vote turns back with the basket, at least 1 unit from the entry; 4 h pause after a loss.
- **V3 without the add:** the same, no ladder.
- **V3-lite:** H1 votes only, both M15 votes must agree, the H1 trend; target 8 and stop 8 units; no ladder; 12 h pause after a loss (5 min after a win). Gold trades Mon 01:00 – Fri 22:00 UTC; BTC all week.
- **The volatility unit:** an exponentially weighted mean (weight 1/24) of the absolute H1 close-to-close move, read at the last closed H1 bar when the basket opens and kept for the basket's life (§5.4). 8 units per 0.01 lot, median: gold $16 (2023), $23 (2024), $39 (2025), $75 (2026); BTC $6, $18, $23, $16 [LC]. On 2 Feb 2026 one uncapped V3-lite gold stop was $408, about 20% of a $2,000 account [ML §5].

| Gold, per quarter (runs that lost) | DEV | CONFIRM | **FINAL 2023** |
|---|---|---|---|
| Live | −$1,480 (37 of 40) | −$675 (47 of 48) | **−$666** (24 of 32) |
| V2 | +$251 (7 of 40) | +$71 (16 of 48) | **+$30** (16 of 32) |
| V3 (one MACD-turn add) | +$453 (8 of 40) | +$180 (12 of 48) | **+$58** (17 of 32) |
| V3 without the add | +$133 (8 of 40) | +$78 (16 of 48) | **+$5** (13 of 32) |
| **V3-lite** | +$404 (8 of 40) | +$152 (0 of 48) | **+$106** (0 of 32) |

| BTC, per quarter (runs that lost) | DEV | CONFIRM | **FINAL 2023** |
|---|---|---|---|
| Live | −$585 (30 of 40) | −$1,995 (48 of 48) | **−$1,194** (32 of 32) |
| V2 | +$159 (7 of 40) | −$7 (24 of 48) | **−$17** (24 of 32) |
| V3 | +$109 (8 of 40) | +$34 (26 of 48) | **−$18** (16 of 32) |
| V3 without the add | +$100 (14 of 40) | +$60 (24 of 48) | **+$3** (12 of 32) |
| **V3-lite** | +$114 (8 of 40) | +$48 (24 of 48) | **+$7** (16 of 32) |

Source: [LC "Final exam result"; IM round 2].
- V3-lite on gold: about 25 baskets a quarter, each held about a day (median 23 – 37 h), 60 – 64% won. In 2023 the average win was +$16.49 and the average loss −$16.09; in Aug 2025 – Nov 2026 the average loss grew to −$112 against an average win of +$87, worst basket −$789 [LC]. Worst DD of any V3-lite run: gold 45% (DEV), 10% (CONFIRM), 6% (2023); BTC 9%, 13%, 4% [IM].
- **The edge is small** (gold about +$4 a basket in 2023), and more than 1,200 designs had been tried by then: the honest 2023 gold figure (+$106) is about a quarter of the DEV figure (+$404) [IM].

**Round 3 (15 Nov 2026): the owner's rules on the live logic** [LC round 3]. The owner asked to keep the live hedging logic and add (1) no new position while the H1 or H4 RSI is beyond 35 / 65, and (2) a force-close when the H1 and H4 RSI are both at the extreme against the basket. 15 quarters (Feb 2023 – Nov 2026), fresh $2,000 each, every tick, 8 timings (120 runs per row):

| Design | Gold per quarter (runs wiped of 120) | BTC per quarter (runs wiped of 120) |
|---|---|---|
| Live logic | −$941 (27) | −$1,311 (49) |
| Owner's rules, entry block read as "directional" | −$781 (6) | −$1,255 (20) |
| **Owner's rules, literal: no entry while the H1 or H4 RSI is beyond either level** | **−$175 (0)** | **−$712 (0)** |
| literal, force-close on H1 instead of M15 | −$197 (4) | −$598 (0) |
| literal entry block only (no RSI force-close) | −$129 (0) | −$772 (3) |
| literal + at most 3 ladder adds | −$148 (0) | −$620 (0) |
| "directional" + basket stop $40 per unit | −$1,057 (0) | −$1,209 (2) |
| literal + H1 trend filter | −$4 (0) | −$140 (0) |
| literal + H1 trend filter + 4 h pause after a loss | **+$9 (0)** | **−$125 (0)** |

- The entry block removed the wipe-outs on fresh quarterly accounts; it did not make the logic profitable.
- **Continuous accounts tell a different story** [R3]: Jan 2024 – Jun 2025, the literal rules were wiped on gold (9 Apr 2025) and BTC (13 Jul 2024). In the final ten, "owner's rules + H1 trend + 4 h pause" was destroyed over 8 years on both symbols: gold $1 left (79.0% of trades won, profit factor 0.54), BTC wiped on 31 Oct 2021 [F10 §2]. **Fresh quarterly accounts had hidden the risk of ruin that a ladder still carries.**

**Round 4 (15 Nov 2026): Top 1, 2 and 3 from the optimiser** [OPT4; LC round 4]
- The search: 9,216 combinations of every rule that had held up; 476 settings run on gold and 490 on BTC, on 16 quarterly blocks of Jan 2023 – Nov 2026. Objective: average month minus one standard error. A setting was out if it wiped the replayed $2,000 account in any block or took it more than $600 below its start. The three best settings that differ from each other were then run on raw ticks under 8 timings. 2021-22 was kept untouched, then run once.

| Design | Entry votes | M15 | Stop / target (vol units) | Unit cap ($ per 0.01 lot) | Adds | Pause after a loss |
|---|---|---|---|---|---|---|
| Gold Top 1 | H1 | must not oppose (`entry_agree_s = 0`) | 8 / 10 | none | 1, on an M5 MACD turn, ≥ 1 unit away | 4 h |
| Gold Top 2 | H1 | must not oppose | 4 / 8 | $12 | none | 12 h |
| Gold Top 3 | H1 | must not oppose | 8 / 10 | $12 | 1, as Top 1 | 1 h |
| BTC Top 1 | H1 | must not oppose | 8 / 8 | $20 (never binds) | none | 4 h |
| BTC Top 2 | H1 | must not oppose | 8 / 10 | $12 (never binds) | none | 4 h |
| BTC Top 3 | H1 + M15 | must not oppose | 8 / 8 | none | none | 4 h |

All use the H1 trend, force-close off and the volatility unit [R4 `top3_v4_*_designs.json`; F10 §9]. `entry_agree_s = 0` still blocks a buy when the M15 score is −1 or −2 [ML §3.2].

| Gold, per quarter | 2023 | 2024-25 | 2025-26 | **2021-22 (untouched)** | One account, 2023 – Nov 2026 | One account, 2021-22 |
|---|---|---|---|---|---|---|
| Live logic | −$666 | −$675 | −$1,480 | **−$1,154** | wiped Mar 2023 | wiped Jun 2021 |
| V3-lite | +$106 | +$152 | +$404 | **+$16** | +$7,977 (DD 32%) | +$168 (DD 11%) |
| Top 1 | +$2 | +$133 | +$685 | **$0** | +$10,446 (DD 32%) | −$43 (DD 28%) |
| Top 2 | +$30 | +$158 | +$412 | **−$16** | +$6,889 (DD 15%) | −$119 (DD 13%) |
| Top 3 | +$23 | +$115 | +$545 | **−$6** | +$5,459 (DD 37%) | −$26 (DD 21%) |

| BTC, per quarter | 2023 | 2024-25 | 2025-26 | **2021-22 (untouched)** | One account, 2023 – Nov 2026 | One account, 2021-22 |
|---|---|---|---|---|---|---|
| Live logic | −$1,194 | −$1,995 | −$585 | **−$1,767** | wiped Apr 2023 | wiped Jan 2021 |
| V3-lite | +$7 | +$48 | +$114 | **+$2** | +$907 (DD 15%) | −$25 (DD 18%) |
| Top 1 | +$26 | +$73 | +$164 | **−$39** | +$1,705 (DD 13%) | −$384 (DD 27%) |
| Top 2 | +$22 | +$145 | +$53 | **−$2** | +$2,039 (DD 16%) | −$29 (DD 17%) |
| Top 3 | +$18 | +$94 | +$160 | **−$6** | +$1,527 (DD 18%) | +$16 (DD 21%) |

Source: [LC round 4; R4]. In 2021-22 the owner's rules design averaged −$131 a quarter on gold and −$191 on BTC [R4 `top3_v4_holdout_*.csv`].
- **Verdict at the time:** gold's money was made in the 2023 – 2026 trend; in 2021-22 the best designs were flat and V3-lite was the only one in profit; on BTC no rule made more than a few dollars a quarter [LC round 4].
- **Walk-forward** (re-chosen after every block from earlier months only, then traded on the next block; 43 months traded): gold +$14.1 a month per 0.01 lot (standard error 27.9), against +$109.2 for the final best setting on the same 43 months (hindsight: those months helped choose it) and +$85.8 for V3-lite; BTC +$8.5 a month (± 10.3), against +$29.0 for the final best setting and +$15.3 for V3-lite on the same months. The best gold setting's +$101.2 is its mean over all 46 selection months [OPT4].

**Our designs in the final ten's windows** (fresh $2,000, the unit rule; last year = median of 8 timings with the range; fair test = total return over 2.1 years, growth a year in brackets) [F10 §2 – §5; F10r]:

| Gold | 8 years | 5 years | Fair test | Last year |
|---|---|---|---|---|
| **V3-lite** | $11,957 · +25.0%/yr · DD 33.0% | $10,748 · +40.0%/yr · DD 30.6% | $2,340 · +17.0% (+7.6%/yr) · DD 8.5% | $3,656 · +82.8% · DD 45.3% ($3,508 – $3,794) |
| Top 1 | $15,168 · +28.8%/yr · DD 32.5% | $12,433 · +44.1%/yr · DD 31.5% | $2,226 · +11.3% (+5.1%/yr) · DD 21.7% | $4,165 · +108.3% · DD 41.9% ($3,662 – $4,474) |
| Top 2 | $8,545 · +19.9%/yr · DD 17.1% | $8,880 · +34.7%/yr · DD 15.3% | $1,910 · −4.5% (−2.1%/yr) · DD 10.7% | $4,018 · +100.9% · DD 17.3% ($3,662 – $4,353) |
| Top 3 | $9,444 · +21.4%/yr · DD 36.4% | $7,453 · +30.1%/yr · DD 36.5% | $2,270 · +13.5% (+6.1%/yr) · DD 21.3% | $4,545 · +127.2% · DD 43.3% ($3,708 – $4,674) |
| Owner's rules + H1 trend + 4 h pause | $1 (destroyed) | $1,190 · −9.9%/yr · DD 71.9% | $1,155 · −42.3% · DD 48.4% | $1,973 · −1.4% · DD 41.0% |
| Live | wiped 21 May 2019 | wiped 15 Mar 2022 | wiped 21 May 2019 | wiped in all 8 timings |

| BTC | 8 years | 5 years | Fair test | Last year |
|---|---|---|---|---|
| V3-lite | $2,914 · +4.8%/yr · DD 18.3% | $2,898 · +7.7%/yr · DD 16.7% | $2,005 · +0.3% · DD 4.4% | $2,207 · +10.4% · DD 9.5% |
| Top 1 | $3,136 · +5.8%/yr · DD 27.2% | $3,550 · +12.2%/yr · DD 15.2% | $2,044 · +2.2% · DD 3.4% | $2,589 · +29.5% · DD 6.5% |
| **Top 2** | $4,149 · +9.5%/yr · DD 16.6% | $3,919 · +14.4%/yr · DD 16.1% | $2,081 · +4.1% · DD 2.3% | $2,119 · +5.9% · DD 13.1% |
| Top 3 | $3,549 · +7.4%/yr · DD 20.9% | $3,542 · +12.1%/yr · DD 17.7% | $2,014 · +0.7% · DD 3.2% | $2,406 · +20.3% · DD 8.0% |
| Owner's rules + H1 trend + 4 h pause | wiped 31 Oct 2021 | wiped 25 Nov 2024 | $1,274 · −36.3% · DD 37.0% | $1,928 · −3.6% · DD 15.6% |
| Live | wiped 26 Jun 2019 | wiped 21 Dec 2021 | wiped 26 Jun 2019 | wiped in 5 of 8 timings |

- **Gold V3-lite:** 809 baskets, 56.1% won, profit factor 1.41, longest dip 532 days. About 8% a year until the end of 2023; more than half its 8-year profit, $6,070 of $9,957, came in 2026 [F10 §2].
- **Gold Top 1 and Top 2** led every finalist on 8- and 5-year growth ÷ DD (Top 2: 1.16 over 8 years against V3-lite's 0.76), but they were left out by the rule for losing in 2 of the 5 selection periods, and they did worse on the fair test. Their lead came in 2024 – 2026, inside the years they were chosen on [F10 "The answer", §3].
- **BTC:** our designs made +0.3% to +4.1% on the fair test, when BTC's spread was about 0.17% of the price, ten times today's [F10 §3]. BTC Top 2 made only +7% in total over 2018 – 2023 [F10r].

**Year by year** (the 8-year accounts; % of the equity at the year's start; 2018 starts 13 Nov and 2026 ends 13 Nov) [F10 §6; `years_<symbol>_ticks.csv`]:

| Gold | 2018* | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026* |
|---|---|---|---|---|---|---|---|---|---|
| V3-lite | 0.0 | +0.5 | +17.2 | +4.1 | −1.3 | +24.3 | +23.4 | +58.7 | +103.1 |
| Top 1 | −0.8 | +2.6 | +10.1 | +13.5 | −14.9 | −1.3 | +30.2 | +130.0 | +137.2 |
| Top 2 | −0.1 | −3.6 | −0.9 | −2.4 | −2.3 | +4.9 | +19.8 | +86.3 | +100.3 |
| Top 3 | −0.3 | +4.6 | +9.5 | +1.3 | −6.3 | −1.9 | +24.4 | +101.8 | +76.8 |
| Live | −33.2 | −100.0 | – | – | – | – | – | – | – |

| BTC | 2018* | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026* |
|---|---|---|---|---|---|---|---|---|---|
| V3-lite | +0.2 | +2.7 | −2.6 | −6.1 | +5.6 | +3.0 | +14.3 | +25.3 | −0.5 |
| Top 1 | 0.0 | +0.9 | +1.4 | −17.0 | −3.7 | +7.4 | +12.2 | +27.5 | +25.0 |
| Top 2 | −0.1 | +1.4 | +2.8 | −5.3 | +4.7 | +3.4 | +30.9 | +45.1 | +2.3 |
| Top 3 | 0.0 | −1.1 | +1.8 | −7.8 | +8.6 | +6.0 | +16.7 | +11.5 | +27.8 |
| Live | −22.6 | −100.0 | – | – | – | – | – | – | – |

**Votes on the forming bar versus the closed bar** (the same V3-lite rules) [F10 §7]:

| Engine and vote timing | Gold, 8 years | Gold, fair test | BTC, 8 years | BTC, last year |
|---|---|---|---|---|
| M1 bars, votes on closed bars | $2,480 · DD 51.4% | $1,941 · DD 12.5% | $2,171 · DD 17.7% | $2,044 · DD 7.7% |
| Tick engine, votes on closed bars | $2,300 · DD 55.4% | $1,912 · DD 12.5% | $2,229 · DD 18.4% | $2,205 · DD 6.6% |
| Tick engine, votes on the forming bar (as the bot) | **$11,957 · DD 33.0%** | **$2,340 · DD 8.5%** | $2,914 · DD 18.3% | $2,207 · DD 9.5% |

- On gold the gap is the vote timing; with closed-bar votes the two engines land within $290 of each other in every window. On BTC the engines also differ; in the last year the whole gap is the engine.
- On the live logic itself, switching to closed bars made gold worse: −$6,829 over three 2026 quarters against −$4,359 live [BT item 10].

### 4.3 What each lever did

Figures are per 0.01 lot unless they say "account". "Round 2 optimiser" = the 500 randomly sampled gold settings on Jul 2025 – Nov 2026; "round 4 optimiser" = the 400 randomly sampled settings per symbol on Jan 2023 – Nov 2026; each figure is the average monthly net of every sampled setting with that value. These compare values across many settings; they are not single tests.

| Lever (backtester key) | Values tested | What it did | Verdict |
|---|---|---|---|
| **Trend filter** `trend_tf`: sign of the MACD(12, 26, 9) signal line on the last closed bar | none / H4 / H1 | Round 1, all 191 designs, per quarter: gold −$423 (none) → −$25 (H4) → +$6 (H1); BTC −$15 → +$12 → +$12 [IM R1]. Gold entries against the H4 trend lost $1.44 over the next 4 h; with it, −$0.12 [EDGE]. Round 2: H1 +$68.9 a month, H4 +$58.9 [OPT2]. H4 failed outside 2025-26 [LC] | **H1 adopted in every design**; the largest single lever on gold |
| **No ladder** `max_adds = 0` | 5 Fibonacci adds / 0 | Live logic, three 2026 quarters, 1 unit: gold's worst basket −$1,687 → −$217, BTC's −$484 → −$26; gold still lost (−$4,359 → −$2,321) [BT item 10] | **Adopted**; a stop is still needed |
| **Basket stop and target in $** | $1 target → $10 / $20 → $20 / $20 | $1 target → $10 target, $20 stop, force-close off: gold −$280 → −$55, BTC −$74 → +$83. With the trend filter, no ladder, force-close off, $5 / $10 → $20 / $20: gold +$53 → +$265, BTC +$10 → +$91 [IM R1] | adopted in V2, then replaced by volatility units |
| **Stop and target in volatility units** `stop_vol`, `target_vol` | 2 – 10 units | 8 / 8 was the best size in the round-2 ladder grid on both symbols and inside the V3-lite entry frame; across all no-ladder gold designs 6 / 6 averaged a little more [IM]. Round 4 gold: target 8 +$18.8, 10 +$19.0, 6 +$8.9, 4 +$10.0; stop 8 +$17.1; BTC target 10 best (+$5.1) [OPT4] | **Adopted** (8 / 8 in V3-lite) |
| **Dollar cap on the unit** `vol_cap_usd_per_unit` | none / $8 / $12 / $20 | Round 2 gold: $12 +$76.7 a month, none +$57.3 [OPT2]. Round 4 gold: $12 +$17.7, none +$13.0, $20 +$11.7 [OPT4]. Binds on gold only from 2025 (3.9% of H1 bars in 2025, 20.8% in 2026); never on BTC (largest BTC unit 2018 – 2026 $9.71 per 0.01 lot) [ML §3.8] | gold Top 2 and Top 3; inert on BTC |
| **Pause after a loss** `loss_cooldown_s` | 5 min / 1 h / 4 h / 12 h | Round 1: 5 min → 1 h moved gold's average net per quarter, over the round-1 designs with each setting, from −$208 to −$87 per 0.01 lot; this is not the average losing basket, although LOGIC_CHANGELOG calls it the "average loss" [IM R1]. Round 2 gold: 1 h +$67.9, 4 h +$71.0, 12 h +$52.9 [OPT2]. Round 4: gold 4 h best (+$16.7); BTC 12 h best (+$1.4) [OPT4] | **Adopted** (12 h in V3-lite; 1 – 12 h in the Tops) |
| **M15 force-close** `force_close_enabled` | on / off | Round 4: gold off +$30.1 a month (96% of settings positive), on −$1.8 (33%); BTC off +$7.7 (83%), on −$5.8 (23%) [OPT4] | **Off in every design** |
| **Entry votes** `open_weights` | H1 + M15 / H1 | Round 4: gold H1 + M15 +$16.5, H1 +$11.8; BTC H1 +$5.0, H1 + M15 −$3.1 [OPT4] | H1 in all designs except BTC Top 3 |
| **M15 agreement** `entry_agree_s` | 2 / 0 (M15 must not oppose) | Round 4: gold 0 +$16.7, 2 +$11.6; BTC 0 −$0.2, 2 +$2.1 [OPT4] | 2 in V3-lite, 0 in the Tops |
| **One bounded add** (equal size, M5 MACD turn, ≥ 1 unit away) | none / 1 | V3 against its no-add twin, per quarter: gold +$321, +$102, +$53 more (DEV, CONFIRM, 2023); BTC +$9, −$27, −$21; it makes the worst basket larger [IM] | optional on gold (Top 1, Top 3) |
| **Ladder trigger** `ladder_trigger` | `rsi_level` / `rsi_cross` / `macd_turn` / `price_step` / `profit_step` | Round 2 first reading (DEV, 1 unit), per quarter, gold / BTC: no ladder +$265 / +$81; 1 add on a price step +$219 / +$61; 1 add on a MACD turn +$216 / +$58; 2 adds on the live RSI level +$150 / +$68 [LC round 2] | **No trigger beat no ladder**; the live RSI level was the weakest |
| **Trailing exit** | off / start 1 – 2, gap 2 – 3 units | Round 2 gold: none +$81.9 a month; gap 2 +$52.3; gap 3 +$57.6 [OPT2] | rejected |
| **Time stop** `max_hold_s` | none / 12 h / 24 h | Round 2 gold: none +$72.4; 12 h +$54.7; 24 h +$64.7 [OPT2] | rejected |
| **Longer pause after any close** `reentry_cooldown_s` | 300 s / 1,800 s | Round 2 gold: +$65.6 / +$62.2 [OPT2] | no gain |
| **Spread cap on entries** `entry_max_spread` | twice the usual spread | no effect: the spread is rarely wide when the bot wants in [IM R1; LC] | rejected |
| **Daily loss limit** | 1 R / 2 R | expectancy per entry −10.7 to +3.1% and −8.3 to +0.9% of the median R across 12 cells: no better than the plain trade [REC] | not used |
| **Owner's RSI-extreme entry block** `entry_rsi_block_tfs` | off / H1 + H4 | on the live logic it removed the wipe-outs but still lost; round 4: gold none +$21.7 a month, block +$6.5; BTC block +$3.0, none −$1.1 [LC round 3; OPT4] | used by none of the six Tops |
| **Votes on closed bars** `slope_on_closed_bars` | forming / closed | gold V3-lite $11,957 → $2,300 over 8 years [F10 §7] | keep the forming bar |
| **Regime entry filter** (`fast.run(regime=...)`) | 200-day trend, 12-month momentum, 1/3/12-month TSMOM, H4 Supertrend | §4.6 | not adopted |
| **Unit auto-step** | live / fixed 1 unit | live gold quarter: unit 1 +$124, unit 2 −$912 [BT item 8] | advice: keep 1 unit until a demo quarter exists [BT recommendation 7] |

### 4.4 Ideas that found no edge

| Idea | Test | Result | Source |
|---|---|---|---|
| 20 entry signals: RSI extremes on M15 / H1 / H4, RSI divergence, bounce off and breakout of the 1-day high / low, momentum, time of day, the bot's own votes | every closed M15 bar over 15 months, 5 quarters, before costs | none statistically significant on either symbol; on gold most fading signals lose in 4 or 5 of 5 quarters; buying an oversold H1 RSI and selling an overbought one lost $2.83 per 0.01 lot over 4 h, negative in all 5 quarters | [IM R1; EDGE] |
| Support / resistance: H1, H4, D1 swings, previous day's and week's high and low, round numbers | DEV, then CONFIRM once; real levels against control and placebo prices | price turned back at a level in 34 – 36% of approaches, against 37 – 40% at control prices and 37.5% for a coin; bounce rule gold −0.12 R (DEV) and −0.15 R (CONFIRM), BTC −0.19 R and −0.15 R; placebo levels did as well or better | [SR] |
| 42 loss-recovery and position-management mechanisms | the same 32,553 entries, 12 cells (3 entry lists × 2 symbols × 2 periods) | **none raised the expectancy**; 68 of 468 comparisons more than 2 standard errors worse, 9 better (chance about 11 each way), none of the 9 repeated in both periods; the change in expectancy tracked the extra spread paid | [REC] |
| … the live ladder with no stop | same | closed 99.8 – 100% of baskets at +$1; in every cell one basket stood at least $1,358 under water at 0.01 lot; in 7 of 12 cells a single basket emptied $2,000; the deepest −$68,514 | [REC] |
| … the live ladder with a $60 or $200 basket stop | same | negative in 23 of 24 cells (−$0.12 to −$2.55 per entry) | [REC] |
| … a budget ladder (equal lots, at most 2 adds, a hard $60 budget, flat over every closure) | same | none of 31,952 baskets lost more than $60, but it earned no more than not adding ($0.06 per entry worse) | [REC] |
| … hedge lock | same | identical to closing and re-entering; a lock closed later costs one spread more than a stop | [REC] |
| … zone recovery, martingale, anti-martingale | same | zone recovery opens 5.5 – 6.9 units per entry and is negative in 19 – 22 of 24 cells; martingale and anti-martingale emptied the account in 6 of 12 cells each | [REC] |

### 4.5 Published strategies (M1-bar simulator)

**How they were run** [EXT]: ten strategies with published, codeable rules, from two literature searches; each coded once with its source's default parameters plus at most one alternative set the source gives; nothing tuned. Each ran standalone on the unit rule, risk-sized as its source prescribes, with the bot's logic as an entry filter (§4.6), and as a regime filter on V3-lite (§4.6).

**Every published row of the final ten** ("warm" = added by the warm re-check, §4.8) [F10r]:

| Gold row | Role | 8 years | 5 years | Fair test | Last year |
|---|---|---|---|---|---|
| London breakout + H1 trend | #1 | $3,924 · +8.8%/yr · DD 18.5% | $3,923 · DD 18.5% | $1,969 · −1.6% · DD 8.7% | $2,883 · +44.1% · DD 17.5% |
| London breakout, 1% risk | #2 | $3,781 · +8.3%/yr · DD 23.0% | $4,460 · DD 14.5% | $1,625 · −18.8% · DD 21.8% | $2,034 · +1.7% · DD 1.0% |
| MA 41/356 + H1 trend | #6 | $7,131 · +17.2%/yr · DD 38.4% | $4,829 · DD 38.9% | $2,237 · +11.9% · DD 10.8% | $4,420 · +121.0% · DD 40.6% |
| Noise-area momentum, vol-targeted | #8 | $3,217 · +6.1%/yr · DD 20.1% | $3,211 · DD 12.4% | $2,118 · +5.9% · DD 13.9% | $2,141 · +7.0% · DD 4.3% |
| MA 34/339 + H1 trend | #9 | $6,465 · +15.8%/yr · DD 40.8% | $5,200 · DD 41.1% | $2,243 · +12.1% · DD 11.4% | $4,018 · +100.9% · DD 43.6% |
| Donchian ensemble long/short + H1 trend | warm #8 | $3,616 · +7.7%/yr · DD 39.7% | $3,634 · DD 39.6% | $2,009 · +0.5% · DD 18.4% | $2,195 · +9.7% · DD 34.9% |
| Donchian ensemble long/short + bot votes | warm #10 | $2,552 · +3.1%/yr · DD 49.7% | $2,581 · DD 49.4% | $2,011 · +0.6% · DD 12.2% | $1,844 · −7.8% · DD 40.2% |

| BTC row | Role | 8 years | 5 years | Fair test | Last year |
|---|---|---|---|---|---|
| Turtle + bot votes (System 1) | #3 | $6,977 · +16.9%/yr · DD 46.0% | $6,305 · DD 44.6% | $2,742 · +37.1% · DD 10.7% | $3,412 · +70.6% · DD 26.4% |
| Turtle, 1% risk | #5 | $113,722 · +65.7%/yr · DD 42.3% | $6,835 · DD 36.3% | $24,161 · +1,108.0% · DD 39.5% | $2,221 · +11.0% · DD 15.4% |
| Daily volatility breakout + bot votes | #6 | $2,376 · +2.2%/yr · DD 8.6% | $2,232 · DD 9.2% | $2,035 · +1.7% · DD 1.7% | $1,989 · −0.6% · DD 6.1% |
| Daily volatility breakout | #7 | $2,505 · +2.9%/yr · DD 17.7% | $2,341 · DD 11.0% | $2,062 · +3.1% · DD 1.4% | $2,041 · +2.0% · DD 4.9% |
| Connors RSI(2) + bot votes | #8 | $2,291 · +1.7%/yr · DD 8.2% | $2,332 · DD 4.1% | $2,004 · +0.2% · DD 0.4% | $2,097 · +4.8% · DD 2.0% |
| TSMOM | #10 | $3,339 · +6.6%/yr · DD 18.8% | $2,808 · DD 14.1% | $2,129 · +6.5% · DD 8.6% | $2,280 · +14.0% · DD 10.5% |
| Turtle System 2 + bot votes | warm #1 | $7,815 · +18.6%/yr · DD 32.5% | $3,547 · DD 38.4% | $2,858 · +42.9% · DD 9.4% | $3,039 · +52.0% · DD 22.4% |
| TSMOM 12-month, vol-targeted | warm #2 | $4,130 · +9.5%/yr · DD 73.3% | $3,833 · DD 57.8% | $1,506 · −24.7% · DD 73.3% | $1,988 · −0.6% · DD 38.6% |
| Supertrend + bot votes | warm #10 | $3,056 · +5.4%/yr · DD 29.3% | $2,413 · DD 30.8% | $2,142 · +7.1% · DD 3.5% | $1,769 · −11.5% · DD 26.1% |

**Per strategy, in short** ("per quarter" figures are [EXT]'s continuous accounts for 2023 / 2024-25 / 2025-26):
- **Asian-range / London breakout (gold):** range 03:00 – 08:00 server time (New York + 7 h); OCO stops beyond it; target 2.5 R; flat at 21:00 server. Standalone it made +$11 / +$189 / +$298 a quarter and was positive in 2021 and 2022 too, but that row (score 3.47) was cut by the two-per-strategy cap and never ran on the fair test [F10 §1.2]. **The two forms that were finalists lost on the fair test:** "+ H1 trend" −1.6% ($1,968.62) and "1% risk" −18.8% ($1,624.85), so not for gold [F10 §3, §10; F10r]. **The same hours on the UTC clock lose:** −$8 / −$1 / −$8 a quarter [EXT].
- **Daily volatility breakout (BTC):** a buy stop at the previous daily close + ATR(2), stop 8%, out at the day's end. Steady but small [F10].
- **Connors RSI(2):** long when the daily close is above its 200-day average and RSI(2) < 5 (short mirror), out at the 5-day average. Flat to negative on gold. On BTC with the votes it was positive in all five selection periods (worst fresh-quarter DD 4.3%), but over 8 years it made 37 trades, a max DD of 8.2% (5-year 4.1%) and almost no money ($2,291): the safest BTC row [EXT; F10 §1.2; F10r].
- **TSMOM** (Moskowitz, Ooi & Pedersen): monthly, the mean of the signs of the 1-, 3- and 12-month returns. Small gains; the risk-sized 12-month form had a 73.3% drawdown [EXT; F10 §8].
- **The Turtle** (Original Turtle Rules): System 1, 20-day breakout with the skip-after-winner filter and the 55-day failsafe, 2 N stop, an add every ½ N up to 4, exit at the 10-day low; System 2, 55-day breakout and 20-day exit. "+ bot votes": the entry needs both M15 votes, on the last closed M15 bar, with the trade. **The only BTC rule that made real money**, at the price of 33 – 46% drawdowns and losing years. System 1 + votes lost in one calendar year of its 8-year account (2025 −31.3%), System 2 + votes in two: 2022 −3.0% ($3,880.75 → $3,764.89) and 2025 −15.2% ($6,468.98 → $5,484.45) [`years_BTCUSDm_warm.csv`, label `Turtle [alt] + bot votes`]. FINAL10 §6's "one losing year" is about the two pre-registered Turtle finalists, System 1 + votes and the 1%-risk Turtle (2025 −27.3%), not System 2. On gold the unit-rule drawdown reached 84%. The 1%-risk Turtle's $113,722 is a start-date effect: its leg size grew from 0.16 lot in 2018 to 1.01 lot in 2023; started in Nov 2021 it made $6,835 [EXT; F10 §2, §4, §6].
- **Supertrend (ATR 10 × 3) on H4:** gold's best rule of 2023 – 2026 (+$1,340 a quarter in 2025-26, three trades made $4,855 of its $7,336), but it lost in 2021 and 2022 [EXT].
- **Long-horizon moving averages** (Urquhart et al. for gold): the highest 8-year equity of the published rules on gold ($7,131 and $6,465), drawdowns near 40%. Weak in what FINAL10 calls "the hard years": MA 41/356 and MA 34/339 made −2.0% and −3.4% in 2019, +3.7% and +3.9% in 2021, −2.1% and −3.0% in 2022, −0.7% and +0.5% in 2023 [F10 §6].
- **Donchian trend ensemble** (Zarattini, Pagani & Barbon 2025): weak.
- **Noise-area intraday momentum** (Zarattini, Aziz & Barbon 2024): gold 5-year DD 12.4%, but at today's gold price its median signal needs a $3,104 account; BTC loses [F10 §5; EXT].
- **Last half-hour momentum:** loses on both symbols. **Bitcoin 10-day MAX / MIN:** small [EXT].
- **Left out on purpose** [EXT "Left out"]: **the 5-minute opening-range breakout, because an independent CFD replication found the edge goes to zero after retail spreads**; TTM Squeeze (no credible test on gold or BTC); Clenow's EMA breakout (the Turtle family); MACD + 200 EMA (negative in independent tests); grid / DCA bots (the bot's own ladder family, tested in [REC]).

### 4.6 Combinations

- **The bot's logic as a filter on published entries** ("+ bot votes" or "+ H1 trend") [EXT]: on gold the filter raised the three-period total in 10 of 20 strategy / parameter pairs, and was better in all three periods in only 3 of 20; on BTC 11 of 18, better in all three in 6 (votes) and 4 (trend). **Not a reliable improvement in general.** The exceptions where the votes helped were all on BTC: Turtle System 1 (+$696 → +$1,143), Turtle System 2 (+$599 → +$1,319, DD 44% → 33%), Connors RSI(2) (+$226 → +$239, DD 8% → 4%).
- **Published regime filters on V3-lite ("V3-lite hybrids")** [EXT; F10 §7, §8]: on M1 bars, gold 2023 – 2026, the 200-day trend filter raised the three-period total from +$1,043 to +$1,881 and cut DD from 39% to 25%. Run as the bot would run them (tick engine, forming-bar votes, added after the pre-registration):

| Gold, as the bot runs it | 8 years | Fair test | Last year |
|---|---|---|---|
| V3-lite (reference) | $11,957 · DD 33.0% | +17.0% · DD 8.5% | +82.8% · DD 45.3% |
| V3-lite + 200-day trend filter | $7,101 · DD 22.3% | +16.5% · DD 6.5% | +61.6% · DD 25.2% |
| V3-lite + 12-month momentum filter | $5,868 · DD 21.1% | +17.8% · DD 6.6% | +37.9% · DD 25.2% |
| V3-lite + H4 Supertrend filter | $5,165 · DD 35.5% | +13.2% · DD 8.1% | +15.8% · DD 45.3% |

  The filters cut gold's 8-year drawdown from 33% to about 22%, but lost 9.6% and 5.5% in 2021 (V3-lite +4.1%) and made +2.2% and −1.5% in 2023 (V3-lite +24.3%). With full warm-up both gold slow-filter hybrids lose in 2021 and 2023. **A lower drawdown, not a free improvement; not adopted** [F10 §7, §8].
- **V3-lite and Balke's gold Range Breakout on one account** (unit rule, trade replay, closed-balance drawdown) [BK §4.3]: daily return correlation 0.10 over 8 years. Half the account each: **$15,092 (DD 14.5%) against V3-lite alone $11,957 (DD 19.8% on this measure)** over 8 years; it beat V3-lite alone on final equity in every window. Below $5,000 the 0.01-lot minimum keeps both at full size.
- **Balke's 8 instances on one account** (his sizing, $10,000) [BK §7]: Jul 2020 – Nov 2026 $83,833, +39.6% a year, max DD 75.5%; 2022 −57.3%. Gold carried it; his sizing holds up to three times the balance in index value on Mondays and Tuesdays.

### 4.7 René Balke's Four Edge strategies (BM Trading GmbH)

- **Rebuilt** from his published settings files, guide and videos: 8 of his 14 live instances, nothing tuned [BK §2]. Limits: stop entries fill exactly at their level on 1-minute bars (kind, §3.3); his broker charges raw spread plus commission, the rebuild used Exness spreads.
- **Rules** [BK §2]: Range Breakout gold (range 03:05 – 06:05 server time, stops at the range edges, first fill cancels the other, stop 1%, closed 18:55, 1% risk); Range Breakout BTC (range 05:00 – 09:00, close 20:00, stop at the far side); ATR Breakout gold (an H1 candle with range > 2.5 × ATR(200) closing within 25% of its extreme, stop 0.5%, target 2%, every signal traded); Go Long (buy an index at 01:05, sell at 22:55); Turnaround Tuesday (Monday 01:05 buy below the SMA of daily closes, sell Tuesday 22:55).

| Strategy | Sizing | 8 years (indices: Jul 2020 – Nov 2026) | Fair test | Last year |
|---|---|---|---|---|
| **Gold Range Breakout** | his, $10,000 | $22,995 · +11.0%/yr · DD 24.0% (2,009 trades, PF 1.20) | +1.8%/yr | +30.8% · DD 11.6% |
| Gold Range Breakout | unit rule | $9,474 · +21.5%/yr · DD 29.4% | +2.7%/yr | +117.9% · DD 28.0% |
| Gold ATR Breakout, every signal | his | $19,126 · +8.4%/yr · DD 27.1% (PF 1.16) | +17.2%/yr | +12.0% |
| Gold ATR Breakout, one position at a time | his | $12,327 · +2.6%/yr | +11.6%/yr | +1.4% |
| BTC Range Breakout | his | $5,536 · −7.1%/yr · DD 80.2% | −21.0%/yr | +46.8% |
| BTC Range Breakout at 0.02% spread throughout | his | $168,113 · +42.3%/yr · DD 32.5% | +154.4%/yr | +39.2% |
| US30 Turnaround Tuesday | his | $11,584 · +2.3%/yr · **DD 6.2%** (PF 1.57) | – | +5.8% |
| USTEC Turnaround Tuesday | his | $13,693 · +5.1%/yr · **DD 5.7%** (PF 1.92) | – | +10.7% |
| US30 / USTEC Go Long | his | $12,749 (+3.9%/yr) / $11,296 (+1.9%/yr) | – | +14.7% / +7.0% |

Source: [BK §4 – §6; BK `results.csv`]. Full table in [BK].
- **What decided the results:** the spread decides BTC (his BTC Range Breakout pays the spread once per trade as a share of a 4-hour-range stop; before 2025 that exceeded its edge in most years); index spreads fell the same way, and Go Long trades about 250 times a year with the whole balance, so a 0.02% spread costs about 5% of the balance a year; ATR Breakout needs several positions at once (+8.4% against +2.6% a year); account size (on $2,000 his gold rules placed no trade in the last year) [BK §4 – §6, §10].
- **Against his own figures:** ATR Breakout matches his test (PF 1.16 against 1.15, 22.6% won against about 23%, 140 trades a year against 141) [BK §9].
- **Verdict** [BK §10]: gold Range Breakout is the one outside idea worth a further test, as a complement to V3-lite, after a tick-level test of its breakout fills and a demo run. BTC Range Breakout works only at today's spreads. Turnaround Tuesday is the steadiest idea of the study, profitable in every calendar year on both indices, but it earns 2 – 5% a year.

### 4.8 How the final ten were picked, and what the re-check changed

**The rule**, pre-registered in commit `5d1e10e` before any 2018 – 2020 data was read [F10 §1.2]:
1. **Pool:** every row with results in all five periods 2021, 2022, 2023, 2024-25 and 2025-26: 87 gold and 78 BTC rows (165), our round-4 designs plus the ten published strategies in every parameter set, variant and sizing.
2. **Yardstick:** fresh $2,000 accounts per quarter; the average profit per quarter in each period; our designs use the median of their 8 timings.
3. **Eligible:** a profit in at least 4 of the 5 periods, never wiped, the worst quarter's drawdown at most 50%, a positive average. That left 20 gold and 25 BTC rows.
4. **Score:** the average profit per quarter ÷ the worst quarter's drawdown in %.
5. **Diversity:** at most two rows per published strategy; rows with identical results in all five periods count once.

**The finalists** [F10 §1.2]: gold 1 London breakout + H1 trend (score 5.48), 2 London breakout 1% risk (5.35), 3 V3-lite + 200-day filter (5.03), 4 V3-lite + 12-month filter (4.21), 5 Top 3 (3.40), 6 MA 41/356 + H1 trend (3.24), 7 V3-lite (3.09), 8 noise-area (2.95), 9 MA 34/339 + H1 trend (2.84), 10 V3-lite + H4 Supertrend (1.08). BTC 1 Top 2 (4.49), 2 Top 3 (4.23), 3 Turtle + bot votes (4.08), 4 V3-lite + 1/3/12-month momentum (3.94), 5 Turtle 1% risk (3.84), 6 daily volatility breakout + votes (3.20), 7 daily volatility breakout (3.02), 8 Connors RSI(2) + votes (2.91), 9 V3-lite (2.90), 10 TSMOM (2.47). References run alongside: the live logic, the owner's rules design, gold Top 1 and Top 2, BTC Top 1, V3-lite on M1 bars.

**The selection flaw** (found by the independent review, §3.5): re-run with full warm-up under the same rule (`selection_warm.json`), gold's two slow-filter hybrids drop out and two weaker Donchian rows come in; on BTC four rows change, and **Turtle System 2 + bot votes comes in as #1** (warm evidence +119 / +13 / +45 / +198 / +180 a quarter, score 4.65 [MT §1]). This was a correction made after the results, not a pre-registration [F10 §8].

### 4.9 What went to the demo accounts

On 15 Nov 2026 the owner asked for three demo branches per symbol, running the best three strategies, chosen from the final ten's evidence [DP]:

| Branch | Strategy | Its backtest (8 years; fair test) |
|---|---|---|
| `demo_hedging_xauusd6` | V3-lite | $11,957 · DD 33.0%; +17.0% · DD 8.5% |
| `demo_hedging_xauusd7` | Top 2 | $8,545 · DD 17.1%; −4.5% · DD 10.7% |
| `demo_hedging_xauusd8` | Top 1 | $15,168 · DD 32.5%; +11.3% · DD 21.7% |
| `demo_hedging_btcusd6` | Turtle System 2 + bot votes | $7,815 · DD 32.5%; +42.9% · DD 9.4% |
| `demo_hedging_btcusd7` | Turtle System 1 + bot votes | $6,977 · DD 46.0%; +37.1% · DD 10.7% |
| `demo_hedging_btcusd8` | Top 2 | $4,149 · DD 16.6%; +4.1% · DD 2.3% |

Why these: gold V3-lite is the most dependable design, Top 2 has the best growth per unit of drawdown, Top 1 the most growth; on BTC only the Turtles made real money, and Top 2 has the lowest drawdown of our designs. The two Turtles share many trades and will move together [DP]. How they were built is in §5.7, how they were verified in §5.8.

### 4.10 The ten most important conclusions

1. **The old "Live" logic loses on both markets in every window and is eventually wiped.**
   - Gold lost $666 to $1,480 a quarter and BTC $585 to $1,995 a quarter on $2,000 [IM; LC round 4]. Every 8-year, 5-year and 15-month account was wiped, the 8-year ones by May / Jun 2019 [F10; BT]. The netting variant did worse: all 40 gold quarter-runs wiped [BTN].
   - The cause is structure: the Fibonacci ladder fires on an RSI *level*, so 26 of 32 units go in at one price within seconds; there is no stop; the $1 target is small next to the spread.
   - Its high win rate is a symptom, not an edge: gold won 93.5% of baskets and needed 94.1% [BT].
   - The live code also has no broker-side stop and several unchecked order paths (§2.9).
2. **The entry signal alone has no edge, and no choice of timeframes fixes the logic.** After an up vote gold was higher four bars later 50.8% of the time, the same as any bar [BT]. Of 432 timeframe combinations, the ones that looked best on one period failed on the hold-out: 0% profitable in both hold-out quarters [BT]. Twenty classic entry signals and support / resistance levels showed no reliable edge either [IM; EDGE; SR].
3. **What turned losses into small profits was structure, not new indicators:** trade only with the H1 trend; one position with a real stop and target on the whole basket, sized in volatility units; no ladder; a long pause after a loss; the M15 force-close off. The H1 trend filter was the largest single lever on gold (−$423 → +$6 a quarter, averaged over 191 designs) [IM R1]. On gold V2 had 0 of 40 quarter-runs wiped against 27 for the live logic, and a worst basket of −$34 against −$1,944 [IM].
4. **Averaging down never added expectancy.** 42 recovery mechanisms on the same 32,553 entries: none raised it [REC]. A mechanism only changes the shape of the result: a higher win rate is paid for with a bigger rare loss. A strictly bounded ladder can cap the loss ($60 on 31,952 baskets) but earns no more than not adding. The closest add (one equal-sized add on an M5 MACD turn) earned more than no add on gold in every period and less on BTC in two of three [IM].
5. **Gold: V3-lite, run as the bot runs it, is the most dependable design found.** $2,000 → $11,957 over 8 years (+25.0% a year, DD 33.0%); +17.0% with an 8.5% drawdown on the only unseen window; a profit in every full calendar year except 2022 [F10]. Its weaknesses: a few dollars of edge a basket; about 8% a year until the end of 2023; more than half its profit in 2026; a 45% drawdown in the last year. Top 1 and Top 2 looked better on 2023 – 2026, the data they were tuned on, but did worse on the unseen window (Top 2 −4.5%) [F10 §3]. Balke's gold Range Breakout is the one outside idea worth testing beside it (daily correlation 0.10; half and half $15,092 against $11,957) [BK §4.3].
6. **BTC: none of the bot's own designs made real money; only trend following did, through the Turtle breakout.** Our designs made +0.3% to +4.1% on the unseen window. Turtle System 2 + votes: $7,815 over 8 years (DD 32.5%) and +42.9% unseen; System 1 + votes: $6,977 (DD 46.0%) and +37.1%. The price: 33 – 46% drawdowns and a losing 2025 (−15% and −31%); System 2 also lost 3.0% in 2022 [F10; MT]. The 1%-risk Turtle's $113,722 was a start-date effect [F10 §4].
7. **Small implementation details changed results by multiples, so the backtester must reproduce the live bot exactly, checked poll by poll.** Forming against closed votes: gold V3-lite $11,957 against $2,300 over 8 years [F10 §7]. The session clock: the London breakout was profitable on New York + 7 h and lost on UTC [EXT]. Every signal against one position at a time: ATR Breakout +8.4% against +2.6% a year [BK]. Loop timing alone: the same live-logic quarter ended anywhere from −$2,000 to +$58 [BT]. Here the tick engine matched the real `app.py` on 373,614 polls [BT], and the demo branches were checked the same way [DP].
8. **Costs decide short-term strategies.** The spread took 39% of the live logic's winning gross on gold and 28% on BTC; a spread 1.25 times wider turned the gold quarter's median from −$70 to −$471 [BT]. Exness's BTC spread fell from 0.215% of the price (2018) to 0.017% (2026), and that alone decides Balke's BTC Range Breakout: −7.1% a year at real spreads, +42.3% at 0.02% [BK §5]. Rules that trade often pay the most.
9. **In-sample results flatter, so selection discipline matters more than cleverness.** Walk-forward selection made a fraction of the in-sample best (round 4, gold: +$14.1 a month against +$109.2 for the final best setting on the same 43 months) [OPT4]; V3-lite's honest 2023 result was about a quarter of its development figure [IM]; rules that worked 2021 – 2026 failed on the unseen 2018 – 2020 (the London breakout −1.6% and −18.8%) [F10 §3]. What worked: pre-register the rule and the test before reading new data; keep hold-outs untouched and run them once; give slow indicators full warm-up; test on fresh accounts per quarter **and** on one continuous account (the owner's rules design had 0 wipes on fresh quarters but was destroyed over 8 years) [LC round 3; F10]. Every year 2018 – 2026 has now been read; the next honest test is a forward run.
10. **Sizing rules and the minimum lot change what a strategy can do on a small account.** Risk-sized rules could not trade on $2,000 at today's gold price (the 1%-risk London breakout took 3 of its last 224 signals, the noise-area rule 23 of 251, Balke's gold rules none in the last year) [F10 §5; BK §10]. The unit rule ties size to the balance, not the price, so a unit's dollar exposure grew about 3.6 times on gold and 14 times on BTC from Nov 2018 to the end of 2025 [F10 §6]. Check whether the smallest tradable size fits the account and the risk rule before trusting any risk-sized result.

---

## 5. The designs and levers, the demo branches, and the engineering checklist

All of §5 is **measured** or read in the code, as of 16 Nov 2026 about 02:53 IST; the status of the second fix round in §5.7, §5.8, §5.9 and §5.13 is as checked at about 04:25 IST, after its push. Kernel line numbers are of `backtesting/engine/kernels.py`, unchanged since `9e4c71f`. "app6", "strat6", "mt6", "const6" are `app.py`, `strategy.py`, `mt5_helper.py`, `constants.py` on `origin/demo_hedging_xauusd6` (`766a523`); "appT" and "turtle" are `app.py` and `turtle.py` on `origin/demo_hedging_btcusd6` (`b082312`). [R1] is the first review of the port (7 findings), [R2] the re-review of the fixed branches (6 findings) [J-port; J-fix1].

### 5.1 Words

- **Basket:** all of the bot's positions on one side. It opens with one position, may add more, and closes as a whole.
- **Size unit:** 1 unit = 0.01 lot; units = floor(balance / 2,500) + 1, at most 10.
- **Volatility unit, v:** a price distance (§5.4). Not the size unit.
- **Poll:** one pass of the loop, about once a second.
- **Forming bar:** the bar still open, row −1 of an MT5 `copy_rates_from_pos(..., 0, n)` fetch. **Closed bar:** row −2 and older.
- **Vote:** the sign (+1, 0, −1) of a pivot slope (§2.3); 0 is "grey".
- **Slot:** 6, 7 or 8: one MT5 account each. On demo, each slot's account is shared by its gold bot and its BTC bot [DP].

### 5.2 The timing model of the backtest

| Setting | Value | Source |
|---|---|---|
| Poll interval | 1,000 ms (fixed grid) | [ML §4] |
| Wait after an open / an add | `open_order_delay_ms`: 0, the config default, in per-second runs (the sweeps and the 8-year, 5-year and fair-test windows), which do not model the 0.1 s at all; 100 in raw-tick runs (a single `run --mode ticks` unless `--set` overrides it, the tick baselines, the `live_timing` ensembles, parity). `add_order_delay_ms` 1,000 | [ML §2, §4; config.py L154; cli.py L151-152; robustness.py L44-47; parity.py L32, L92; final10.py L572; RM] |
| Wait after a close | none (live has none either) | [ML §2] |
| Eight-timing ensemble | poll 1,000 ms, jitter 200 ms, seeds 1 – 8, open delay 100 ms | [robustness.py] |
| Liveness | a poll more than 180 s after the last tick is dead: **no exit and no stop check** | [ML §2] |
| Market closed | the quote is the last before a silence of ≥ 30 min and more than 1 s old: orders refused | [ML §2] |
| Close-only after a break | 90 s / 210 s | [ML §4] |
| Costs | quoted spread only; slippage 0; commission 0; **no swap** | [ML §4; F10 §1.4] |
| Account | fresh $2,000; leverage 1:2000 (BTC 1:400); stop-out at 0% margin level | [ML §4; F10 §1.4] |
| Data holes | gold off; BTC: a ≥ 3 h archive gap closes the basket at its last quote and blocks entries for 547,200 s (6.3 days); backtest-only | [ML §4, §7] |

The **live loop is not on a fixed grid:** about 1 s of sleep plus the work time (7 timeframes × 500 bars fetched and computed per poll), plus 0.1 s after each order and 1 s more after an add [MLL §1.4].

### 5.3 The levers on one screen

The live default is `BacktestConfig.live()`, i.e. the live `constants.py` [ML §1].

| Lever | Live default | What it does | When / which bar | The trap in a port |
|---|---|---|---|---|
| `open_weights` | {H1: 1, M15: 1} | entry score over these timeframes, grey fill | every poll, forming bar, bid | none |
| `entry_agree_s` | 2 | `fc_score` must be ≥ +s (buy) / ≤ −s (sell) | every flat poll, forming M15 bar | **0 is not "off"** |
| `force_close_enabled` | True | False: the M15 force-close never fires | every basket poll | keep computing `fc_score`: it is the agreement gate |
| `trend_tf` (+ `trend_mode` 1) | None | entry only with the sign of the H1 MACD **signal line** of the last **closed** bar | at the entry decision; changes once per H1 bar | do not reuse the forming bar's signal line |
| `loss_cooldown_s` | 0 | after a losing basket, this pause **instead of** 300 s | every flat poll | state lost on restart |
| `vol_tf` / `vol_len` | None / 24 | the volatility unit v | read when a basket opens | closed bars only; persist per basket |
| `target_vol` / `stop_vol` | 0 / 0 | target / stop = multiple × v in USD, **fixed at the open** | every basket poll | per-basket state |
| `vol_cap_usd_per_unit` | 0 | caps v at cap / (contract × 0.01) | at the open | **USD per 0.01 lot**, not price |
| `max_adds` | 99 (→ 5 tiers) | number of adds = min(len(ladder_tfs), max_adds) | every basket poll | 0 = delete the ladder |
| `ladder_trigger` | `rsi_level` | `macd_turn`: an add on a turn of the tier timeframe's MACD vote | every basket poll with adds left | path-dependent arming state |
| `ladder_gap_vol` | 0 | an add also needs the price ≥ gap × v (fixed at the open) worse than the last fill | every basket poll | buy judged on the ask, sell on the bid |
| `ladder_multipliers` | Fibonacci | add n size = mult[n] × units × 0.01 | at the add | the designs add 1 unit; live would add 2 |

Inert in every design: `entry_rsi_block_tfs`, `entry_rsi_block_mode`, `fc_rsi_tfs` [ML §3.11].

### 5.4 Each lever exactly

- **The trend gate (`trend_tf = 'H1'`).**
  - Reads the sign of the MACD(12, 26, 9) **signal line** (not the MACD line, not the histogram) of the **last closed** H1 bar, on bid closes: `SG[off + K − 1]` [kernels.py L1016-1022].
  - A fresh entry is blocked when `want_side × trend × trend_mode ≤ 0` [L1217-1219]: **a signal of exactly 0, or NaN, blocks both sides.** Entries only; adds and exits are never filtered.
  - The value changes once per H1 bar, at the first tick of the next bar. MT5 behaves the same: a new bar appears as row −1 only with its first tick, so "row −2 = last closed" holds in both [ML §2; MLL §5].
  - **Port:** `macd_df['signal'].iloc[-2]` of the 500-bar H1 fetch [app6 L1537-1546]; **not** `iloc[-1]`, the forming bar's signal line, which only picks the MACD vote's pivot side [ML §3.4]. Fewer than 300 closed H1 bars block the entry [app6 L1547-1549].
- **The volatility unit (`vol_tf = 'H1'`, `vol_len = 24`)** [kernels.py L304-321]:
  - v₁ = |C₁ − C₀|; vₖ = vₖ₋₁ + (|Cₖ − Cₖ₋₁| − vₖ₋₁) / 24 for k ≥ 2; 0 ("unknown") until 24 bar-to-bar changes have been averaged. C are **bid closes of closed H1 bars**. This equals pandas `abs(close.diff()).ewm(alpha=1/24, adjust=False).mean()`.
  - **It is not an ATR** (no high or low) **and not a 24-bar simple mean:** on the latest bars of the store the simple mean was 10.54 against the EWMA's 8.82 (gold), 167.3 against 189.0 (BTC) [ML §3.6]. A weekend or daily break counts as one bar-to-bar change, as MT5's bars do.
  - A decision reads the value at the last closed bar. At the basket's open it is **fixed for the basket's life** [L1266-1289]; before every entry a gate blocks the entry while it is still 0 [L1223-1225].
  - **Bars to fetch:** 500 H1 bars match the full-history value to 3e-10 (gold) and 1e-10 (BTC); 300 bars to 3e-7; 100 bars are off by 0.4% (gold) to **12% (BTC)** [ML §3.6].
  - Port: `Indicator.vol_unit(closes[:-1], 24)`, the forming row excluded, bit for bit the kernel's arithmetic [app6 L1550-1552; R1].
  - Typical H1 values, median (p90 / max) [ML §3.6]: gold 2.04 (2021), 2.02 (2023), 2.85 (2024), 4.89 (2025), 9.40 (2026, p90 15.63, max **54.4**); BTC 266, 73, 220, 286, 196 BTC-dollars, i.e. $2.66, $0.73, $2.20, $2.87, $1.96 per 0.01 lot.
- **Target and stop, fixed at the open (`target_vol`, `stop_vol`)** [L1266-1289, L1073-1079]:
  - Per-unit target = `target_vol × v × usd_per_price`, stop = `stop_vol × v × usd_per_price`, with `usd_per_price` = contract × 0.01 (gold 1.0, BTC 0.01). For the basket: × the basket's units **at the open**.
  - **Stop first:** close when profit ≤ −stop (inclusive). **Then target:** close when profit > target (strict). Both cannot hold at once.
  - **Never updated:** not by later bars, a change in volatility, or an add [ML §3.7].
  - As prices, one leg (buy): target when bid > fill + `target_vol` × v; stop when bid ≤ fill − `stop_vol` × v. Two equal legs: the same USD over twice the lots, so the distances from the **average** price halve [ML §3.7].
  - `target_usd_per_unit = None` and `stop_loss_usd_per_unit = None` in every design: the volatility versions replace the USD ones.
  - **Tail risk:** V3-lite's stop is uncapped. On 2 Feb 2026 01:10:23 a gold sell at 4623.376 opened with v = 50.967; its stop was $407.74 and it closed at −$408.79, **one stop worth 20% of a $2,000 account** [ML §5]. V3-lite's worst 8-year basket lost $1,574.97 (largest lot 0.06) [F10r].
- **The cap (`vol_cap_usd_per_unit`)** caps **v itself** at the open, before target, stop and gap are derived: if v × usd_per_price > cap, v = cap / usd_per_price [L1276-1277]. **Units are USD per 0.01 lot:** gold $12 = a $12 move per H1 bar; **BTC $12 = a $1,200 move.** It binds on gold only from 2025 (3.9% of H1 bars in 2025, 20.8% in 2026); on BTC never. Read as price units it would make BTC targets about 100× too small [ML §3.8].
- **The pause after a loss (`loss_cooldown_s`)** [L1014, L1461, L1479]:
  - `entry_allowed = (T − last_close) ≥ (loss_cooldown if (last_lost and loss_cooldown > 0) else cooldown)`; `last_lost = (realised − commission) < 0` (strict), with the cents-rounded P/L at the close fill; `last_close = T` of the poll that **decided** the close.
  - It **replaces** the 300 s pause; wall-clock time, so it runs through weekends; only the last basket counts; no pause at the start of a run. In these designs "lost" = "closed by the stop". Verified on the 8-year trades: the shortest wait after a loss equals the pause exactly (12.00 h, 4.00 h, 1.00 h); after a win 5.0 min [ML §3.5].
  - Port: "lost" comes from the **realised deal history** (profit + swap + commission + fee of the bot's deals); a close that closed nothing starts no pause; the pause is persisted and, without the state file, rebuilt from the deal history [J-port; app6 L859-895, L985-1011].
- **Force-close off, M15 agreement kept.** `force_close_enabled = False` stops both the M15 slope force-close and the RSI force-close [L1049-1064]. The same `fc_score` remains the entry agreement gate. V3-lite (`entry_agree_s` 2): a buy needs both M15 votes up. The Tops (`entry_agree_s` 0): a buy needs `fc_score` ≥ 0, so **M15 must not be against**; FINAL10 §9's "no M15 agreement needed" is imprecise [ML §3.2]. **Port trap:** `SLOPE_TIMEFRAMES` is derived from the OPEN and FORCE-CLOSE weights only; emptying `FORCE_CLOSE_SCORE_WEIGHTS` with H1-only open weights would stop the M15 votes being computed and make `fc_score` 0 on every poll [MLL §4e].
- **H1-only entry votes (`open_weights = {'H1': 1}`).** The range becomes ±2, so `ENTRY_S` = 2 needs H1 (RSI, MACD) = (+, +), (+, 0) or (0, +) for a buy. The ladder gate `open_score > −2` then blocks an add only when H1 is fully against [ML §3.1].
- **The one add of gold Top 1 (and Top 3):** `max_adds` 1, `ladder_trigger` `macd_turn`, tier M5, `ladder_gap_vol` 1, multipliers [1, 1, 1, 1] [ML §3.10; L1113-1136]:
  - The vote is the M5 MACD vote on the forming M5 bar at the current bid; M5 votes are computed every poll but carry no weight in any score.
  - **Arming:** cleared at the open and after each add; set on **any** later poll on which the M5 vote × side ≤ 0 (against or grey), evaluated only on polls that reach the ladder branch; once armed, it stays armed.
  - **Firing:** on the first later poll with the vote × side > 0, `open_score > −2` (buy), and the gap: a buy needs last fill − ask ≥ 1 × v (v fixed at the open), a sell bid − last fill ≥ 1 × v. No time spacing.
  - **Size:** 1 unit, the same as the entry. After the add the basket's USD target and stop stay the same, which halves their distance from the average. Not gated by the window brake, the trend, the pause or the volatility gate, in the kernel as in live. Over 8 years 672 of gold Top 1's 1,240 baskets took the add [ML §3.9].

### 5.5 The order of checks, the effective parameters, and expected values for tests

**One kernel poll** (`run_kernel`, L594; loop L783) [ML §2]:
1. Advance to the latest quote at or before T.
2. **Liveness:** more than 180 s since the last tick → a dead poll: no exit, no stop check.
3. Market-closed flag; bid and modelled ask.
4. The forming-bar index of every timeframe moves at the first tick of a new bar.
5. Floating profit per position, rounded to cents; margin.
6. Units, only while flat. Trading window → brake (fresh entries only).
7. Indicators and votes on the forming bar at the bid; scores.
8. Entry direction, pause, trend of the closed bar.
9. **Flat:** BUY/SELL if the direction is set and the pause is over.
10. **In a basket, the first exit that fires:** stop → target → trailing → book → force-close → max hold. If none fired: the ladder (tier → trigger and arming → `add_ok` gate → gap).
11. Data-hole close (backtest-only); broker stop-out; fill quote.
12. **Entry execution**, refusals: brake → data-hole quarantine → long/short allowed → regime → **trend** → spread cap → **volatility unknown** → daily loss → RSI block → hours → confirm; then the broker's: market closed, close-only, margin. On a fill, **the basket's distances are fixed.**
13. Add execution (market closed, close-only, margin refusals); then disarm and record the last fill.
14. Close bookkeeping: `last_lost`, `last_close = T`.
15. T += poll + wait (+ jitter).

The entry gates are ANDed, so their order changes only the block counters. **The order that matters is the basket's: stop, then target, then (no force-close) the ladder.** The kernel's trace signal is written before the execution-time entry filters, so **put entry-only gates in `app.py` after the brake**, as the kernel does, or parity shows "signal mismatches" while the fills agree [MP §0, §6].

**One port poll** (`process_symbol`, app6 L1245-1895), in order: install the order guard and check the terminal (no answer → decide nothing) and that the account is this bot's demo account → `symbol_select` first (the replay stamps the poll time on it [MP §1.3]), the M15 source feed and the M1 market probe → this bot's positions (magic only; `None` → skip the poll), account, server time, tick → match the saved basket with the positions (pending fill, closed outside, taken over) → units → brake → liveness → for every timeframe in use: 500 bars, RSI, votes, trend from row −2, the short-history check, v on closed bars → pause → strategy: flat → entry; in a basket → **stop (≤) → target (>) → force-close (if enabled) → ladder** → execution: entry only if not braked and `entry_block_reason` is empty (votes unknown → trend → volatility unknown or short history → contract size unknown); levels fixed and saved on a filled order; adds; closes and the pause → dashboard JSON, daily trades every 60 s, history every 300 s, sleep 1 s.

**The four basket designs on the demo branches** (from `BacktestConfig.live(sym).replace(**design)` [ML §4], identical to the design blocks at the end of each branch's `constants.py`):

| Key | Live | Gold V3-lite (xau6) | Gold Top 2 (xau7) | Gold Top 1 (xau8) | BTC Top 2 (btc8) |
|---|---|---|---|---|---|
| `OPEN_SCORE_WEIGHTS` | {H1: 1, M15: 1} | {H1: 1} | {H1: 1} | {H1: 1} | {H1: 1} |
| `ENTRY_AGREE_S` | 2 | 2 | **0** | **0** | **0** |
| `FORCE_CLOSE_ENABLED` | True | False | False | False | False |
| `TREND_TF` | None | H1 | H1 | H1 | H1 |
| `VOL_TF` / `VOL_LEN` | None / 24 | H1 / 24 | H1 / 24 | H1 / 24 | H1 / 24 |
| `TARGET_VOL` / `STOP_VOL` | 0 / 0 | 8 / 8 | 8 / 4 | 10 / 8 | 10 / 8 |
| `VOL_CAP_USD_PER_UNIT` | 0 | 0 | 12 | 0 | 12 (never binds) |
| `LOSS_COOLDOWN_S` | 0 | 43,200 (12 h) | 43,200 (12 h) | 14,400 (4 h) | 14,400 (4 h) |
| `MAX_ADDS` | 99 | 0 | 0 | 1 | 0 |
| Ladder | RSI level, Fibonacci | – | – | `macd_turn`, M5, gap 1 v, 1 unit | – |
| `TARGET_USD_PER_UNIT` / `STOP_LOSS_USD_PER_UNIT` | 'live' ($1) / None | None / None | None / None | None / None | None / None |

Unchanged in all: `ENTRY_S` 2, `LADDER_S` 2, `FORCE_CLOSE_S` 1, `REENTRY_COOLDOWN_SECONDS` 300, RSI 14, MACD 12/26/9, pivots 20/2, RSI bands 60/40, votes on the forming bar, the unit rule (2,500 / 10 / 0.01), the trading window [ML §4].

- **Stop and target per 0.01 lot** at the median H1 unit of 2025 → 2026 [ML §4]: gold V3-lite 8v / 8v $39 / $39 → $75 / $75, uncapped ($408 at the Feb 2026 unit of 51); gold Top 2 4v / 8v with v ≤ $12: $20 / $39 → $38 / $75, at most $48 / $96; gold Top 1 8v / 10v: $39 / $49 → $75 / $94, uncapped; BTC Top 2 8v / 10v: $22.9 / $28.7 → $15.7 / $19.6.
- **Baskets over 8 years** (per-second replay, one timing) [ML §4]:

| Design | Baskets | Target / stop / data hole | 2-leg baskets | Hold h: median / p90 / max | Win rate |
|---|---|---|---|---|---|
| Gold V3-lite | 809 | 454 / 355 / 0 | 0 | 24.8 / 121.6 / 503 | 0.56 |
| Gold Top 1 | 1,240 | 599 / 641 / 0 | 672 | 22.3 / 93.3 / 238 | 0.48 |
| Gold Top 2 | 1,316 | 479 / 837 / 0 | 0 | 11.9 / 63.9 / 265 | 0.36 |
| BTC Top 2 | 1,110 | 535 / 569 / 6 | 0 | 24.2 / 116.2 / 599 | 0.48 |

- **Expected values a port's tests assert** (fast engine, February 2026, each basket's unit recomputed independently) [ML §5; J-port]:

| Case | Expected |
|---|---|
| Gold V3-lite, 2026-02-02 01:10:23 SELL 4623.376 | v 50.967 (uncapped), stop $407.74, closed at −$408.79 |
| Gold Top 3, 2026-02-02 04:05:14 SELL 4603.890 | v 49.726 capped to 12 → target $120.00, stop $96.00, gap 12.000; add at 4655.265; stopped at −$96.20 |
| Gold Top 3, 2026-02-17 00:52:16 SELL 4957.284 | v 9.931 (not capped) → target $99.31, stop $79.45; add 9.985 against the entry; target at +$99.44 |
| BTC Top 2, 2026-02-06 19:39:35 SELL 70270.95 | v 725.7 → target $72.57, stop $58.06; the cap would start at v = 1,200 |
| Shortest pause after a loss | Top 3 1.45 h (pause 1 h); V3-lite 26.4 h (12 h); BTC Top 2 4.00 h (4 h); after a win 5.0 min |

### 5.6 The Turtle, as the backtest runs it and as the port runs it

The two BTC Turtle rows exist only in the M1-bar simulator of `research/external.py`; the tick engine has no breakout, pyramid or channel code, so **no poll-by-poll parity exists for the Turtle** [MT §0]. Full detail: [MT].

- **Bars:** M1 bid bars from the archive; ask = bid + the M1 bar's mean spread. **D1 bars = UTC calendar days** (on BTC no day was ever merged, 2018 – 2026: 3,233 D1 bars, all 00:00 to 00:00 UTC) [MT §2].
  - The 3,233 bars cover 3,238 calendar days (1 Jan 2018 – 12 Nov 2026): archive holes leave 5 days with no bar, 3 Mar 2021, 28 Apr 2025, 30 Aug 2025, 30 and 31 Mar 2026 [computed from the M1 store].
  - So a "20-day" channel is 20 calendar days, weekends included, except near those dates, where a K-bar channel spans K + 1 or K + 2 calendar days (21 – 22 for the 20-day channel, 56 – 57 for the 55-day one).
  - The demo port reads the terminal's bars, which may include those days, so its levels can differ from the backtest's there.
- **N:** Wilder RMA(20) of the D1 true range, seeded with the mean of the first 20 true ranges. Channels: highest high / lowest low of the last K D1 bars **including the bar that just closed**, used on the next day [MT §3].

| | System 1 + bot votes (`demo_hedging_btcusd7`) | System 2 + bot votes (`demo_hedging_btcusd6`) |
|---|---|---|
| Entry levels | buy stop at the 20-day high + 0.01, sell stop at the 20-day low − 0.01; the **55-day** levels on days the filter says skip (both sides) | 55-day high + 0.01 / low − 0.01; no filter |
| Exit channel | 10-day low (long) / high (short) | 20-day low / high |
| Stop | the tighter of 2 N from the fill and the exit channel; after each add 2 N from the newest fill; at each D1 close raised to the exit channel; **never loosened**; one stop for all legs | same |
| Adds | +1 leg every 0.5 N (N frozen at the entry) beyond the previous **actual** fill, up to 4 legs; not gated by the votes | same |

- **The System 1 filter** [MT §5; external.py L1218-1279]: a separate, hypothetical, unfiltered System 1 on D1 bid OHLC (one unit, no spread, no adds) takes every 20-day breakout while flat.
  - **Its exit** is the tighter of a fixed 2 N stop (from the first fill, with N of the previous day) and the previous day's 10-day low for a long (10-day high for a short). It is checked from the day after entry, with gap-at-open exits; on the entry day only the 2 N stop counts. A port that uses only the 2 N stop gets different `use20` days.
  - `use20[b]` is True only when it is flat at the close of day b **and** its last trade did not make money; it selects the levels for day b + 1. True on 18.3% of days in 2018 – 2026; of System 1's 88 eight-year trades, 51 entered on the 20-day level and 37 on the 55-day failsafe. Real trades never feed it.
- **Execution on each M1 bar** [MT §6]: gap at the open first; at 00:00 UTC raise the stop and replace the day's orders; in a position, the stop first, then the adds; stop entries only when flat. After a stop exit inside M1 bar j, `next_ok = t[j] + 60`, so entries resume from the next M1 bar's open; after a gap exit at the bar's open, `next_ok = t[j]`, so an entry can fill in that same bar (external.py L594, L683, L717, L769). The port uses "not in the M1 bar of the last exit". A buy triggers when the **ask** high reaches the level, a sell when the **bid** low does; the fill is at the level, or at the open if the bar opened beyond it. **The vote gate:** the entry needs the M15 agreement of the **last closed** M15 bar (RSI vote and MACD vote both +1 for a long, both −1 for a short, no grey fill). **One fill cancels both orders for the rest of that UTC day.**
- **Vote-delayed fills:** if the price is already beyond the level when the vote turns on, the trade fills at the ask open of the M1 bar that starts at that M15 close, effectively a market order. Over eight years the vote delayed 46 of System 1's 88 entries and 30 of System 2's 60. Of those, 39 and 28 filled worse than the level, 38 and 27 of them at the open right after an M15 close. Excess over the level: mean 0.117 N (System 1) and 0.161 N (System 2) [MT §7, §14].
- **Sizing:** units = floor(realised balance / 2,500) + 1, at most 10, **fixed at the first fill**; every leg is units × 0.01 lot [MT §8].

| Row | 8 years | 5 years | Nov 2018 – Dec 2020 | Last year |
|---|---|---|---|---|
| System 1 + votes | $6,977.48, DD 46.0%, 88 trades, PF 1.56 | $6,304.88, DD 44.6% | $2,742.20, DD 10.7% | $3,412.49, DD 26.4%, 11 trades |
| System 2 + votes | $7,814.72, DD 32.5%, 60 trades, PF 2.15 | $3,546.56, DD 38.4% | $2,857.89, DD 9.4% | $3,039.45, DD 22.4%, 7 trades |

Source: [MT §0, §11; F10r]. Win rates about 38%. Selection caveat: System 1 + votes was a pre-registered finalist; System 2 + votes was picked by the warm re-check, after the results [MT §1; F10 §8].

**How the demo port runs it** (`turtle.py` + `_process_turtle`; pure rule functions fed closed bars, quotes, the vote and the fills) [turtle; appT; CLd demo.2]:

| Rule | Port |
|---|---|
| D1 levels | the last 1,000 closed D1 bars; no trading below 300 |
| When a bar counts as closed | by the **terminal's clock** (the last tick's time); a bar is read 2 s after its end |
| M15 vote | the bot's own `indicator.py` on the last 1,000 closed M15 bars; no vote with fewer than 100; an entry needs a vote read in the current quarter hour |
| Entry | flat; the day's orders armed; ask ≥ buy level with vote +1 (bid ≤ sell level with −1); not in the M1 bar of the last exit; a vote that turns while the price is past the level enters at once |
| Orders | **market deals** at the poll that sees the trigger (the backtest fills at the level or the M1 open) |
| Adds | every 0.5 N_entry beyond the last actual fill, up to 4 legs, never in the entry's M1 bar, not vote-gated |
| Stop | one stop, the tighter of 2 N from the newest fill and the tightest exit channel seen; never loosened; checked every poll on the bid (long) / ask (short); every leg closed at market |
| Units | the unit rule on the virtual balance at the first fill, fixed for the trade |
| No window, no pause | as the backtest; the manual `brake` still stops new entries |
| Broker target | none: the live default TP of 2 × price would close a BTC long leg that doubled |
| Book | `OUTPUT_DIR/state/<symbol>_turtle.json`; without it the trade is rebuilt from the positions and the deal history |

Known differences from the backtest: market fills, slippage, spread widening, swap and commission are real; the bars are the terminal's, not the archive's; the port never merges a UTC day with fewer than 360 M1 bars into the next day, and never enters in the M1 bar of a gap exit, where the backtest can (neither case occurred on BTC 2018 – 2026); the server clock is assumed to be UTC and **not checked at runtime** [CLd demo.2; DP; J-port].

### 5.7 The six demo branches: what they run and how they are built

| Branch | Symbol | Design | Magic | Dashboard port | Output folder |
|---|---|---|---|---|---|
| `demo_hedging_xauusd6` | XAUUSDm | V3-lite | 26116 | 8061 | `C:\Alcadeias\demo_hedging_xauusd6` |
| `demo_hedging_xauusd7` | XAUUSDm | Top 2 | 26117 | 8062 | `C:\Alcadeias\demo_hedging_xauusd7` |
| `demo_hedging_xauusd8` | XAUUSDm | Top 1 | 26118 | 8063 | `C:\Alcadeias\demo_hedging_xauusd8` |
| `demo_hedging_btcusd6` | BTCUSDm | Turtle System 2 + bot votes | 26126 | 8071 | `C:\Alcadeias\demo_hedging_btcusd6` |
| `demo_hedging_btcusd7` | BTCUSDm | Turtle System 1 + bot votes | 26127 | 8072 | `C:\Alcadeias\demo_hedging_btcusd7` |
| `demo_hedging_btcusd8` | BTCUSDm | Top 2 | 26128 | 8073 | `C:\Alcadeias\demo_hedging_btcusd8` |

- Every branch sizes from a **virtual $2,000** plus its own closed P/L since `VIRTUAL_START_DATE` = 15 Nov 2026 (UTC) [design blocks; DP].
- Each slot has its own demo account, shared by that slot's gold and BTC bot, which are kept apart by magic number and virtual balance [DP; RMd].
- Their backtests are those of §4.9; every year 2018 – 2026 had been read by earlier studies, so **the demo run is the first test on data no study has seen** [RMd].

**How a branch is built.** Each was made from `hedging_<symbol><n>` **with no upstream**, so a plain `git push` cannot reach the live branch [DP]. On top of the live v3.9.2 code it has these layers (commits of `demo_hedging_xauusd6` / `demo_hedging_btcusd6`; the other branches carry cherry-picks):

| Layer | What | Commits |
|---|---|---|
| Plumbing | `mt5_credentials.json` keeps only the `demo` block; the launchers refuse `live` (`app.py` still accepted it and failed only because the file had no `live` block; its own refusal came with `1a7080d`, v3.9.2-demo.3, §5.9 item 1); own `OUTPUT_DIR`, `DASHBOARD_PORT`, `MAGIC`, `DEMO_BRANCH`; the daily-trade folder follows `OUTPUT_DIR` | `8fad5ef` / `1e3dd84` |
| The port (v3.9.2-demo.1) | every lever as a constant **defaulting to the live value**; magic on every order; reads keep only own positions; units from the virtual balance; per-basket state in `OUTPUT_DIR/state`; design checked at start | `22c382d` / `686c6e3` |
| The Turtle (v3.9.2-demo.2, BTC 6 and 7 only) | `turtle.py` behind `STRATEGY = 'turtle'`; the basket loop untouched | – / `b013569` |
| Design block | one block at the end of `constants.py` | `263c02f` / `a1d740b` |
| README | what it runs, its backtest, how to start it, how it is kept apart | `cf5ad63` / `03a5426` |
| Review fixes (v3.9.2-demo.3) | the seven findings of [R1] (§5.9) | `1a7080d` … `39a80a8` / `6340753` … `e2c576d` |
| Own demo account per slot (16 Nov 2026) | credentials and README only | `766a523` / `b082312` |
| Second fix round (v3.9.2-demo.4; pushed on all six on 16 Nov 2026, 03:56 IST) | the [R2] findings (§5.9, §5.13), plus two Turtle fixes | `87a7f71` … `18e422d` / `bc7cab0` … `5eca621` (Turtle: `659703d`, `6c43e1a`) |

The four basket branches share identical `app.py`, `mt5_helper.py` and `strategy.py`, comments aside; BTC 6 and 7 add `turtle.py` and the Turtle loop. A diff of xau 7 / 8 against xau 6, and of btc 7 against btc 6, shows only `constants.py` (identity, design block), the branch name in the three launchers, and `README.md` [J-fix1].

### 5.8 How the demo branches were verified

**Basket designs: the bot's own code against the backtest engine** [DP; demo_parity.py]. `demo_parity` replays the branch's own `app.py` on a simulated MT5 terminal fed with real Exness ticks, runs the fast engine on the same ticks with the design's settings, and compares at every 1 s poll the signal, scores, position count, floating P/L, unit, cooldown and pause state; then every fill and close; then the final balance. It also checks statically that the branch holds the design, and runs on a **shared $10,000 account** with a manual position, another bot's position and trades, and an own trade from before the virtual start date.

| Design | Window (UTC) | Polls | What happened | Final balance, bot / engine |
|---|---|---|---|---|
| Gold V3-lite | 2026-10-28 17:00 – 10-30 14:00 | 154,856 | buy stopped −$42.47, sell at target +$54.87; the trend held entries back on 12,290 polls | $2,012.40 / $2,012.40 |
| Gold V3-lite | 2026-06-30 00:00 – 07-01 14:00 | 133,228 | sell stopped −$65.77; the next sell opened exactly when the 12 h pause ended, stopped −$80.66 | $1,853.57 / $1,853.57 |
| Gold Top 2 | 2026-10-21 06:00 – 10-22 14:00 | 111,627 | sell stopped −$21.28, sell at target +$51.87 | $2,030.59 / $2,030.59 |
| Gold Top 2 | 2026-01-28 22:00 – 01-30 02:00 | 93,359 | buy at target +$97.26, buy stopped −$51.97, both with v capped at $12 | $2,045.29 / $2,045.29 |
| Gold Top 1 | 2026-11-02 22:00 – 11-03 14:00 | 53,960 | a 2-leg sell (the M5 MACD-turn add) at target +$82.60, a sell stopped −$64.75; 82 close-only refusals in both | $2,017.85 / $2,017.85 |
| Gold Top 1 | 2026-10-12 00:00 – 10-13 05:00 | 100,819 | buy stopped −$51.73; the next buy opened when the 4 h pause ended, 2 legs, target +$57.13 | $2,005.40 / $2,005.40 |
| BTC Top 2 | 2026-09-03 14:00 – 09-04 13:00 | 82,799 | buy at target +$20.23, buy stopped −$21.20 | $1,999.03 / $1,999.03 |
| BTC Top 2 | 2026-10-17 20:00 – 10-19 03:00 | 111,568 | sell stopped −$10.97; the next sell opened when the 4 h pause ended, stopped −$11.12 | $1,977.91 / $1,977.91 |

- **Every window: 0 signal, score and fill mismatches, no live-code errors; largest RSI difference 4.3e-14** [DP].
- **Windows** were chosen with the fast engine first, so that across a design's two windows the trend gate, the stop, the target and the pause each act at least once [DP].
- **Scaled-down replays** make every rule fire in the short fixture windows: gold 2026-11-11 15:00 – 15:45 with minute-bar votes and short pauses gave 3 baskets (2 targets, 1 stop); BTC 2026-11-09 06:00 – 07:00 with the MACD-turn add gave 9 baskets, 2 adds, 22 of 22 fills. Use `initial_balance` for the unit, not `fixed_units` (refused) [MP §7.3; DP].
- **The port at live defaults changes nothing:** exported at `22c382d` and replayed against the live configuration on XAUUSDm 2026-11-12 00:00 – 10:00: 35,978 polls, 24 baskets (20 targets, 4 force-closes, 17 Fibonacci adds, two 6-leg baskets), 82 of 82 fills, $1,626.72 on both sides [J-port]. `tests_demo/test_live_equivalence.py` replays the code before and after the port on the same synthetic market with every lever at its live default [CLd demo.3].
- **After the first fix round**, four windows replayed again were identical in polls, fills, balances and every basket [J-fix1].
- **Backstops:** the simulated terminal stores `sl` but never executes it, so a separate tick scan checked three windows: every leg carried a backstop on the correct side at twice the basket's stop; none was touched; the closest approach was 0.50 – 0.54 of the backstop distance [J-fix1].
- **The 14 recorded parity windows** of the live logic recompare identically on the extended harness [git c61c998; git bed551e].

**The Turtles: decision-level replay** [DP; J-port; J-fix1]. `tests_demo/test_turtle_replay.py` (on `demo_hedging_btcusd6` and `btcusd7`) feeds the stored BTCUSDm M1 bars to `turtle.py`'s rules in the backtest's order and compares with `external.run_path`:
- 2023-01-01 – 2026-11-13: every trade matches on its first and last M1 bar, side, legs and prices (System 1 48 trades, System 2 33; $3,579.60 and $4,119.17 to the cent).
- 2018-11-13 – 2026-11-13: 88 and 60 trades, $6,977.48 and $7,814.72, the final ten's figures to the cent. The daily levels equal the backtest's plan rows on every D1 bar; the vote equals the backtest's on every M15 bar checked.
- Run with `TURTLE_REPLAY_FROM=2018-11-13`, the backtester checkout in `ALCADEIAS_BACKTEST_REPO`, and `TURTLE_REPLAY_CACHE` for the votes (a cold run takes 80 s) [J-port].

**Tests on the branches:** `python3 -m pytest tests_demo -q -p no:cacheprovider` with `PYTHONDONTWRITEBYTECODE=1`, from the branch root, against `tests_demo/fake_mt5.py`. 69 (basket) / 105 (Turtle) tests at the port; **107 / 147 after the first fix round**, all passing on the six heads of that round: `39a80a8` and `e2c576d` (15 Nov 2026, 23:34 IST), `91cf724`, `63f18d8`, `040c6f4` and `3378e44` (16 Nov 2026, 00:08 – 00:11 IST). Only in UTC do all six fall on 15 Nov. The six suites ran in parallel after those commits, 1,184.53 – 1,276.96 s each [J-port; J-fix1]. **124 / 168 after the second fix round**, on the six heads pushed at 03:56 IST (§0.5), 20 – 22 minutes each [J-fix2]. Every replay-based fix test was run against the pre-fix code and failed there [J-fix1]. On `backtest_hedging`, `tests/test_demo_parity.py` has 27 tests of the harness extensions (about 5 s) [git c61c998].

**What the checks do not cover** [DP; J-fix1]:
- **Polls:** parity holds on a fixed 1 s grid in a simulated terminal; on the demo account the loop's timing, the feed, requotes and slippage differ. The eight-timing spread is the guide (gold Top 3 last year: $3,708 – $4,674). The live loop makes about 7 rate fetches per poll, so it runs slower than 1.0 s [R1].
- **The broker backstop** is never executed by the simulated terminal (tick scans only).
- **Failure paths** (terminal down, wrong account, failed reads, the 10 s pending fill) are exercised only by `tests_demo` with the fake terminal.
- **Turtle fills** are market orders at the poll; the backtest filled at the level or the M1 open.
- **Swap:** if the demo account charges it, it enters the realised P/L, so it decides whether a basket "lost" (the pause) and moves the virtual balance.
- **A lost state file** rebuilds a gold Top 1 basket with its add disarmed.
- **The server clock** is assumed UTC for the Turtle's D1 boundary.

### 5.9 The engineering checklist: every defect the reviews found, and the generic lesson

Status as of 16 Nov 2026 about 04:25 IST. Every fix in the table is pushed. The second-round fixes were cherry-picked from `demo_hedging_xauusd6` (the Turtle fixes from `demo_hedging_btcusd6`) onto all six branches, and pushed at 03:56 IST after every branch's full test suite passed (§0.5).

| # | Item | Found by | Severity | Fix commit | Status |
|---|---|---|---|---|---|
| 1 | Trade on the intended account only | [R1] #1 | high | `1a7080d` | pushed |
| 2 | Never log in on a terminal another account holds | [R2] #1 | high | `87a7f71` | pushed |
| 3 | Account switch between the check and the positions read | [R2] #2 | medium | `ed1594e`; Turtle `659703d` | pushed |
| 4 | Keep each bot's positions apart (magic) | port design | – | `22c382d` | in place |
| 5 | Size from the strategy's own ledger (virtual balance) | port design | – | `22c382d` | in place |
| 6 | Survive a restart (state file, rebuild) | port design | – | `22c382d` | in place; the add's arming cannot be rebuilt |
| 7 | A fill the broker has not listed yet | [R1] #2 | medium | `825c63f` | pushed |
| 8 | Broker-side backstop | [R1] #3 (+ [R2] #5) | medium | `1c3f434`, `cad41e9`; `9101642` | pushed |
| 9 | Reconnect after a terminal restart | [R1] #4 | medium | `a34fe2e` | pushed |
| 10 | A failed read is not an empty answer | [R1] #5 | low | `1aaede4` (deal history: `22c382d`) | pushed |
| 11 | No entry on votes the poll does not have | [R1] #6 | low | `cfe43d2` | pushed |
| 12 | No decision on a short history | [R1] #7 | low | `38bfaa4` | pushed |
| 13 | Partial closes | port design (+ [R2] #3) | low | `22c382d`; `8c8f5ad`; Turtle `6c43e1a` | own partial close in place; one leg closed outside: pushed |
| 14 | Logs that flood | [R2] #4 | low | `d77c323` | pushed |
| 15 | Refuse an impossible design at start | port design | – | `22c382d` and later | in place |
| – | Microsecond window between the account check and `order_send` | [R2] #6 | low | none possible in code | deployment rule (§5.12) |
| – | A terminal still logging into its saved account when the bot attaches reads as having no account, so the bot logs in | [J-fix2], named by the fix round | – | none possible in code | deployment rule (§5.12) |

Only one MT5 installation per slot closes these last two gaps [J-fix2; the demo.4 README's safety section].

1. **Trade on the intended account only.** *Risk:* all demo bots attached to one terminal; only the credentials file and the launchers stood between them and live trading; the code accepted `live`, never checked `account_info().trade_mode`, and checked nothing before `order_send`. *Fix* [CLd demo.3; app6 L456-460, L533-577, L1060-1167]: at start refuse unless the account is a **demo**, **hedging** account with **the login of the credentials**; `live` refused by the command line and by `load_credentials` before the file is opened; every poll and **every `order_send`** re-reads `account_info()`, and a wrong account means the poll decides and sends nothing (one `ACCOUNT_REFUSED` event when the problem starts, `ACCOUNT_OK` when it ends). *Generic form:* before every order, verify the session belongs to the expected account and environment (paper / live); make "live" impossible to select on a test branch, in code.
2. **Never log in on a terminal another account holds.** *Risk:* a login switches the account for **every process attached** to an MT5 terminal. In a probe, after the slot-7 bot started, the slot-6 bot was refused on 300 of 300 polls and never recovered; a live bot on the same terminal would be pulled off the real account. The fake terminal's `login()` never switched the account, so the tests could not show it [R2]. *Fix* (`87a7f71`, local): read `account_info()` right after `mt5.initialize()`; no account → log in; this bot's account → no login; any other account → detach without logging in, ERROR `TERMINAL_IN_USE` ("give this slot its own MT5 installation"), retry with back-off [J-fix2]. *Generic form:* a bot must never change the global state of a shared session that other processes use; detect "held by someone else" and refuse.
3. **The account can change between the check and the read.** *Risk:* the poll checked the account, then read the positions in another lock block; a switch in between handed it another account's positions, so the open basket was booked as "closed outside the bot" and rebuilt [R2]. *Fix* (`ed1594e`, local): read the account again right after the positions, in the same lock block. The Turtle loop got the same fix (`659703d`, local) [J-fix2]. *Generic form:* validate the context **after** reading the data you will act on, in the same critical section.
4. **Keep each bot's positions apart.** Live reads every position on the symbol, so manual trades or another bot's positions become part of "the basket", and a foreign position on the other side freezes it. *Port* [CLd demo.1; mt6]: every order (open, add, **close**) carries `MAGIC` and a comment (cut to **31 characters**, the MT5 limit); reads, counts, profit and closes keep only own positions; the bot's deals = deals with its magic plus any deal on a position it opened. Tested on a shared account in every parity replay [DP]. *Generic form:* tag every order with a per-bot identifier and filter every read and every close by it; never close "all positions on the symbol".
5. **Size each strategy as its backtest did.** Two bots share each demo account, whose balance is not $2,000. *Port:* virtual balance = $2,000 + profit + swap + commission + fee of the bot's deals since `VIRTUAL_START_DATE`, the unit rule on it, re-derived only while flat; if the history read fails, the last value or $2,000 [app6 L824-837]. *Generic form:* on a shared account, size from the strategy's own ledger.
6. **Survive a restart.** *Risk:* live keeps only `units` (reset to 1) and the last close time (reset to 0) in memory; after a restart mid-basket the stop and target would scale with unit 1, the distances would be gone, and a 12 h pause would end at once [ML §7]. *Port* [CLd demo.1; app6 L757-791, L897-927]: `OUTPUT_DIR/state/<symbol>_state.json` holds the open basket and the last close, written **atomically** (temporary file + `os.replace`), refused if written for another symbol or magic, in a sub-folder because the dashboard lists every top-level JSON as a symbol; without it the unit, v and the pause are rebuilt from the positions, bars and deal history; **the add's arming cannot be rebuilt** (it is a path of per-poll votes). *Generic form:* list every variable the strategy carries between decisions; persist each atomically; for each, say how it is rebuilt from the broker if the file is lost.
7. **A fill the broker has not listed yet is still a fill.** *Risk:* the next poll comes about 1.1 s after an entry; if the terminal does not list the new position yet, the sync dropped the basket, the poll saw "flat", and the same votes sent a second entry. A probe with a 1.5 s listing delay sent 26 orders, 13 entry pairs under 5 s apart; the parity replays could not catch it because their terminal lists positions at once [R1]. *Fix* (`825c63f`): a basket without positions is kept 10 s after it opened. *Remaining:* a listing slower than 10 s can still allow a second entry. *Generic form:* treat "order acknowledged, position not yet visible" as an explicit state with a timeout.
8. **A broker-side stop beyond the bot's own.** *Risk:* the stops existed only inside the bot; after a VPS reboot or a terminal disconnect, positions ran with no stop. An exact broker stop would change the backtested behaviour (the backtest closes on a 1 s poll, and two-leg baskets would need their SL moved), so a backstop further out was chosen [R1; ML §7]. *Fix* (`1c3f434`; Turtle `cad41e9`): every fill carries `sl` = the decision quote ∓ 2.0 × the basket's stop distance (Turtle: 1 N beyond its stop), no `tp`, never moved; a position the backstop closes is booked by the "closed outside the bot" path; the design is refused unless the factor is > 1. *Remaining:* computed from the decision quote, not the fill; a ladder adding **in favour** could put an add's backstop inside the basket's stop (none of the six designs can; the refusal of stop + ladder without an add gap is `9101642`, local). *Generic form:* every position must have a broker-held protective order from the moment it exists, placed beyond the strategy's own exit, so the backtest is unchanged in normal operation and an outage is bounded.
9. **Reconnect after the terminal restarts.** *Risk:* after a terminal restart the Python package does not re-attach: every call answers None, positions read as flat, nothing raises, and the bot idles for ever while its positions are unmanaged [R1]. *Fix* (`a34fe2e`): every poll starts with `terminal_info()`; no answer, or not connected → decide and send nothing; after 5 such polls, shut down and initialise again with all the account checks, retried after 5, 10, 30, then every 60 s; "not connected to the trade server" only waits; on demo both launchers restart `app.py` 30 s after it exits. *Remaining:* the `.bat` restart loops are stored with LF line endings and could not be run (no Windows machine); `cmd` can misread labels in LF-only batch files [J-fix1]. *Generic form:* health-check the broker connection every cycle; decide nothing while it is unhealthy; reconnect with back-off; supervise the process.
10. **A failed read is not an empty answer.** *Risk:* `positions_get()` answering None was read as "no positions", which booked a phantom close, re-derived the unit and rebuilt the basket [R1]. *Fix* (`1aaede4`): when `positions_get()` answers None, `_own_positions` raises `TerminalReadError` and the poll books and decides nothing; a close that cannot see the positions closes nothing and reports a failure. The deal-history distinction was already in the port (`22c382d`, v3.9.2-demo.1): `get_bot_deals` returns None when the terminal returns no history, so the caller can tell "no deals" from "unknown" (mt6 L829-838). *Generic form:* every broker read must distinguish "error / unknown" from "none"; never infer an event from a failed read.
11. **No entry on votes the poll does not have.** *Risk:* a failed rates fetch left no votes, read as 0; with `ENTRY_AGREE_S` = 0 a failed M15 fetch **passed** the "M15 not against" gate (probe: H1 up with no M15 data → BUY) [R1]. *Fix* (`cfe43d2`): a fresh entry is blocked as "votes unknown" while any timeframe it needs returned no bars; exits and stops keep working. *Generic form:* missing inputs fail **closed** for entries and must not block exits; beware neutral defaults (0, 50) that a threshold reads as "allowed".
12. **No decision on a short history.** *Risk:* after a restart H1 can come back with about 100 bars, so v is off by up to 12% on BTC and a basket keeps the wrong unit for its life [R1; ML §3.6]. *Fix* (`38bfaa4`): an entry needs at least 300 closed bars of the volatility and trend timeframes; the Turtle needs 300 closed D1 and 100 closed M15 bars. *Generic form:* measure each indicator's minimum history for a given accuracy and refuse to trade below it.
13. **Partial closes.** A close that closed nothing changes nothing (it is decided again next poll; live started the pause anyway); a partial close keeps the basket and retries the rest [J-port]. If something **outside** the bot closes one leg of gold Top 1's two-leg basket (the entry's backstop while the bot is down), the old sync booked nothing, judged stop and target on the remaining leg, and could add again [R2]. *Fix* (`8c8f5ad`, local): the other legs are closed at once and the whole basket is booked as closed outside the bot. *The Turtle* (`6c43e1a`, local): if a leg disappears and the deal history shows it closed at or beyond the stop, or does not show it yet, the other legs are closed at once; a leg closed by hand inside the stop leaves the trade running [J-fix2]. *Generic form:* model a basket as a set of legs and reconcile every poll: legs closed by you, by the broker, or by hand, each with its own booking rule.
14. **Logs that flood.** `RECONNECT_FAILED` was logged on every retry; the strategy log keeps 200 entries, so an outage of about 3 h 20 min pushed every earlier entry, exit and block note out of the log the dashboard shows [R2]. *Fix* (`d77c323`, local): log the first failure, a change of reason, and at most every 15 minutes, with a count. *Generic form:* rate-limit by (event, reason); log transitions, not states.
15. **Refuse an impossible design at start.** `design_problems()` refuses unknown timeframes, a bad `VOL_LEN`, `BACKSTOP_FACTOR` ≤ 1, a volatility lever without `VOL_TF`, negative values, a bad `MAGIC`, a bad virtual start, fewer than 300 closed bars, and `STRATEGY = 'turtle'` on a basket branch [app6 L227-270; strat6 L131-151]. Change `STRATEGY` only while flat. *Generic form:* validate the whole configuration before the first order, mirroring the backtester's own validation.

**Smaller lessons** [MLL; MP; R1; CLd demo.3]:
- Check every order's return code (live logged `BUY_EXECUTED` even when refused).
- A broad `except Exception` around the loop turns a bug into silent non-trading while the loop keeps running; the replay counts every printed "Error:" line as a parity failure.
- The MT5 Python API is not thread-safe: every call goes under one lock.
- JSON cannot carry NaN: keep it out of dashboard data.
- A shared output folder made bots on one machine overwrite each other's JSON and logs: one folder and one dashboard port per bot.
- The dashboard imports constants by name; renaming one breaks it.
- Read the contract size from the broker (`trade_contract_size`); fall back to a table only if it gives none.
- Do not name a module after a standard-library one: the Turtle branches load `turtle.py` by path, because a bare `import turtle` can resolve to Python's turtle-graphics module (appT L45-55).
- **Clock domains differ:** the pause uses the machine's `time.time()`, deal times and the Turtle's bar boundaries use the broker's clock. On a broker whose server time is not UTC (for Ballom: Indian exchanges run on IST, to confirm) these would disagree.

### 5.10 Lessons from building the parity harness

These defects were in the *verification* tooling and matter as much as the bot's [MP; J-port]:
1. **The replay accepted levers the bot does not have**, so parity could "pass" a rule the code lacks. Now, for a live root whose `constants.py` defines the demo contract (`_apply_contract`), every lever is set from the config in every module that imported it, and levers neither the bot nor the contract has are refused. For the old live root, `_apply_config` still accepts `trend_tf`, `loss_cooldown_s`, `vol_tf` / `target_vol` / `stop_vol`, `ladder_trigger`, `entry_rsi_block_tfs`, `fc_rsi_tfs`, `entry_max_spread`, `agree_weights` and `trail_*` without a word, so a false pass is still possible there (§3.7, parity item 1) [reference.py L1125-1189; J-port].
2. **The comparison itself had bugs** (ladder RSIs for tiers the kernel never writes; duplicate column names). Now only the tiers the kernel writes are compared.
3. **Where a gate sits decides whether the signals match** (§5.5); `--strict-gates` refuses the tolerance for an entry the branch holds back where the kernel holds it back at execution.
4. **The simulated terminal must serve what the bot reads:** magic and comment (refusing comments over 31 characters, as MT5), position identifiers and times, `history_deals_get`, contract size, digits and volume limits, closed-bar reads, partial closes, a shared account. It **stores but never executes** `sl`/`tp`, and answers pending orders "invalid".
5. **Every clock reading in every live module must be simulated**, new modules imported and removed with the rest, no bytecode written into the branch, the bot's output folder redirected.
6. **The config reader did not know the new constants:** `BacktestConfig.live()` would have silently tested the **live** levers on a demo branch; the CLI now maps the contract with `reference.contract_overrides`. `config.py` was left alone because it is part of the engine fingerprint.
7. **Pick windows where every rule fires**, and use scaled-down settings (minute bars, short pauses) to make rare rules fire in short fixtures.
8. **Keep the old windows green** after any engine or harness change, and re-stamp reports only after recomputing them.

### 5.11 The verification ladder (reusable)

1. Port every lever with its **default = the live value**. Prove old code = new code at the defaults: a before/after replay on the same market, plus one full replay against the live configuration [J-port].
2. Set the design in one block at the end of the constants file; a static check ties that block to the backtest's design row.
3. Replay the bot's own code against the engine, poll by poll, on windows where each rule fires, on a shared account [DP].
4. For rules the engine lacks (the Turtle), compare decisions against the research simulator's trade list: first and last bar, side, legs, prices [DP].
5. Inject faults with a fake broker (account switch, terminal down, read errors, listing delay, broker stops, outages). **Prove each new test fails on the pre-fix code** [J-fix1].
6. Independent review → fixes → re-run the parity (identical before and after) → independent re-review [J-fix1].
7. Forward test on demo. Parity proves code equality, not performance [MP §8.4].

**The lesson for Ballom:** parity proved the decision code. The defects of §5.9 sat in the plumbing around it, where the simulated broker always answered normally. They were found by reading the code and by fault-injection probes on a fake terminal.

### 5.12 Deployment rules

- **Branches:** never push to the live-money branches (§1.4). Same-prefix branches differ only in credentials. Branch from a live branch with `--no-track` and push to a new remote branch of its own; check the upstream. The demo branches now track `origin/demo_hedging_*` [MEM; DP].
- **Credentials:** demo branches keep **only the `demo` block**, and `live` is refused by the launchers, the command line and `load_credentials`. Never open, print or copy the file; tests must not read it [DP; CLd demo.3; MEM].
- **One terminal per account.** Give each demo login its own MT5 installation (its own `terminal_path`), never shared with a live bot; a login switches the account for every process attached [R2]. **Do not run a live-branch bot on an account the demo bots use:** live code has no magic filter and would adopt and close their positions [R1].
- **Per-bot identity:** each bot needs its own `MAGIC`, `OUTPUT_DIR`, `DASHBOARD_PORT` and state files. Change `STRATEGY` only while flat.
- **Launchers:** on demo both launchers restart `app.py` 30 s after it exits; close the window to stop. The `.bat` files are stored with LF line endings; consider `*.bat text eol=crlf` in `.gitattributes` [J-fix1].
- **Pre-flight list before starting a demo bot:** (1) the branch is a `demo_hedging_*` branch whose upstream is its own remote branch; (2) its terminal is its own installation, logged into its own demo account, with no live bot attached; (3) `python3 -m pytest tests_demo -q -p no:cacheprovider` passes on the branch head; (4) the start-up line shows the right design, magic and virtual balance; (5) no other process writes to its `OUTPUT_DIR` and its dashboard port is free; (6) check whether the account charges swap.

### 5.13 Status and open items (16 Nov 2026, about 04:25 IST)

- **Pushed:** all six demo branches with the first fix round (v3.9.2-demo.3) and each slot's own demo account.
- **Pushed on 16 Nov 2026 at 03:56 IST (second fix round, [J-fix2]):**
  - On `demo_hedging_xauusd6`: `87a7f71` (terminal-in-use guard), `ed1594e` (account re-read after the positions read), `8c8f5ad` (a basket a backstop closed only partly is closed and booked whole), `d77c323` (a long outage does not fill the strategy log), `9101642` (a design with a stop and a ladder needs an add gap), `18e422d` (CHANGELOG v3.9.2-demo.4 and the README's safety section).
  - On `demo_hedging_btcusd6` (02:55 – 03:06 IST): the five code fixes cherry-picked (`bc7cab0`, `cd36ed9`, `e69dc79`, `d1a3540`, `2ff49ef`), two Turtle-only fixes, `659703d` (the account read again right after the Turtle's positions read) and `6c43e1a` (a leg closed beyond the stop ends the trade at once), and the demo.4 docs commit `5eca621`.
  - Cherry-picked onto the other four at 03:26 – 03:29 IST: `xauusd7` `fdf8553`, `xauusd8` `effac75`, `btcusd8` `b3a557e` (six commits each), `btcusd7` `68915b5` (eight).
  - Checks: the full suites pass on all six local heads (124 basket tests, 168 Turtle tests). The demo parity replay after the fixes ran on `xauusd6` only (V3-lite, 2026-06-30 00:00 – 07-01 14:00 UTC): PASS, 133,228 polls, $1,853.57 as before. Top 2, Top 1 and BTC Top 2 were not replayed again; their `app.py` is the same as `xauusd6`'s (`btcusd8`'s differs only in two docstring examples), and a Top 1 replay (the one design with an add) would be the most useful extra check.
  - Still running at 04:25 IST: replays of the other designs on the fixed code (Top 2, Top 1, BTC Top 2, and the Turtle decision replays) and an independent review of the fixes. Their outcome goes into `backtest_results/demo_parity/DEMO_PARITY.md`. Check `git log origin/demo_hedging_<x>` for any later fix.
- **Open by design:** no exact broker-side stop (backstop only); the Top 1 arming lost with the state file; swap; feed and cadence differences; the server clock assumed UTC; no Turtle poll-level parity [DP]. Two account gaps that only one MT5 installation per slot closes: the microsecond window between the account check and `order_send`, and a terminal still logging into its saved account when the bot attaches, which reads as having no account, so the bot logs in [J-fix2].
- **Not done:** the live-defaults replay ran on gold only, one window [J-port]. The netting variant has no demo branch and was not put through the later research [MEM].

---

## 6. For Ballom: Indian options on Fyers (Nifty, GoldM, SilverM, CE/PE pairs)

Everything in §6 is a **hypothesis** or a **to-confirm** item unless it cites a measured section of this file. No Ballom code was read, nothing was tested on options or Indian data, and no Indian-market rule was checked on the web.

### 6.0 What is known about Ballom, and what is not

- **Known only from the owner's memory note** (16 Nov 2026) [MEM ballom]: the repo is `/Users/sidharthsingh/Desktop/Ballom` ("Ballom_Fyers"); it trades CE/PE option pairs on the Nifty index, GoldM and SilverM through the Fyers broker; it runs "the same old Live logic" that the final ten found wiped in every window; no work has been done there yet.
- **Not known (phase 1 must find out):** which branches trade real money; which version of the logic it runs (§2.1, §2.16); whether it buys options, sells them, or both; how it picks strike and expiry; what a "pair" is in its state machine (one CE and one PE together, or one per direction); which prices its votes read (the index, a future, or the premium); its bar timeframes; its loop cadence (a polling interval like the MT5 bot's about 1 s, or event-driven on websocket ticks); one unit in lots; its rupee target; whether it has any stop; intraday square-off or carry; what it does at expiry; how it logs in to Fyers and keeps its token; whether a credentials or token file is tracked in git; the capital and risk limits.

### 6.1 What transfers, as hypotheses to test

| Measured in Alcadeias | Hypothesis for Ballom | First test |
|---|---|---|
| A capped win (+$1 × unit), an uncapped loss, a ladder that fires as one block, no stop: wiped in every window of a year or longer (§2) | If Ballom keeps a fixed rupee target, the ladder and no stop, the same arithmetic applies. **Selling** CE/PE pairs collects a capped premium against an open-ended loss (gamma), so a short pair with a ladder and no stop could fail faster than the CFD bot, by the tail. **Buying** pairs caps the loss per lot at the premium paid but pays time decay every hour, so the likely failure is the bleed | phase 4: measure the old logic on Ballom's own instruments, in money terms |
| The votes fade the last extreme and do not predict direction (50.8% against 50.8%, §2.3); 20 classic entry signals had no edge (§4.4) | The same votes on Nifty, GoldM or SilverM will not predict direction either | the edge screen of `backtesting/research/edge_screen.py` on the underlying's closed bars, before any option layer |
| Forming-bar votes decided the gold result ($11,957 against $2,300, §3.2) | Whatever bar Ballom reads must be replicated exactly; if it reads indicators on the **premium**, they also move with implied volatility and time decay, not only with direction | phase 3 parity |
| Structure turned losses into small profits: the H1 trend gate, a stop and a target in volatility units fixed at the open, no ladder, a long pause after a loss, force-close off (§4.2, §4.10 conclusion 3) | These levers may help on the underlying signal; whether they survive the option layer is open | phase 5, first on the underlying (fast), then with option P/L |
| The H1 trend gate was the largest single lever on gold (−$423 → +$6 a quarter, §4.3) | The cheapest first lever to test on Nifty / MCX futures | phase 5, pre-registered |
| Recovery mechanisms and averaging down never raised the expectancy (§4.4) | Averaging down on options will not either; adding to a short option as its premium rises compounds the gamma risk | skip ladders unless a test says otherwise |
| Costs decided short-term strategies: the spread took 39% of the winners' gross on gold (§2.13) | The option bid-ask plus Indian charges per round trip may be a large share of a small rupee target | phase 2: cost per round trip per lot against the bot's target |
| A fixed $1 target was a different bet in each year (§2.13 item 7) | A fixed rupee target per lot behaves differently across instruments, premium levels and volatility regimes | phase 4, per year and per instrument |
| Loop timing alone moved a quarter from −$2,000 to +$58 (§3.3) | If Ballom polls on a fixed interval as the MT5 bot does (its cadence is unknown, §6.0), it is just as path-dependent; if it is event-driven on websocket ticks, the order and timing of the ticks play that role. The Fyers API's latency and rate limits add to either | timing ensembles in phase 3 and 4 |
| Trend following (the Turtle) was the only rule that made real money on BTC (§4.5) | Trend following on the underlying may work, but long options pay time decay over Turtle-length holds (median about 10 days, §3.3) | phase 5, with the option layer, or via futures if the owner allows |
| The London breakout was profitable on New York + 7 h and lost on UTC (§4.5) | Session clocks matter: Indian sessions run on IST (to confirm the exchange clocks and the broker's timestamps) | phase 2 calendar and tests |
| The 5-minute opening-range breakout was left out because an independent CFD replication found its edge goes to zero after retail spreads (§4.5) | A Nifty opening-range breakout must be tested with realistic option spreads and charges, not on the index alone | phase 5 |
| Fresh quarterly accounts hid the risk of ruin that one continuous account showed (§4.2, round 3) | The same will hold for any ladder or short-premium design | always test both |
| Parity proved the decision code; the defects sat in the plumbing (§5.9) | Each generic form of §5.9 has a Fyers counterpart (§6.6) | phases 3 and 6 |

**The method transfers as it is, not as a hypothesis:** parity against the bot's own code, timing ensembles, pre-registration pushed before each hold-out, hold-outs run once, full warm-up, fresh and continuous accounts, every setting counted, independent reviews (§3).

### 6.2 What does not transfer, and why

- **Every number in §2 to §5.** They are for Exness CFDs, in USD, with spread-only costs, no swap, a $2,000 account and 0.01-lot steps.
- **The option payoff is not linear.** A CFD's P/L is linear in price ($1 per $1 move per 0.01 lot of gold). An option's premium moves with the underlying through **delta**, which itself changes with the price (**gamma**); it loses value with time (**theta**, faster near expiry); and it moves with implied volatility (**vega**, **IV**). A rule tuned on the underlying's moves does not map one-to-one to premium P/L: the same signal can win on the underlying and lose on the option. A long CE plus a long PE at the same strike has a delta of about 2N(d₁) − 1, which is close to zero only when the common strike is near the money; then the pair is mainly a bet on volatility and time, not on direction. An in-the-money or out-of-the-money same-strike pair has a directional delta. What Ballom's "pair" is (same strike, one per direction, …) is itself unknown (§6.0): a hypothesis to confirm in phase 1.
- **Expiry cycles** (to confirm every rule and its history). Options expire; a strategy must choose an expiry, exit or roll before it, and decide what to do on expiry day, when gamma near the money is largest. That spreads are also widest then is an untested assumption; measure it in phase 2. The weekly-expiry rules and the expiry weekday of index options were changed by SEBI and NSE more than once in recent years; a backtest must use the calendar in force on each date. For GoldM and SilverM options on MCX, confirm from MCX circulars: the underlying (the futures contract or the goods), the expiry schedule relative to the futures, what happens to an in-the-money option at expiry (devolvement into a futures or delivery position), and whether SilverM options are listed at all.
- **Exchange lot sizes instead of 0.01 lots.** Each contract has a lot size set by the exchange and changed from time to time (to confirm the history for each instrument). Positions come in whole lots, so the unit rule of §2.7 must be redefined in lots, and on a small account one lot may already be a large share of the capital (§4.10 conclusion 10).
- **Indian charges** (§6.4): brokerage, STT (CTT on MCX), exchange transaction charges, the SEBI fee, stamp duty and GST, several of them on premium turnover and some at different rates on exercise. The backtests here charged only the spread: commission is zero on Exness Standard, and swap was taken as zero and never read from a real account (§3.3), so "no swap" is an assumption.
- **Wide bid/ask far out of the money and near expiry.** Option spreads can be a large share of a cheap premium, especially far OTM, on thinner MCX options, and in the last minutes of expiry day (to measure in phase 2). Exness gold's median spread was 0.018% of the price in 2018 – 2020 [F10 §1.3].
- **NSE and MCX session hours, holidays and special sessions** (to confirm). NSE equity derivatives trade one day session on IST; MCX commodity derivatives trade from the morning into the late evening, with a closing time that has followed US daylight saving. Exchange holidays and special sessions must come from the exchanges' calendars. Alcadeias's windows (gold Mon 01:00 – Fri 22:00 UTC, BTC around the clock) do not apply.
- **The index has no bid/ask.** Nifty 50 spot is computed from stocks and is not traded; the tradables are futures and options with their own quotes. Historical option bars from most sources are last-traded-price OHLC with stale prints on illiquid strikes, not bid/ask (to confirm per source).
- **Margins and broker risk rules** (to confirm). Buying an option needs the premium; selling needs exchange margin, with benefits for hedged positions; brokers may square off positions at a cut-off time or on a margin shortfall. Alcadeias modelled only leverage and a stop-out.
- **The broker side** (to confirm from Fyers's documentation): REST and websocket APIs instead of a local MT5 terminal; an access token that has to be renewed (possibly daily); API rate limits; whether orders can carry a tag (the equivalent of MT5's magic number); which protective orders exist for options (exchanges may refuse stop-loss-market orders on options and accept only stop-limit, which can fail to fill in a fast move, so a broker-held backstop is weaker than on MT5).
- **Regulation of retail algorithmic trading** (to confirm): SEBI's rules for retail algorithmic trading through broker APIs may require registration, a static IP, order-rate limits or algo identifiers. Check with Fyers before any live order.
- **The forward-testing environment (to confirm).** The memory note assumes that Fyers has no MT5-style demo, so forward testing would mean paper trading against live quotes (§6.5 phase 6) [MEM ballom]. That note records a session's plan, not a checked fact: ask whether Fyers offers a sandbox, test or paper-trading environment for its API.
- **Currency and size:** INR, and the owner's capital per instrument is unknown (§6.7).

### 6.3 The data needed, and how to get it

| Data | Used for | Ways to get it | Caveats |
|---|---|---|---|
| **Underlying 1-minute history** (or finer): Nifty 50 spot, Nifty futures (continuous, with rolls), GoldM and SilverM futures | the signal layer: votes, trend, volatility unit; quick tests of the levers before any option layer | Fyers history API (depth, resolution and request limits to confirm); data vendors; exchange data products | spot has no bid/ask; futures need a roll rule; MCX contract months; one dated calendar |
| **Option premiums of expired contracts**, every strike and expiry the bot could pick, 1-minute or better, ideally with bid/ask | the option layer: P/L, fills, costs, expiry handling | (a) broker history: Fyers, if it serves expired contracts (to confirm; many brokers serve only live ones); (b) paid vendors of Indian historical option data (to research in phase 2); (c) exchange end-of-day files (NSE and MCX bhavcopies: daily OHLC, settlement price and open interest per contract), daily only; (d) **model** premiums from the underlying with Black-76 / Black-Scholes and an IV input: India VIX for Nifty (an implied-volatility index computed from Nifty options, to confirm its definition), historical or bhavcopy-implied volatility for GoldM and SilverM | modelled premiums miss the skew, intraday IV moves, the bid/ask and liquidity: use them for screening, never for final results, and check them against bhavcopy settlement prices |
| **Option bid/ask history** | the spread part of the cost model | vendors with quote data; recorded quotes from the Fyers websocket from now on (forward only); a spread model by moneyness and time to expiry fitted on recorded quotes | past quotes may not be available; start recording on day one of paper trading |
| **India VIX history** | IV input; a regime filter to test | NSE; vendors | to confirm availability |
| **The calendar**: trading days, holidays, special sessions, session hours, expiry dates and weekday changes, lot sizes, strike intervals, contract specifications | correct windows, expiries and sizes | exchange circulars; Fyers's symbol master files (to confirm); bhavcopies | keep one dated table, with the source of every row |
| **The charges history** | the cost model | exchange circulars, SEBI, the tax rules, Fyers's charge pages | one dated table per charge |
| **Ballom's own order and trade history**, if it has traded live | calibrate the replay and the fill model; compare with the backtest of the same weeks | Fyers order and trade books | never print client IDs or account numbers |

**Suggested order:** the underlying first (it lets the Alcadeias levers be tested on the signal within days), then the cheapest honest option source, then recorded quotes.

### 6.4 The cost model checklist (phase 2)

Every rate and base must be confirmed from the official source and kept as a dated history, because several were revised in recent years.

| Charge | Applies to | Base | Notes |
|---|---|---|---|
| Brokerage | every executed order | Fyers's schedule (per order or per turnover) | confirm for options on NSE and MCX |
| STT (Securities Transaction Tax) | NSE options and futures | for options, the sell-side premium; on exercise, the intrinsic value | the exercise case can cost far more than the trade itself; confirm |
| CTT (Commodity Transaction Tax) | MCX non-agricultural commodities, instead of STT | to confirm for options on futures | confirm |
| Exchange transaction charges | NSE, MCX | premium turnover for options | confirm per exchange and segment |
| SEBI turnover fee | all | turnover | confirm |
| Stamp duty | the buy side | turnover | confirm |
| GST | brokerage, exchange charges, SEBI fee | those charges | confirm |
| Clearing and other charges | as applicable | – | confirm |
| **Bid/ask** | every fill | from quotes or a fitted spread model | by moneyness, time to expiry, time of day, instrument |
| **Slippage and latency** | every fill | from paper trading | a pessimistic default until measured |

Then compute **the round-trip cost per lot** at typical premiums and compare it with the bot's target per lot (§2.16 question 3).

### 6.5 The phased plan

**Phase 0. Hand-off.** This file and `docs/handoff/` (16 Nov 2026).

**Phase 1. Map Ballom read-only, including which branches are live.**
- List every branch with its last commit, and ask the owner which trade real money (§6.7). Until the owner answers, treat every deployment-like branch as live: no checkout, no commit, no push; read with `git show <branch>:<path>`.
- Map the live loop as `docs/handoff/live_loop_map.md` does for MT5: start-up and login, one poll, every API call, the bars and prices read, the votes and scores, entries, exits, the ladder, sizing in lots, strike and expiry choice, the CE/PE pair logic, order types, state kept between polls, restarts, logging, every constant and who reads it.
- Answer the eleven questions of §2.16 and check each defect of §2.9.
- Note credentials handling **by file name only**; never open or print a credentials or token file.
- Write the map into a file on a safe branch the owner names; commit only when asked.

**Phase 2. Data and costs.**
- Build the underlying store (Alcadeias's `data/store.py` layout is a template: raw downloads kept, one folder per instrument and month, compressed arrays, conservative cleaning with counts).
- Choose the option-premium source (§6.3) with the owner; build it; run a quality report (coverage, silences by kind: session close, holiday, halt, hole; spreads by hour, moneyness and expiry; large moves checked against real events).
- Build the calendar and the dated cost model (§6.4).
- **Do not read any result yet.** Fix the DEV, CONFIRM and FINAL windows first and write them into `LOGIC_CHANGELOG.md`-style notes (§3.4).

**Phase 3. The backtester, with a parity harness against a simulated Fyers API.**
1. A fast engine of Ballom's loop on the **underlying** first (the signal), which also lets the Alcadeias levers be tested directly.
2. The **option layer**: map each signal to the contract the bot would pick, price it from the premium series, apply lot sizes, costs and expiry rules.
3. A **reference replay**: Ballom's own unmodified code against a simulated Fyers API, as `backtesting/engine/reference.py` does for MT5 [MP]: replace the broker module, patch every clock in every module, serve quotes, bars, orders, positions, funds and the order book, apply the broker's refusals, record one trace row per poll, and count every swallowed exception as a failure.
4. **Parity windows** that include a session break, a refusal, an expiry day and a crash; record them and keep the recordings somewhere durable.
5. The tests of §3.10: characterisation, invariants, no-look-ahead (also inside the decision minute), mutation, time-zone, holiday and expiry-day tests, fault injection (failed reads, rejected orders, restarts, reconnects, an expired token).

**Phase 4. Measure the current Live logic on options.** Fresh accounts per quarter **and** continuous accounts, timing ensembles, results per year and per instrument, cost sensitivity, how the accounts die (§2.12). This shows the owner how dangerous it is in money terms.

**Phase 5. Improve, under the same pre-registration and hold-out discipline.**
- **Pre-register** each round: the candidates, the selection rule, the windows and the account, frozen in a commit pushed before the hold-out is read; run each hold-out once; report whatever it shows (§3.4).
- **Candidates:**
  - the Alcadeias levers (trend gate, volatility stop and target fixed at the open, no ladder, loss pause, force-close off), on the underlying signal and then with option P/L;
  - option-specific choices: strike (ATM, ITM or OTM, by delta); expiry (weekly or monthly, a minimum number of days to expiry); stops on the premium or on the underlying; time exits before decay accelerates; IV filters (India VIX level or percentile); whether to avoid or target expiry day;
  - known Indian-market strategies: opening-range breakouts on Nifty, expiry-day behaviour, **hedged** premium selling (defined-risk spreads rather than naked short pairs).
- **Tools:** `lcb`, the haircut, the probability of overfitting, walk-forward, neighbours, families of results (Alcadeias's `backtesting/optimise.py` and `OPTIMISER.md` are templates); full warm-up; fresh and continuous accounts; equal sizing for comparisons.

**Phase 6. Paper trading.**
- A paper broker fed with live Fyers quotes (the simulated Fyers API of phase 3 can serve, filling at the live bid/ask, with the cost model), or a Fyers sandbox if one exists (to confirm, §6.2).
- The same isolation, logging and dashboard ideas as the demo branches: an order tag per bot, its own ledger, its own state file and output folder, the checklist of §5.9 and §6.6.
- Record every quote the bot sees: it builds the bid/ask history the backtest lacks.
- Compare the paper deals with the backtest of the same weeks; one to three months before any real money, as FINAL10 advised for Alcadeias [F10 §10].

### 6.6 The engineering checklist, translated for a Fyers API bot (suggestions)

| Alcadeias lesson (§5.9) | Fyers counterpart to check |
|---|---|
| Trade on the intended account only | verify the logged-in client and the environment (paper or live) before every order; make "live" impossible on a test branch |
| Never change a shared session's global state | one session or token per bot; never log another process out |
| Validate the context after the read, in the same critical section | re-check the session after reading positions and before acting |
| Magic isolation | an order tag per bot (if the API supports one), and filtering of positions and orders by it; never square off "all positions" |
| Virtual balance | size each strategy from its own ledger when an account is shared |
| Persisted state, rebuilt without it | persist every variable the strategy carries; rebuild from the order book and trade book |
| A fill not yet listed | "order placed, position not yet visible" as an explicit state with a timeout |
| A broker-side backstop | which protective orders exist for options, and what happens when a stop-limit does not fill |
| Reconnect | websocket reconnects, token renewal, back-off; decide nothing while unhealthy |
| A failed read is not an empty answer | an API error must never look like "no positions" |
| Missing inputs fail closed for entries | a missing quote or bar blocks entries and never blocks exits |
| Minimum history | measure each indicator's minimum history |
| Partial closes | reconcile legs every poll, also legs closed by the broker or by hand |
| Log flooding | rate-limit by (event, reason) |
| Refuse an impossible design at start | validate the whole configuration before the first order |
| Clock domains | exchange time (IST, to confirm) against machine time against the API's timestamps |

### 6.7 Questions to ask the owner first

1. **Which Ballom branches trade real money?** They will be treated like the `hedging_*` branches here: never pushed to.
2. **Does the bot buy options, sell them, or both?** How does it pick the strike and the expiry today? What is a "pair"?
3. **Data:** does the Fyers API access include historical data, and for expired option contracts? Is there another data source already?
4. **Capital and risk limits per instrument** (Nifty, GoldM, SilverM): capital, the most lots, the most loss per day.
5. **Is Ballom trading now,** on which accounts and since when? Is there a trade history to compare the replay with?
6. **Intraday only, or carried overnight and into expiry?**
7. **Where does it run** (machine, operating system), how is it started and restarted, and how does it log in? (Without sharing any secret.)
8. **Which branch may the work go on,** and should results be committed there?

### 6.8 The first prompts to use in the Ballom session

First, in the Ballom session: `/add-dir /Users/sidharthsingh/Desktop/Alcadeias/Alcadeias`.

1. **Phase 1:**
   > Read the research brief in the Alcadeias repo (`/Users/sidharthsingh/Desktop/Alcadeias/Alcadeias/HANDOFF.md`), then map Ballom read-only (phase 1). List every branch with its last commit and ask me which ones trade real money before anything else. Do not check out, commit or push anything, and never open or print a credentials or token file. Map the live loop the way `docs/handoff/live_loop_map.md` maps the MT5 bot, answer the questions of HANDOFF.md §2.16, and check every defect of §2.9.
2. **Phase 2:**
   > Using the Ballom map and HANDOFF.md §6.3 – §6.4, propose the data sources for the underlying and for option premiums with their coverage and cost, the calendar and the cost model. Then build the underlying store and its quality report. Fix the DEV, CONFIRM and FINAL windows in writing before reading any result.
3. **Phase 3:**
   > Build the backtester for Ballom's loop: the signal on the underlying first, then the option layer, then a reference replay of Ballom's own code against a simulated Fyers API with a poll-by-poll parity check, as HANDOFF.md §3.2 and `docs/handoff/parity_map.md` describe. Work through the trust checklist of §3.10.
4. **Phase 4:**
   > Measure the current Live logic on Nifty, GoldM and SilverM: fresh accounts per quarter and continuous accounts, timing ensembles, per-year results, cost sensitivity, and how the accounts die, as HANDOFF.md §2.12 does for MT5.
5. **Phase 5:**
   > Write a pre-registration for round 1 (candidates, selection rule, windows, account), commit it, and only then run it. Candidates: the Alcadeias levers of HANDOFF.md §5.3 – §5.4 and the option-specific choices of §6.5.
6. **Phase 6:**
   > Build paper trading for the chosen design: a paper broker on live Fyers quotes, with the isolation, state, logging and checklist of HANDOFF.md §5.9 and §6.6, recording every quote it sees.

---

## 7. Where everything is

### 7.1 Files in this repo (branch `backtest_hedging`)

| What | Where |
|---|---|
| This hand-off and its maps | `HANDOFF.md`; `docs/handoff/live_loop_map.md`, `levers_map.md`, `turtle_map.md`, `parity_map.md` |
| Every logic change and result, newest first | `LOGIC_CHANGELOG.md` |
| Rounds 1 and 2 | `IMPROVEMENT.md` |
| The live hedging baseline, the live-code findings, the recommendations | `BACKTEST.md` (generated by `python -m backtesting docs`); `backtest_results/index.html`, `findings.json`, `recommendations.md` |
| The backtester's manual; the optimiser's manual | `backtesting/README.md`; `backtesting/OPTIMISER.md` |
| The final ten | `backtest_results/final10/`: `FINAL10.md` (generated from `FINAL10.template.md`), `results.csv`, `selection.json`, `selection_warm.json`, `evidence.csv`, `evidence_warm.csv`, `runs_*`, `years_*`, `equity_*`, `trades_*`, `timings_1y_*`, `regression_check.csv`, `identity_check.csv`, `signal_sizes.csv` |
| The Balke study | `backtest_results/balke/`: `BALKE.md`, `results.csv`, `years_<symbol>.csv` |
| The research rounds | `backtest_results/improve/`: `external_strategies.md` and CSVs, `recovery_mechanisms.md`, `sr_study.md`, `sr_trades.md`, `edge_screen_*.txt`, `round2/`, `round3/`, `round4/` (`top3_v4_*_designs.json`, `top3_v4_holdout_*.csv`, `top3_v4_dev_*.csv`, `equity_top3.csv`, `top3_v4.py`) |
| The optimiser's reports | `backtest_results/optimise/v3_XAUUSDm/`, `v4_XAUUSDm/`, `v4_BTCUSDm/` (`report.md`) |
| The parity reports | `backtest_results/parity/*.json` (7 hedging windows) |
| The demo-parity write-up | `backtest_results/demo_parity/DEMO_PARITY.md` (untracked, partly stale, §0.5) |
| Configuration and engines | `backtesting/config.py`; `backtesting/engine/kernels.py`, `fast.py`, `reference.py`, `parity.py`, `demo_parity.py` |
| Data | `backtesting/data/exness.py` (downloader), `store.py` (the store), `quality.py` (the quality report) |
| Analysis | `backtesting/analysis/metrics.py`, `robustness.py` (timing ensembles, cost, latency, start date, bootstrap), `signal.py` (the votes on closed bars), `holdout.py`, `sweep.py`, `diagnostics.py` |
| Research code | `backtesting/research/external.py` (M1-bar simulator, published strategies, the Turtle), `final10.py`, `balke.py`, `recovery.py`, `sr.py`, `sr_trades.py`, `edge_screen.py`, `improve.py` |
| Search with overfitting controls | `backtesting/optimise.py` |
| Fingerprints and stale outputs | `backtesting/experiments.py` (`stale_outputs`, `parity_fingerprint`, `live_fingerprint`) |
| Charts, reports, the tick-by-tick studio | `backtesting/viz/` |
| Tests | `tests/`: `test_parity.py`, `test_live_strategy_characterization.py`, `test_live_fault_injection.py`, `test_lever_rules.py` (e.g. L1422 trend, L1473 loss pause, L1540 MACD-turn add, L1615 volatility units), `test_external.py`, `test_demo_parity.py`, `test_regime_filter.py`, `test_data_holes.py`, `test_account_and_broker_rules.py`, `test_engine_invariants.py` and others; real-tick fixtures in `tests/fixtures/store` |
| The live code (identical to `origin/hedging_xauusd6`) | `app.py`, `strategy.py`, `indicator.py`, `mt5_helper.py`, `constants.py`, `symbols.json`, `dashboard.py`, `CHANGELOG.md`, `docs/weighted-regime-redesign.md`, `docs/h4h1m15-decision-table.md` |

**On other branches** (read with `git show <branch>:<path>`):
- `backtest_netting:BACKTEST.md`: the netting baseline.
- Each `demo_hedging_*` branch: `README.md`, `CHANGELOG.md` (on origin: v3.9.2-demo.1 and demo.3 on all six, demo.2 only on BTC 6 and 7), the design block at the end of `constants.py`, `tests_demo/` (with `fake_mt5.py`), and `turtle.py` on BTC 6 and 7.
- The live branches: the same live files as above, plus `mt5_credentials.json`, which must never be opened.

### 7.2 Commands

The full table with costs is §3.8. The ones a Ballom session is most likely to read or copy:
- Data and quality: `python -m backtesting data ...`, `python -m backtesting quality --symbol S`.
- One run: `python -m backtesting run --symbol S --start ... --end ... [--mode ticks] [--set k=v] [--live-root DIR]`.
- Parity: `python -m backtesting parity --symbol S --start ... --end ... [--live-root DIR] --out f.json`; `python -m backtesting.engine.demo_parity <branch dir> <SYMBOL> "<design>" "<start>" "<end>"`.
- Robustness and search: `python -m backtesting robust ...`, `python -m backtesting optimise --space S --symbol X ...`.
- The final ten: `python -m backtesting.research.final10 select | run | supplement | warm | checks | report`.
- Tests: `python -m pytest tests -q -p no:cacheprovider` with `PYTHONDONTWRITEBYTECODE=1` and `NUMBA_CACHE_DIR` outside the repo.
- Export a branch's code without credentials: `git archive <branch> app.py strategy.py indicator.py mt5_helper.py constants.py symbols.json | tar -x -C <dir>`. On `demo_hedging_btcusd6` and `btcusd7` add `turtle.py` (their `app.py` loads it at import), and `tests_demo/` to run the branch's tests (§0.2).

### 7.3 Outside the repo

| What | Where | Note |
|---|---|---|
| Ballom_Fyers | `/Users/sidharthsingh/Desktop/Ballom` | from the owner's note; not opened for this file |
| The review journals | `~/.claude/projects/-Users-sidharthsingh-Desktop-Alcadeias-Alcadeias/210c2577-eab3-4001-bc50-2408e8c4d100/subagents/workflows/<id>/journal.jsonl` (`wf_285378d0-a0a`, `wf_c9b9a4c0-2f4`, `wf_3ebd063f-c01`, `wf_c0f3ff36-384`, `wf_ea170a6c-975`) | the full record of each review; their findings are in §3.7 and §5.9 |
| The owner's memory notes for Alcadeias | `~/.claude/projects/-Users-sidharthsingh-Desktop-Alcadeias-Alcadeias/memory/` | not visible to a Ballom session; their content is in §1 and §6 |
| The parity recordings, re-check script and probe scripts | `data/archive/session_2026-11-16/` in this repo (git-ignored, this machine only; `parity_final/*.ref.pkl`, 14 files, 109 MB; `parity_final.py`; `README.md`) | copied from the session's temporary scratch folder on 16 Nov 2026; see §0.6 |
| The tick store | `data/raw/` and `data/store/` in this repo (git-ignored; 11 GB and 22 GB on 16 Nov 2026) | rebuild with `python -m backtesting data` |
