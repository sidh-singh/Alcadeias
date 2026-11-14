"""
Shared visual language for every chart this suite draws.

The surfaces and the gold chrome accent come from the live dashboard (``dashboard.py``),
so a backtest report sits naturally next to it. Data colours are assigned by the job
they do and were checked with a colour-vision-deficiency validator against the card
surface below (OKLab delta-E, protan/deutan simulation, contrast >= 3:1):

* polarity  (long / short, profit / loss, up / down candle): UP vs DOWN -- CVD dE 9.8,
  and always backed by a second channel (marker shape, bar direction, a signed label);
* identity  (exit reason, which score): SERIES in a fixed order, never recycled;
* emphasis  (one line is the point): EMPHASIS on CONTEXT grey.

Text always wears the ink tokens, never a series colour.
"""

from __future__ import annotations

# ── surfaces & ink ──
PAGE = "#060b18"
SURFACE = "#0c1328"          # chart / card surface (colours are validated against this)
SURFACE_2 = "#111a35"
BORDER = "rgba(192,168,100,0.16)"
INK = "#f0ede4"
INK_2 = "#b8b0a0"
INK_MUTED = "#8a8fa3"
GRID = "#18213d"             # hairline, one step off the surface
AXIS = "#2a3557"
ACCENT = "#d4a843"           # brand gold: chrome only (headings, rules), never a data colour

# ── polarity ──
UP = "#2dab92"               # long / profit / up candle
DOWN = "#d94a4a"             # short / loss / down candle
NEUTRAL = "#5d6785"

# ── categorical (fixed order) ──
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
EMPHASIS = SERIES[0]
CONTEXT = "#6b7594"

# entity -> colour: an entity keeps its colour in every chart, whatever else is shown
REASON_COLOR = {
    "target": SERIES[0],
    "force_close": SERIES[1],
    "book": SERIES[2],
    "stop_loss": SERIES[3],
    "stop_out": SERIES[4],
    "time_stop": SERIES[6],
    "data_hole": CONTEXT,
    "": CONTEXT,
}
REASON_LABEL = {
    "target": "Target (+$ per unit)",
    "force_close": "Force-close (slope reversal)",
    "book": "Profit-book (slope reversal in profit)",
    "stop_loss": "Stop-loss",
    "stop_out": "Broker stop-out",
    "time_stop": "Time stop",
    "data_hole": "Hole in the tick history",
    "": "Open at end",
}
# exit markers on the price chart: shape = why it closed, colour = won or lost
REASON_SYMBOL = {"target": "circle", "book": "diamond", "force_close": "x",
                 "stop_loss": "square", "stop_out": "star", "time_stop": "hexagon", "data_hole": "diamond-open", "": "circle-open"}
SCORE_COLOR = {"open_score": SERIES[0], "fc_score": SERIES[1], "book_score": SERIES[2]}
SCORE_LABEL = {"open_score": "OPEN score", "fc_score": "FORCE-CLOSE score", "book_score": "BOOK score"}

FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'


def plotly_layout(**kw) -> dict:
    """Base layout: recessive solid hairline grid, ink tokens, no chart junk."""
    base = dict(
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family=FONT, color=INK_2, size=12),
        margin=dict(l=56, r=20, t=36, b=36),
        hoverlabel=dict(bgcolor=SURFACE_2, bordercolor=AXIS, font=dict(family=FONT, color=INK, size=12)),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(color=INK_2, size=12)),
        hovermode="x unified",
        dragmode="pan",
    )
    base.update(kw)
    return base


def axis(**kw) -> dict:
    base = dict(gridcolor=GRID, gridwidth=1, zeroline=False, linecolor=AXIS, linewidth=1,
                tickfont=dict(color=INK_MUTED, size=11), title_font=dict(color=INK_MUTED, size=11),
                showspikes=False, automargin=True)
    base.update(kw)
    return base


