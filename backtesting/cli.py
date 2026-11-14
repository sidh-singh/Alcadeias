"""
Command line for the backtesting suite.

    python -m backtesting data    --from 2025-07 --to 2026-11          # download + build the tick store
    python -m backtesting quality --symbol XAUUSDm                     # data-quality report
    python -m backtesting run     --symbol XAUUSDm                     # live config, last 3 months, HTML report
    python -m backtesting run     --symbol BTCUSDm --set entry_s=4 --set 'open_weights={"H4":1,"M15":1}'
    python -m backtesting parity  --symbol BTCUSDm --start "2026-11-05 00:00" --end "2026-11-05 02:00"
    python -m backtesting sweep   --symbol XAUUSDm --kind timeframes   # which timeframes for OPEN / FC / BOOK
    python -m backtesting robust  --symbol XAUUSDm                     # timing, costs, start date, bootstrap
    python -m backtesting reproduce                                    # the whole pipeline behind backtest_results/
    python -m backtesting docs                                         # index.html + PNG snapshots + BACKTEST.md
    python -m backtesting studio                                       # interactive replay in the browser

The commands do not all take the same options (``python -m backtesting <command> --help``
lists them in full):

    data                          --symbols, --from / --to (months), --raw-dir, --store-dir, --force,
                                  --build-only, --no-ticks
    quality                       --symbol, --start / --end (UTC), --out
    run, parity, sweep, robust    --symbol, --start / --end (UTC), --balance, --leverage,
                                  --set KEY=VALUE (any ``BacktestConfig`` field; the value is parsed
                                  as JSON when possible), --live-root DIR (the checkout whose
                                  constants.py, symbols.json and live code are used; default: this
                                  one), and each command's own switches
    reproduce                     --symbols, --only, --out, --live-root DIR, --jobs, --force, --no-index
    docs                          --symbols, --out, --live-root DIR, --md, --no-images
    studio                        --host, --port, --debug; always reads this checkout's settings

reproduce and docs work on the pipeline's fixed windows and balances, so they take no
--start / --end, --balance, --leverage or --set.

``run --mode sec`` (the default) replays the per-second series with one poll on every whole
second; ``run --mode ticks`` replays every tick and adds the 0.1 s the live buy() / sell() sleep
after an order (open_order_delay_ms=100, unless given with --set).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .config import BacktestConfig, REPO_ROOT, SYMBOLS

RESULTS_DIR = REPO_ROOT / "backtest_results"
DEFAULT_START = "2026-08-13"
DEFAULT_END = "2026-11-13"
UNIVERSE = ["M1", "M5", "M15", "M30", "H1", "H4"]
# The live buy() / sell() sleep 0.1 s after sending an order. Only a raw-tick replay can follow
# it: the per-second series holds one quote per second, so its polls have to stay on whole seconds.
LIVE_OPEN_ORDER_DELAY_MS = 100


def _parse_sets(pairs: Optional[List[str]]) -> dict:
    out = {}
    for item in pairs or []:
        if "=" not in item:
            raise SystemExit(f"--set expects key=value, got {item!r}")
        k, v = item.split("=", 1)
        try:
            out[k.strip()] = json.loads(v)
        except ValueError:
            low = v.strip().lower()
            out[k.strip()] = None if low in ("none", "null") else True if low == "true" else False if low == "false" else v
    return out


def _live_root(args) -> Path:
    """The checkout whose constants.py, symbols.json and live code a command uses (--live-root)."""
    given = getattr(args, "live_root", None)
    if not given:
        return REPO_ROOT
    root = Path(given).expanduser().resolve()
    if not (root / "constants.py").is_file():
        raise SystemExit(f"--live-root {given}: no constants.py in {root}")
    return root


def _config(args) -> BacktestConfig:
    kw = dict(start=args.start, end=args.end)
    if getattr(args, "balance", None) is not None:
        kw["initial_balance"] = args.balance
    if getattr(args, "leverage", None) is not None:
        kw["leverage"] = args.leverage
    kw.update(_parse_sets(getattr(args, "set", None)))
    return BacktestConfig.live(args.symbol, repo_root=_live_root(args), **kw)


def _write_json(path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def _ym(s: str) -> date:
    y, m = s.split("-")[:2]
    return date(int(y), int(m), 1)


# ───────────────────────────── commands ─────────────────────────────

def cmd_data(args) -> int:
    from .data import exness, store
    raw, st = Path(args.raw_dir), Path(args.store_dir)
    a, z = _ym(args.from_), _ym(args.to)
    if not args.build_only:
        exness.download_range(args.symbols, a, z, raw, force=args.force)
    store.build_range(args.symbols, a, z, raw, st, force=args.force, keep_ticks=not args.no_ticks)
    for sym in args.symbols:
        span = store.data_span(sym, st)
        if span:
            print(f"{sym}: {span[0]} .. {span[1]}")
    return 0


def cmd_quality(args) -> int:
    from .data import quality
    q = quality.quality_report(args.symbol, args.start, args.end)
    print(quality.format_quality(q))
    if args.out:
        _write_json(args.out, q)
        print(f"wrote {args.out}")
    return 0


def cmd_run(args) -> int:
    from .engine.fast import run
    cfg = _config(args)
    if args.mode == "ticks" and "open_order_delay_ms" not in _parse_sets(args.set):
        cfg = cfg.replace(open_order_delay_ms=LIVE_OPEN_ORDER_DELAY_MS)
    t0 = time.time()
    res = run(cfg, mode=args.mode)
    s = res.summary()
    print(f"{cfg.symbol} {cfg.variant}  {cfg.start} -> {cfg.end}  [{cfg.describe_scores()}]  "
          f"({res.mode} mode, {time.time() - t0:.1f}s)")
    for k in ("net_profit", "return_pct", "max_drawdown_usd", "max_drawdown_pct", "baskets", "win_rate_pct",
              "profit_factor", "avg_win", "avg_loss", "largest_loss", "ladder_adds", "max_lots", "stopped_out"):
        print(f"  {k:22s} {s.get(k)}")
    if not args.no_report:
        from .viz.report import build_report, ensure_plotly_js
        out = Path(args.out) if args.out else RESULTS_DIR / f"{cfg.variant}_{cfg.symbol}_{cfg.key()}"
        ensure_plotly_js(out.parent / "assets")
        path = build_report(res, out, closeups=not args.no_closeups)
        print(f"report: {path}")
    return 0


def cmd_parity(args) -> int:
    from .engine.parity import check_parity
    cfg = _config(args)
    t0 = time.time()
    rep = check_parity(cfg, live_root=_live_root(args), mode=args.mode,
                       progress=lambda n, t: print(f"  live loop: {n:,} iterations ({time.time() - t0:.0f}s)", flush=True))
    print(rep)
    if args.out:
        import dataclasses
        from . import experiments
        # everything the results page needs to list the window, and what the report vouches for
        _write_json(args.out, {**dataclasses.asdict(rep), "name": Path(args.out).stem, "variant": cfg.variant,
                               "symbol": cfg.symbol, "start": cfg.start, "end": cfg.end,
                               "scores": cfg.describe_scores(), "elapsed_s": round(time.time() - t0, 1),
                               "stamp": {"engine": experiments.parity_fingerprint(),
                                         "live": experiments.live_fingerprint(_live_root(args))}})
    return 0 if rep.ok else 1


def cmd_sweep(args) -> int:
    from .analysis import sweep
    cfg = _config(args)
    universe = args.universe or UNIVERSE
    if args.kind == "timeframes":
        grid, labels = sweep.grid_joint_timeframes(universe, cfg.variant)
    elif args.kind == "split-open":
        grid, labels = sweep.grid_split_indicator(universe, cfg.variant,
                                                  fc_tfs=list(cfg.fc_weights) if args.fix_exits else None,
                                                  book_tfs=list(cfg.book_weights) if args.fix_exits else None)
    elif args.kind == "split-fc":
        grid, labels = sweep.grid_split_exit(universe, cfg.variant, "fc")
    elif args.kind == "split-book":
        grid, labels = sweep.grid_split_exit(universe, cfg.variant, "book")
    else:
        raise SystemExit(f"unknown sweep kind {args.kind}")
    print(f"{args.kind}: {len(grid)} configurations on {cfg.symbol} {cfg.start} -> {cfg.end}")
    t0 = time.time()
    df = sweep.run_grid(cfg, grid, n_jobs=args.jobs, labels=labels,
                        progress=lambda a, b, t: print(f"  {a}/{b} ({t:.0f}s)", flush=True))
    out = Path(args.out) if args.out else RESULTS_DIR / "sweeps" / f"{cfg.variant}_{cfg.symbol}_{args.kind}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"done in {time.time() - t0:.0f}s -> {out}")
    with pd.option_context("display.width", 220, "display.max_columns", 30):
        print(df.sort_values("net_profit", ascending=False).head(args.top).to_string(index=False))
    return 0


def cmd_robust(args) -> int:
    from .analysis import robustness
    from .engine.fast import run
    cfg = _config(args)
    out = Path(args.out) if args.out else RESULTS_DIR / "robustness" / f"{cfg.variant}_{cfg.symbol}"
    out.mkdir(parents=True, exist_ok=True)
    show = lambda title, df: print(f"\n== {title}\n{df.to_string(index=False)}")
    tick_jobs = max(1, min(args.jobs or 2, 3))      # every raw-tick worker holds the whole window of ticks in memory
    with pd.option_context("display.width", 220, "display.max_columns", 30):
        df = robustness.cost_grid(cfg, n_jobs=tick_jobs)
        df.to_csv(out / "costs.csv", index=False)
        show("costs (raw ticks)", df)
        df = robustness.start_shift(cfg, n_jobs=tick_jobs)
        df.to_csv(out / "start_shift.csv", index=False)
        show("start shift (raw ticks)", df)
        df = robustness.segments(cfg, n_jobs=args.jobs)
        df.to_csv(out / "segments.csv", index=False)
        show("segments", df)
        if not args.no_ticks:
            df = robustness.timing_grid(cfg, n_jobs=tick_jobs)
            df.to_csv(out / "timing.csv", index=False)
            show("timing (raw ticks)", df)
    # the baskets of one run of the window: raw ticks at the live cadence as in the pipeline, unless --no-ticks
    if args.no_ticks:
        res, source = run(cfg, light=True), "per-second replay"
    else:
        res, source = run(cfg.replace(open_order_delay_ms=100), mode="ticks", light=True), "raw ticks, live cadence"
    bs = {"source": source, "baskets": int(len(res.baskets)),
          "live_units": robustness.bootstrap(res.baskets, cfg.initial_balance, cfg.step_up_balance, cfg.unit_max_limit),
          "fixed_unit_1": robustness.bootstrap(res.baskets, cfg.initial_balance, 0.0, 1)}
    _write_json(out / "bootstrap.json", bs)
    print("\n== whole days drawn with replacement; live_units = baskets re-sized by the bot's unit rule, "
          "fixed_unit_1 = one unit throughout\n" + json.dumps(bs, indent=2))
    return 0


def cmd_reproduce(args) -> int:
    from . import experiments
    out = Path(args.out) if args.out else RESULTS_DIR
    live_root = _live_root(args)
    experiments.reproduce(out, symbols=args.symbols, live_root=live_root, only=args.only,
                          force=args.force, n_jobs=args.jobs)
    if not args.no_index:
        from .viz.index import build_index
        print(f"index: {build_index(out, live_root=live_root)}")
    return 0


def cmd_docs(args) -> int:
    """Rebuild the landing page, the PNG snapshots and BACKTEST.md from the result files."""
    out = Path(args.out) if args.out else RESULTS_DIR
    live_root = _live_root(args)
    from .viz.index import build_index
    from .viz.markdown import build_backtest_md
    from .viz.report import ensure_plotly_js
    ensure_plotly_js(out / "assets")
    if not args.no_images:
        from .viz.snapshot import build_gallery
        build_gallery(out, symbols=args.symbols, live_root=live_root)
    print(f"index:       {build_index(out, symbols=args.symbols, live_root=live_root)}")
    target = Path(args.md) if args.md else None
    print(f"BACKTEST.md: {build_backtest_md(out, symbols=args.symbols, live_root=live_root, target=target)}")
    return 0


def cmd_studio(args) -> int:
    from .viz.studio import serve
    serve(host=args.host, port=args.port, debug=args.debug)
    return 0


# ───────────────────────────── parser ─────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m backtesting", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    live_root_help = ("checkout whose constants.py, symbols.json and live code are used, for example a "
                      "worktree of another deployment branch (default: this checkout)")

    def window(sp):
        """Symbol and period: every command that reads one symbol's ticks."""
        sp.add_argument("--symbol", default="XAUUSDm", choices=list(SYMBOLS))
        sp.add_argument("--start", default=DEFAULT_START, help="inclusive, UTC (default %(default)s)")
        sp.add_argument("--end", default=DEFAULT_END, help="exclusive, UTC (default %(default)s)")

    def account(sp):
        """What makes up a BacktestConfig: only for the commands that run the strategy."""
        sp.add_argument("--balance", type=float, default=None, help="starting balance in USD (default 2000)")
        sp.add_argument("--leverage", type=float, default=None,
                        help="account leverage (default 2000; an instrument's own cap still applies)")
        sp.add_argument("--set", action="append", metavar="KEY=VALUE",
                        help="override any BacktestConfig field; the value is parsed as JSON when possible (repeatable)")
        sp.add_argument("--live-root", default=None, metavar="DIR", help=live_root_help)

    sp = sub.add_parser("data", help="download Exness tick history and build the local store")
    sp.add_argument("--symbols", nargs="+", default=list(SYMBOLS))
    sp.add_argument("--from", dest="from_", default="2025-07", help="first month, YYYY-MM (the pipeline needs 2025-07 onwards)")
    sp.add_argument("--to", default="2026-11", help="last month, YYYY-MM")
    sp.add_argument("--raw-dir", default=str(REPO_ROOT / "data" / "raw" / "exness"))
    sp.add_argument("--store-dir", default=str(REPO_ROOT / "data" / "store"))
    sp.add_argument("--force", action="store_true", help="re-download / rebuild even if up to date")
    sp.add_argument("--build-only", action="store_true", help="skip the download, just (re)build the store")
    sp.add_argument("--no-ticks", action="store_true", help="keep only the per-second and M1 stores (saves disk)")
    sp.set_defaults(fn=cmd_data)

    sp = sub.add_parser("quality", help="data-quality report for the stored ticks")
    window(sp)
    sp.add_argument("--out", default=None, help="also write the report as JSON to this file")
    sp.set_defaults(fn=cmd_quality)

    sp = sub.add_parser("run", help="run one backtest and write an HTML report")
    window(sp)
    account(sp)
    sp.add_argument("--mode", choices=["sec", "ticks"], default="sec",
                    help="sec (default) = the per-second series, one poll on every whole second; it cannot "
                         "represent the 0.1 s the live code sleeps after an order. ticks = every tick, with that "
                         "sleep (open_order_delay_ms=100 unless given with --set)")
    sp.add_argument("--out", default=None, help="report directory")
    sp.add_argument("--no-report", action="store_true")
    sp.add_argument("--no-closeups", action="store_true")
    sp.set_defaults(fn=cmd_run)

    sp = sub.add_parser("parity", help="replay a window through the real live code and compare the fast engine")
    window(sp)
    account(sp)
    sp.add_argument("--mode", choices=["sec", "ticks"], default="ticks")
    sp.add_argument("--out", default=None, help="also write the parity report as JSON to this file")
    sp.set_defaults(fn=cmd_parity, start="2026-11-05 00:00", end="2026-11-05 02:00")

    sp = sub.add_parser("sweep", help="timeframe sweeps")
    window(sp)
    account(sp)
    sp.add_argument("--kind", default="timeframes", choices=["timeframes", "split-open", "split-fc", "split-book"])
    sp.add_argument("--universe", nargs="+", default=None, help=f"timeframes to try (default {' '.join(UNIVERSE)})")
    sp.add_argument("--fix-exits", action="store_true", help="split-open: keep the live FC/BOOK timeframes")
    sp.add_argument("--jobs", type=int, default=None)
    sp.add_argument("--top", type=int, default=20)
    sp.add_argument("--out", default=None)
    sp.set_defaults(fn=cmd_sweep)

    sp = sub.add_parser("robust", help="timing / cost / start-date / bootstrap robustness tests")
    window(sp)
    account(sp)
    sp.add_argument("--jobs", type=int, default=None)
    sp.add_argument("--no-ticks", action="store_true",
                    help="skip the loop-timing grid (the cost and start-date tests still replay raw ticks)")
    sp.add_argument("--out", default=None)
    sp.set_defaults(fn=cmd_robust)

    sp = sub.add_parser("reproduce", help="re-run the whole experiment pipeline behind backtest_results/")
    sp.add_argument("--symbols", nargs="+", default=list(SYMBOLS))
    sp.add_argument("--only", nargs="+", default=None,
                    choices=["quality", "baseline", "long", "signal", "sweeps", "levers", "improve", "holdout", "candidates", "robust"])
    sp.add_argument("--out", default=None, help="results directory (default backtest_results/)")
    sp.add_argument("--live-root", default=None, metavar="DIR", help=live_root_help)
    sp.add_argument("--jobs", type=int, default=None)
    sp.add_argument("--force", action="store_true")
    sp.add_argument("--no-index", action="store_true")
    sp.set_defaults(fn=cmd_reproduce)

    sp = sub.add_parser("docs", help="rebuild index.html, the PNG snapshots and BACKTEST.md from the result files")
    sp.add_argument("--symbols", nargs="+", default=list(SYMBOLS))
    sp.add_argument("--out", default=None, help="results directory (default backtest_results/)")
    sp.add_argument("--live-root", default=None, metavar="DIR", help=live_root_help)
    sp.add_argument("--md", default=None, help="where to write the markdown (default <live root>/BACKTEST.md)")
    sp.add_argument("--no-images", action="store_true", help="skip the PNG snapshots (they need headless Chrome)")
    sp.set_defaults(fn=cmd_docs)

    sp = sub.add_parser("studio", help="interactive replay studio (Dash); reads this checkout's live settings")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8060)
    sp.add_argument("--debug", action="store_true")
    sp.set_defaults(fn=cmd_studio)
    return p


def _utf8_console() -> None:
    """
    Make stdout and stderr write UTF-8.

    The logs and tables contain characters such as "→", "–", "✕" and "·". A console or a
    redirected stream in a legacy code page (cp1252 on Windows) cannot encode them, and a
    print() would raise UnicodeEncodeError in the middle of a stage. errors="replace" keeps a
    stream that still refuses a character from raising.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def main(argv: Optional[List[str]] = None) -> int:
    _utf8_console()
    args = build_parser().parse_args(argv)
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