CSS = f"""
:root {{
  --page: {PAGE}; --surface: {SURFACE}; --surface-2: {SURFACE_2}; --border: {BORDER};
  --ink: {INK}; --ink-2: {INK_2}; --muted: {INK_MUTED}; --grid: {GRID}; --axis: {AXIS};
  --accent: {ACCENT}; --up: {UP}; --down: {DOWN};
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; background: var(--page); color: var(--ink); font-family: {FONT};
  font-size: 14px; line-height: 1.5; -webkit-font-smoothing: antialiased; }}
a {{ color: var(--accent); text-decoration: none; }} a:hover {{ text-decoration: underline; }}
.wrap {{ max-width: 1500px; margin: 0 auto; padding: 28px 28px 80px; }}
header.top {{ display: flex; align-items: baseline; justify-content: space-between; gap: 16px;
  flex-wrap: wrap; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 22px; }}
header.top h1 {{ font-size: 22px; font-weight: 650; margin: 0; letter-spacing: 0.2px; }}
header.top .sub {{ color: var(--ink-2); font-size: 13px; }}
.brand {{ color: var(--accent); font-weight: 650; letter-spacing: 1.5px; font-size: 12px; text-transform: uppercase; }}
h2 {{ font-size: 15px; font-weight: 650; margin: 34px 0 6px; color: var(--ink); }}
h2 + p.lede {{ margin: 0 0 14px; color: var(--ink-2); max-width: 980px; }}
.card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }}
.card.flush {{ padding: 6px 6px 2px; }}
.card, .tile {{ min-width: 0; }}
.card .plotly-graph-div {{ width: 100% !important; }}
.controls {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px 10px; margin: 4px 0 10px; }}
.controls .lab {{ color: var(--muted); font-size: 12px; margin-left: 6px; }}
.controls .lab:first-child {{ margin-left: 0; }}
.seg {{ display: inline-flex; border: 1px solid var(--axis); border-radius: 8px; overflow: hidden; }}
.seg button {{ background: var(--surface); color: var(--ink-2); border: 0; border-right: 1px solid var(--axis);
  padding: 5px 12px; font: inherit; font-size: 12px; cursor: pointer; }}
.seg button:last-child {{ border-right: 0; }}
.seg button:hover {{ background: var(--surface-2); color: var(--ink); }}
.seg button.on {{ background: var(--surface-2); color: var(--ink); font-weight: 650; box-shadow: inset 0 -2px 0 var(--accent); }}
.hero {{ display: grid; grid-template-columns: minmax(260px, 1.15fr) 3fr; gap: 14px; align-items: stretch; }}
.hero .big {{ display: flex; flex-direction: column; justify-content: center; }}
.hero .big .label {{ color: var(--ink-2); font-size: 13px; }}
.hero .big .value {{ font-size: 54px; font-weight: 680; line-height: 1.05; margin: 4px 0 6px; }}
.hero .big .note {{ color: var(--ink-2); font-size: 13px; }}
.tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }}
.tile {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; }}
.tile .label {{ color: var(--ink-2); font-size: 12px; }}
.tile .value {{ font-size: 22px; font-weight: 650; margin-top: 2px; }}
.tile .note {{ color: var(--muted); font-size: 11.5px; margin-top: 2px; }}
.pos::before {{ content: "\\25B2"; color: var(--up); font-size: 0.55em; margin-right: 0.35em; vertical-align: 0.25em; }}
.neg::before {{ content: "\\25BC"; color: var(--down); font-size: 0.55em; margin-right: 0.35em; vertical-align: 0.25em; }}
.grid2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(430px, 1fr)); gap: 14px; }}
.grid3 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 14px; }}
.card h3 {{ font-size: 13px; font-weight: 650; margin: 2px 0 2px; color: var(--ink); }}
.card p.cap {{ margin: 0 0 6px; color: var(--ink-2); font-size: 12.5px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 12.5px; }}
th, td {{ padding: 6px 10px; text-align: right; border-bottom: 1px solid var(--grid); white-space: nowrap; }}
th {{ color: var(--muted); font-weight: 600; position: sticky; top: 0; background: var(--surface); }}
td {{ color: var(--ink); font-variant-numeric: tabular-nums; }}
th:first-child, td:first-child {{ text-align: left; }}
td.l, th.l {{ text-align: left; }}
.scroll {{ max-height: 420px; overflow: auto; }}
details {{ margin-top: 8px; }} details summary {{ color: var(--muted); cursor: pointer; font-size: 12px; }}
.key {{ display: flex; flex-wrap: wrap; gap: 6px 18px; color: var(--ink-2); font-size: 12.5px; margin: 6px 4px 8px; }}
.key span.sw {{ display: inline-block; width: 11px; height: 11px; margin-right: 6px; vertical-align: -1px; }}
.callout {{ border-left: 3px solid var(--accent); background: var(--surface); padding: 10px 14px;
  border-radius: 0 10px 10px 0; color: var(--ink); margin: 10px 0; }}
.callout b {{ color: var(--ink); }}
.finding {{ display: grid; grid-template-columns: 26px 1fr; gap: 4px 10px; padding: 10px 0; border-bottom: 1px solid var(--grid); }}
.finding .n {{ color: var(--accent); font-weight: 680; }}
.finding .t {{ font-weight: 640; }}
.finding .d {{ grid-column: 2; color: var(--ink-2); }}
code, .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: var(--ink-2); }}
.cfg {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 2px 24px; }}
.cfg div {{ display: flex; justify-content: space-between; gap: 12px; border-bottom: 1px solid var(--grid); padding: 4px 0; }}
.cfg div span:first-child {{ color: var(--ink-2); }}
.foot {{ color: var(--muted); font-size: 12px; margin-top: 36px; border-top: 1px solid var(--border); padding-top: 14px; }}
@media (max-width: 900px) {{ .hero {{ grid-template-columns: 1fr; }} }}
"""
