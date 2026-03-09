import base64
import json
import os
import glob
import re
from datetime import datetime, timezone, timedelta

import dash
from dash import dcc, html, callback_context
from dash.dependencies import Input, Output
import plotly.graph_objects as go
from plotly.subplots import make_subplots


from constants import (
    OUTPUT_DIR, DAILY_TRADE_SUBDIR,
    DASHBOARD_REFRESH_INTERVAL, DASHBOARD_HOST, DASHBOARD_PORT,
    HISTORICAL_SUMMARY_FILENAME,
    GRAPH_TEXT_LABEL_THRESHOLD, GRAPH_CUM_LABEL_THRESHOLD,
    STRATEGY_LOG_FILENAME,
    ACTIVE_CONFIG_FILENAME,
)

# ─── Configuration ───
JSON_DIR = OUTPUT_DIR
DAILY_TRADE_DIR = os.path.join(JSON_DIR, DAILY_TRADE_SUBDIR)
REFRESH_INTERVAL = DASHBOARD_REFRESH_INTERVAL

# ─── Mascot Image (base64 encoded for reliable loading) ───
_MASCOT_IMG_PATH = os.path.join(os.path.dirname(__file__), 'assets', 'alcadeias.png')
try:
    with open(_MASCOT_IMG_PATH, 'rb') as _f:
        _MASCOT_B64 = 'data:image/png;base64,' + base64.b64encode(_f.read()).decode()
except FileNotFoundError:
    _MASCOT_B64 = ''

# ─── Alcadeias Lord of Spirits — Blue / Gold / White Angel Theme ───
COLORS = {
    # Backgrounds — deep celestial navy
    'bg': '#060b18',
    'bg_secondary': '#0a1025',
    'card': 'rgba(10, 16, 37, 0.88)',
    'card_solid': '#0c1328',
    'card_border': 'rgba(192, 168, 100, 0.14)',
    'card_hover': 'rgba(192, 168, 100, 0.08)',
    # Text — luminous white / gold
    'text': '#f0ede4',
    'text_secondary': '#b8b0a0',
    'text_dim': '#5c6478',
    'text_muted': '#3a4058',
    # Accents — divine gold
    'accent': '#d4a843',
    'accent_glow': 'rgba(212, 168, 67, 0.30)',
    'accent_soft': 'rgba(212, 168, 67, 0.12)',
    # Signals — celestial green / ember red
    'buy': '#3cc48e',
    'buy_soft': 'rgba(60, 196, 142, 0.12)',
    'buy_glow': 'rgba(60, 196, 142, 0.30)',
    'sell': '#e05555',
    'sell_soft': 'rgba(224, 85, 85, 0.12)',
    'sell_glow': 'rgba(224, 85, 85, 0.30)',
    # Status
    'positive': '#3cc48e',
    'negative': '#e05555',
    'warning': '#f0c040',
    'neutral': '#5c6478',
    # UI — gold / royal blue
    'header_bg': 'rgba(6, 11, 24, 0.96)',
    'tab_bg': '#0a1025',
    'tab_active': '#d4a843',
    'chart_grid': 'rgba(192, 168, 100, 0.07)',
    'divider': 'rgba(192, 168, 100, 0.10)',
    'gradient_start': '#d4a843',
    'gradient_end': '#4a8ecc',
}


# ─── Shared Styles ───
CARD_STYLE = {
    'background': COLORS['card'],
    'backdropFilter': 'blur(20px)',
    'WebkitBackdropFilter': 'blur(20px)',
    'border': f'1px solid {COLORS["card_border"]}',
    'borderRadius': '16px',
    'padding': '20px 24px',
    'transition': 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
}

SECTION_TITLE_STYLE = {
    'color': COLORS['text'],
    'fontSize': '15px',
    'marginBottom': '0px',
    'fontWeight': '600',
    'letterSpacing': '0.3px',
}


def load_symbol_data(symbol):
    """Load JSON data for a symbol"""
    path = os.path.join(JSON_DIR, f'{symbol}.json')
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def load_account_data():
    """Load account data from dedicated account.json"""
    path = os.path.join(JSON_DIR, 'account.json')
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_available_symbols():
    """Get list of symbols from JSON files in directory"""
    pattern = os.path.join(JSON_DIR, '*.json')
    files = glob.glob(pattern)
    return [
        os.path.splitext(os.path.basename(f))[0]
        for f in files if os.path.basename(f) not in ('account.json', ACTIVE_CONFIG_FILENAME)
    ]


# ─── Active Config Management ───
ACTIVE_CONFIG_PATH = os.path.join(JSON_DIR, ACTIVE_CONFIG_FILENAME)


def load_symbols_config():
    """Load symbols configuration from symbols.json (array-of-objects format)"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'symbols.json')
        with open(config_path, 'r') as f:
            cfg = json.load(f)
        # Extract symbol name list from the array for dashboard usage
        sym_list = cfg.get('symbols', [])
        cfg['_symbol_names'] = [s.get('symbol', '') for s in sym_list if s.get('symbol')]
        return cfg
    except (FileNotFoundError, json.JSONDecodeError):
        return {'symbols': [], '_symbol_names': []}


def load_active_config():
    """Load active configuration (mode + selected symbols)"""
    try:
        with open(ACTIVE_CONFIG_PATH, 'r') as f:
            cfg = json.load(f)
        # Migrate old per-mode format to single active_symbols list
        if 'active_symbols' not in cfg:
            mode = cfg.get('mode', 'demo')
            cfg['active_symbols'] = cfg.get(f'{mode}_symbols', [])
            save_active_config(cfg)
        return cfg
    except (FileNotFoundError, json.JSONDecodeError):
        symbols_cfg = load_symbols_config()
        all_syms = symbols_cfg.get('_symbol_names', [])
        return {
            'mode': 'demo',
            'active_symbols': all_syms[:],
        }


def save_active_config(config):
    """Save active configuration to JSON file"""
    try:
        config_dir = os.path.dirname(ACTIVE_CONFIG_PATH)
        if config_dir:
            os.makedirs(config_dir, exist_ok=True)
        with open(ACTIVE_CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
    except OSError:
        pass


def make_signal_badge(status):
    """Create a premium styled signal badge with glow effect"""
    color_map = {
        'BUY': (COLORS['buy'], COLORS['buy_glow']),
        'SELL': (COLORS['sell'], COLORS['sell_glow']),
        'CLOSE_BUY': (COLORS['warning'], 'rgba(255, 217, 61, 0.25)'),
        'CLOSE_SELL': (COLORS['warning'], 'rgba(255, 217, 61, 0.25)'),
        'BUY_MORE': (COLORS['buy'], COLORS['buy_glow']),
        'SELL_MORE': (COLORS['sell'], COLORS['sell_glow']),
        'DO_NOTHING': (COLORS['neutral'], 'transparent'),
    }
    color, glow = color_map.get(status, (COLORS['neutral'], 'transparent'))
    return html.Span(status, style={
        'background': f'linear-gradient(135deg, {color}, {color}dd)',
        'color': '#fff',
        'padding': '6px 18px',
        'borderRadius': '24px',
        'fontSize': '12px',
        'fontWeight': '700',
        'letterSpacing': '0.8px',
        'boxShadow': f'0 0 20px {glow}, 0 2px 8px rgba(0,0,0,0.3)',
        'textShadow': '0 1px 2px rgba(0,0,0,0.3)',
        'display': 'inline-block',
    })


def make_metric_card(title, value, color=None, sub=None, icon=None):
    """Create a compact metric card"""
    accent = color or COLORS['text']
    return html.Div([
        html.Div([
            html.Span(icon or '', style={
                'fontSize': '11px',
                'marginRight': '5px',
                'opacity': '0.6',
            }) if icon else None,
            html.Span(title, style={
                'fontSize': '9px',
                'color': COLORS['text_dim'],
                'textTransform': 'uppercase',
                'letterSpacing': '1px',
                'fontWeight': '500',
            }),
        ], style={'display': 'flex', 'alignItems': 'center', 'marginBottom': '5px'}),
        html.Div(value, style={
            'fontSize': '16px',
            'fontWeight': '700',
            'color': accent,
            'fontFamily': "'JetBrains Mono', 'SF Mono', monospace",
            'letterSpacing': '-0.3px',
            'lineHeight': '1.2',
        }),
        html.Div(sub, style={
            'fontSize': '9px',
            'color': COLORS['text_dim'],
            'marginTop': '3px',
        }) if sub else None,
    ], style={
        'background': COLORS['card'],
        'border': f'1px solid {COLORS["card_border"]}',
        'borderRadius': '10px',
        'padding': '12px 14px',
        'minWidth': '110px',
        'flex': '1',
    })


def build_positions_section(data):
    """Build compact positions section"""
    pos = data.get('positions', {})
    buy = pos.get('buy', {})
    sell = pos.get('sell', {})
    buy_count = buy.get('count', 0)
    sell_count = sell.get('count', 0)

    if buy_count == 0 and sell_count == 0:
        return html.Div([
            html.Div([
                html.Span('📋', style={'fontSize': '14px'}),
                html.Span('Open Positions', style={**SECTION_TITLE_STYLE, 'fontSize': '13px'}),
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '8px', 'marginBottom': '10px'}),
            html.Div('No open positions', style={
                'color': COLORS['text_dim'], 'fontSize': '12px',
                'padding': '14px 16px', 'textAlign': 'center',
                'background': COLORS['card'], 'borderRadius': '10px',
                'border': f'1px solid {COLORS["card_border"]}',
            }),
        ])

    def pos_row(label, p, color):
        count = p.get('count', 0)
        if count == 0:
            return None
        profit = p.get('total_profit', 0)
        profit_color = COLORS['positive'] if profit >= 0 else COLORS['negative']
        return html.Div([
            html.Div([
                html.Span('●', style={'color': color, 'fontSize': '9px', 'marginRight': '6px'}),
                html.Span(label, style={'fontWeight': '600', 'fontSize': '12px'}),
                html.Span(f'{count}', style={
                    'marginLeft': '6px', 'color': COLORS['text_dim'],
                    'fontSize': '10px', 'background': 'rgba(255,255,255,0.04)',
                    'padding': '1px 7px', 'borderRadius': '8px',
                }),
            ], style={'display': 'flex', 'alignItems': 'center', 'marginBottom': '8px'}),
            html.Div([
                make_metric_card('P/L', f"${profit:.2f}", profit_color),
                make_metric_card('Volume', f"{p.get('total_volume', 0):.2f}"),
                make_metric_card('First', f"${p.get('first_profit', 0):.2f}",
                                 COLORS['positive'] if p.get('first_profit', 0) >= 0 else COLORS['negative']),
                make_metric_card('Last', f"${p.get('last_profit', 0):.2f}",
                                 COLORS['positive'] if p.get('last_profit', 0) >= 0 else COLORS['negative']),
            ], style={'display': 'flex', 'gap': '8px', 'flexWrap': 'wrap'}),
        ], style={
            'background': COLORS['card'],
            'border': f'1px solid {COLORS["card_border"]}',
            'borderRadius': '10px',
            'borderLeft': f'3px solid {color}55',
            'padding': '12px 14px',
            'flex': '1',
        })

    rows = [r for r in [pos_row('BUY', buy, COLORS['buy']), pos_row('SELL', sell, COLORS['sell'])] if r]

    return html.Div([
        html.Div([
            html.Span('📋', style={'fontSize': '14px'}),
            html.Span('Open Positions', style={**SECTION_TITLE_STYLE, 'fontSize': '13px'}),
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '8px', 'marginBottom': '10px'}),
        html.Div(rows, style={'display': 'flex', 'gap': '12px', 'flexWrap': 'wrap'}),
    ])


def build_signal_section(data):
    """Build compact inline signal badges — minimal footprint"""
    signal = data.get('signal', {})
    buy_status = signal.get('buy_status', 'DO_NOTHING')
    sell_status = signal.get('sell_status', 'DO_NOTHING')

    def _mini_badge(label, status):
        color_map = {
            'BUY': COLORS['buy'], 'SELL': COLORS['sell'],
            'CLOSE_BUY': COLORS['warning'], 'CLOSE_SELL': COLORS['warning'],
            'BUY_MORE': COLORS['buy'], 'SELL_MORE': COLORS['sell'],
            'DO_NOTHING': COLORS['text_muted'],
        }
        color = color_map.get(status, COLORS['text_muted'])
        is_active = status != 'DO_NOTHING'
        return html.Div([
            html.Span(label, style={
                'fontSize': '8px', 'color': COLORS['text_dim'],
                'textTransform': 'uppercase', 'letterSpacing': '1px',
                'fontWeight': '500', 'marginRight': '6px',
            }),
            html.Span(status, style={
                'background': f'{color}22' if is_active else 'transparent',
                'color': color,
                'padding': '3px 10px',
                'borderRadius': '12px',
                'fontSize': '10px',
                'fontWeight': '700',
                'letterSpacing': '0.5px',
                'border': f'1px solid {color}44' if is_active else f'1px solid {COLORS["card_border"]}',
            }),
        ], style={'display': 'flex', 'alignItems': 'center'})

    return html.Div([
        html.Span('⚡', style={'fontSize': '11px', 'marginRight': '6px', 'opacity': '0.6'}),
        _mini_badge('B', buy_status),
        _mini_badge('S', sell_status),
    ], style={
        'display': 'flex', 'alignItems': 'center', 'gap': '10px',
        'background': COLORS['card'],
        'border': f'1px solid {COLORS["card_border"]}',
        'borderRadius': '10px',
        'padding': '6px 14px',
    })


def _parse_order_response(order_resp):
    """Parse MT5 OrderSendResult into clean fields"""
    resp_str = str(order_resp)
    fields = {}
    for key in ('retcode', 'comment', 'deal', 'order', 'volume', 'price', 'symbol'):
        if key == 'comment':
            m = re.search(r"comment='([^']*)", resp_str)
        else:
            m = re.search(rf'{key}=([^,)]+)', resp_str)
        if m:
            fields[key] = m.group(1).strip()
    return fields


def build_activity_section(data):
    """Build compact Recent Activity strip for order/close responses.
    Always renders consistently regardless of content."""
    order_resp = data.get('order_response')
    close_resp = data.get('close_response')

    if not order_resp and not close_resp:
        return html.Div()  # Nothing to show

    rows = []

    # ── Order response row ──
    if order_resp:
        f = _parse_order_response(order_resp)
        retcode = f.get('retcode', '?')
        comment = f.get('comment', '')
        symbol = f.get('symbol', '')
        volume = f.get('volume', '')
        is_ok = retcode == '10009'
        rc_color = COLORS['positive'] if is_ok else COLORS['warning']
        icon = '✓' if is_ok else '⚠'

        detail_chips = []
        if symbol:
            detail_chips.append(html.Span(symbol, style={
                'fontSize': '10px', 'color': COLORS['text_secondary'],
                'background': 'rgba(255,255,255,0.04)', 'padding': '2px 8px',
                'borderRadius': '6px', 'marginLeft': '8px',
            }))
        if volume and volume != '0.0':
            detail_chips.append(html.Span(f'vol {volume}', style={
                'fontSize': '10px', 'color': COLORS['text_secondary'],
                'background': 'rgba(255,255,255,0.04)', 'padding': '2px 8px',
                'borderRadius': '6px', 'marginLeft': '4px',
            }))

        rows.append(html.Div([
            html.Span(icon, style={
                'fontSize': '12px', 'marginRight': '10px', 'color': rc_color,
                'width': '16px', 'textAlign': 'center',
            }),
            html.Span('ORDER', style={
                'fontSize': '9px', 'fontWeight': '700', 'color': COLORS['text_dim'],
                'letterSpacing': '1.5px', 'marginRight': '12px', 'minWidth': '42px',
            }),
            html.Span(comment or f'retcode={retcode}', style={
                'fontSize': '12px', 'color': rc_color, 'fontWeight': '500',
                'fontFamily': "'JetBrains Mono', monospace",
            }),
            html.Span(f'  RC {retcode}', style={
                'fontSize': '10px', 'color': COLORS['text_dim'],
                'fontFamily': "'JetBrains Mono', monospace", 'marginLeft': '6px',
            }),
            *detail_chips,
        ], style={
            'display': 'flex', 'alignItems': 'center',
            'padding': '9px 16px',
            'borderBottom': f'1px solid {COLORS["divider"]}' if close_resp else 'none',
        }))

    # ── Close response row ──
    if close_resp:
        success = close_resp.get('success', False)
        closed = close_resp.get('closed_count', 0)
        failed = close_resp.get('failed_count', 0)
        total = close_resp.get('filtered_count', 0)
        errors = close_resp.get('errors', [])
        sc = COLORS['positive'] if success else COLORS['negative']
        icon = '✓' if success else '✗'

        summary = f'{closed}/{total} closed'
        if failed > 0:
            summary += f', {failed} failed'

        err_chip = None
        if errors:
            err_text = errors[0] if len(errors) == 1 else f'{len(errors)} errors'
            err_chip = html.Span(err_text, style={
                'fontSize': '10px', 'color': COLORS['negative'],
                'background': COLORS['sell_soft'], 'padding': '2px 8px',
                'borderRadius': '6px', 'marginLeft': '8px',
                'fontFamily': "'JetBrains Mono', monospace",
            })

        rows.append(html.Div([
            html.Span(icon, style={
                'fontSize': '12px', 'marginRight': '10px', 'color': sc,
                'width': '16px', 'textAlign': 'center',
            }),
            html.Span('CLOSE', style={
                'fontSize': '9px', 'fontWeight': '700', 'color': COLORS['text_dim'],
                'letterSpacing': '1.5px', 'marginRight': '12px', 'minWidth': '42px',
            }),
            html.Span(summary, style={
                'fontSize': '12px', 'color': sc, 'fontWeight': '500',
                'fontFamily': "'JetBrains Mono', monospace",
            }),
            err_chip,
        ], style={
            'display': 'flex', 'alignItems': 'center',
            'padding': '9px 16px',
        }))

    return html.Div([
        html.Div([
            html.Span('📌', style={'fontSize': '11px', 'marginRight': '6px'}),
            html.Span('Recent Activity', style={
                'fontSize': '9px', 'fontWeight': '600', 'color': COLORS['text_dim'],
                'textTransform': 'uppercase', 'letterSpacing': '1.5px',
            }),
        ], style={
            'display': 'flex', 'alignItems': 'center',
            'padding': '8px 16px 4px',
        }),
        *rows,
    ], style={
        'background': COLORS['card'],
        'border': f'1px solid {COLORS["card_border"]}',
        'borderRadius': '10px',
        'marginTop': '12px',
        'overflow': 'hidden',
    })


def _power_bar(power, max_power=7):
    """Compact inline power gauge with colored rectangular segments."""
    dots = []
    for i in range(max_power):
        if i < power:
            c = '#00d2a0' if power >= 5 else '#f39c12' if power >= 3 else '#e74c3c'
        else:
            c = 'rgba(255,255,255,0.06)'
        dots.append(html.Span(style={
            'display': 'inline-block', 'width': '8px', 'height': '16px',
            'borderRadius': '2px', 'background': c, 'marginRight': '2px',
        }))
    p_color = '#00d2a0' if power >= 5 else '#f39c12' if power >= 3 else '#e74c3c'
    return html.Div([
        *dots,
        html.Span(f' {power}', style={
            'fontSize': '0.75rem', 'fontWeight': '700', 'marginLeft': '4px',
            'color': p_color if power > 0 else COLORS['text_dim'],
            'fontFamily': "'JetBrains Mono', monospace",
        }),
    ], style={'display': 'inline-flex', 'alignItems': 'center'})


def _list_dots(lst, max_items=7):
    """Render the bullish/bearish list as colored circle dots with fade."""
    dots = []
    for i, v in enumerate(lst[:max_items]):
        c = '#00d2a0' if v == 1 else '#e74c3c'
        opacity = max(0.35, 1.0 - (i * 0.09))
        dots.append(html.Span(style={
            'display': 'inline-block', 'width': '10px', 'height': '10px',
            'borderRadius': '50%', 'background': c,
            'marginRight': '3px', 'opacity': str(opacity),
        }))
    return html.Div(dots, style={'display': 'inline-flex', 'alignItems': 'center'})


def _signal_row(label, icon, color, power, lst):
    """One compact row for SHA / Price in the signal card — grid layout."""
    return html.Div(
        style={
            'display': 'grid',
            'gridTemplateColumns': '64px 1fr 1fr',
            'gap': '8px', 'alignItems': 'center',
            'padding': '8px 0',
        },
        children=[
            html.Span(f'{icon} {label}', style={
                'fontWeight': '700', 'fontSize': '0.82rem', 'color': color,
            }),
            _power_bar(power),
            _list_dots(lst),
        ],
    )


def _build_gap_row(gap_pct, gap_range, convergence=None):
    """Build the SHA gap% row with range indicator and convergence state."""
    # Convert raw ratio to display percentage
    display_gap = gap_pct * 100
    gap_min = gap_range[0] if gap_range and len(gap_range) >= 2 else 0.001
    gap_max = gap_range[1] if gap_range and len(gap_range) >= 2 else 0.003
    in_range = gap_min <= gap_pct <= gap_max

    display_min = gap_min * 100
    display_max = gap_max * 100

    gap_color = '#00d2a0'
    range_badge_color = '#00d2a0' if in_range else '#ffd93d'
    range_badge_text = '✓ IN RANGE' if in_range else '○ OUT'

    # Convergence state
    conv = convergence or {}
    conv_state = conv.get('state', 'UNKNOWN')
    conv_delta = conv.get('gap_delta', 0)
    _conv_cfg = {
        'DIVERGING':  ('↗ DIVERGING',  '#f39c12', 'rgba(243,156,18,0.12)'),
        'CONVERGING': ('↘ CONVERGING', '#3cc48e', 'rgba(60,196,142,0.12)'),
        'PARALLEL':   ('↔ PARALLEL',   '#5dade2', 'rgba(93,173,226,0.12)'),
        'CLOSE':      ('● CLOSE',      '#a78bfa', 'rgba(167,139,250,0.12)'),
    }
    conv_label, conv_color, conv_bg = _conv_cfg.get(
        conv_state, ('─ UNKNOWN', '#5c6478', 'rgba(92,100,120,0.08)'),
    )
    conv_delta_display = f'{conv_delta * 100:+.4f}%' if conv_delta else ''

    return html.Div(
        style={
            'display': 'flex', 'flexDirection': 'column',
            'gap': '6px', 'padding': '8px 0',
        },
        children=[
            # Row 1: Gap value + range
            html.Div(
                style={
                    'display': 'grid',
                    'gridTemplateColumns': '64px 1fr 1fr',
                    'gap': '8px', 'alignItems': 'center',
                },
                children=[
                    html.Span('📊 Gap', style={
                        'fontWeight': '700', 'fontSize': '0.82rem', 'color': '#a78bfa',
                    }),
                    html.Span(f'{display_gap:.4f}%', style={
                        'fontWeight': '800',
                        'fontSize': '1.05rem',
                        'color': gap_color,
                        'fontFamily': "'JetBrains Mono', monospace",
                    }),
                    html.Div([
                        html.Span(f'{display_min:.2f}% – {display_max:.2f}%', style={
                            'fontSize': '0.72rem',
                            'color': COLORS['text_secondary'],
                            'fontFamily': "'JetBrains Mono', monospace",
                            'marginRight': '8px',
                        }),
                        html.Span(range_badge_text, style={
                            'fontSize': '0.6rem',
                            'fontWeight': '700',
                            'color': range_badge_color,
                            'background': f'{range_badge_color}18',
                            'padding': '2px 8px',
                            'borderRadius': '8px',
                            'border': f'1px solid {range_badge_color}33',
                        }),
                    ], style={'display': 'flex', 'alignItems': 'center'}),
                ],
            ),
            # Row 2: Convergence state
            html.Div(
                style={
                    'display': 'grid',
                    'gridTemplateColumns': '64px 1fr 1fr',
                    'gap': '8px', 'alignItems': 'center',
                },
                children=[
                    html.Span('🔀 State', style={
                        'fontWeight': '700', 'fontSize': '0.82rem', 'color': '#a78bfa',
                    }),
                    html.Span(conv_label, style={
                        'fontWeight': '800',
                        'fontSize': '0.9rem',
                        'color': conv_color,
                        'background': conv_bg,
                        'padding': '3px 12px',
                        'borderRadius': '10px',
                        'border': f'1px solid {conv_color}33',
                        'display': 'inline-block',
                        'width': 'fit-content',
                    }),
                    html.Span(conv_delta_display, style={
                        'fontSize': '0.72rem',
                        'color': COLORS['text_secondary'],
                        'fontFamily': "'JetBrains Mono', monospace",
                    }) if conv_delta_display else html.Span(),
                ],
            ),
        ],
    )


def _build_rsi_row(rsi_value, rsi_mtf=None, rsi_mtf_blocked=False):
    """Build a compact multi-timeframe RSI indicator section for the SHA analysis panel."""

    def _rsi_color_label(rsi):
        if rsi <= 30:
            return '#e74c3c', 'OVERSOLD'
        elif rsi >= 70:
            return '#00d2a0', 'OVERBOUGHT'
        elif rsi >= 50:
            return '#5dade2', 'NEUTRAL'
        else:
            return '#f39c12', 'NEUTRAL'

    def _rsi_mini_row(tf_label, rsi):
        rsi = round(rsi, 2)
        color, label = _rsi_color_label(rsi)
        fill_pct = max(0, min(100, rsi))
        return html.Div(
            style={
                'display': 'grid',
                'gridTemplateColumns': '36px 1fr auto',
                'gap': '8px', 'alignItems': 'center',
                'padding': '3px 0',
            },
            children=[
                html.Span(tf_label, style={
                    'fontWeight': '600', 'fontSize': '0.7rem',
                    'color': COLORS['text_secondary'],
                    'fontFamily': "'JetBrains Mono', monospace",
                }),
                html.Div(style={
                    'width': '100%', 'height': '12px',
                    'background': 'rgba(255,255,255,0.06)',
                    'borderRadius': '3px', 'overflow': 'hidden',
                }, children=[
                    html.Div(style={
                        'width': f'{fill_pct}%', 'height': '100%',
                        'background': color,
                        'borderRadius': '3px',
                        'transition': 'width 0.3s ease',
                    }),
                ]),
                html.Div([
                    html.Span(f'{rsi}', style={
                        'fontWeight': '700', 'fontSize': '0.82rem',
                        'color': color,
                        'fontFamily': "'JetBrains Mono', monospace",
                        'marginRight': '5px',
                    }),
                    html.Span(label, style={
                        'fontSize': '0.55rem', 'fontWeight': '700',
                        'color': color,
                        'background': f'{color}18',
                        'padding': '1px 6px', 'borderRadius': '6px',
                        'border': f'1px solid {color}33',
                    }),
                ], style={'display': 'flex', 'alignItems': 'center', 'whiteSpace': 'nowrap'}),
            ],
        )

    # Build timeframe rows
    tf_display = {'TIMEFRAME_M1': 'M1', 'TIMEFRAME_M5': 'M5', 'TIMEFRAME_M30': 'M30'}
    tf_rows = []
    if rsi_mtf and len(rsi_mtf) > 0:
        for tf_key in ['TIMEFRAME_M1', 'TIMEFRAME_M5', 'TIMEFRAME_M30']:
            if tf_key in rsi_mtf:
                tf_rows.append(_rsi_mini_row(tf_display[tf_key], rsi_mtf[tf_key]))
    else:
        tf_rows.append(_rsi_mini_row('M1', rsi_value))

    # Blocked badge
    blocked_badge = None
    if rsi_mtf_blocked:
        blocked_badge = html.Div([
            html.Span('⛔', style={'fontSize': '10px', 'marginRight': '4px'}),
            html.Span('MTF RSI BLOCKED', style={
                'fontSize': '0.6rem', 'fontWeight': '700',
                'color': '#e74c3c',
                'letterSpacing': '0.5px',
            }),
            html.Span(' — entry paused (all TFs at extreme)', style={
                'fontSize': '0.58rem', 'color': COLORS['text_dim'],
            }),
        ], style={
            'display': 'flex', 'alignItems': 'center',
            'background': 'rgba(231, 76, 60, 0.08)',
            'border': '1px solid rgba(231, 76, 60, 0.25)',
            'borderRadius': '6px',
            'padding': '4px 10px',
            'marginTop': '4px',
        })

    return html.Div(
        style={
            'display': 'grid',
            'gridTemplateColumns': '64px 1fr',
            'gap': '8px', 'alignItems': 'start',
            'padding': '8px 0',
        },
        children=[
            html.Span('📊 RSI', style={
                'fontWeight': '700', 'fontSize': '0.82rem', 'color': '#a78bfa',
                'paddingTop': '3px',
            }),
            html.Div(tf_rows + ([blocked_badge] if blocked_badge else [])),
        ],
    )


def build_sha_analysis_panel(symbol, analysis, last_updated=''):
    """Build clean SHA analysis card — Ballom-inspired grid layout."""
    sha_list = analysis.get('sha_power_list', [])
    price_list = analysis.get('price_power_list', [])
    sha_buy = analysis.get('sha_buy_strength', 0)
    sha_sell = analysis.get('sha_sell_strength', 0)
    price_buy = analysis.get('price_buy_strength', 0)
    price_sell = analysis.get('price_sell_strength', 0)

    # Trend SHA data
    trend_list = analysis.get('sha_trend_power_list', [])
    trend_buy = analysis.get('sha_trend_buy_strength', 0)
    trend_sell = analysis.get('sha_trend_sell_strength', 0)

    # Gap% data
    rsi_value = analysis.get('rsi_value', 50.0)
    rsi_mtf = analysis.get('rsi_mtf', {})
    rsi_mtf_blocked = analysis.get('rsi_mtf_blocked', False)
    gap_pct = analysis.get('current_gap_pct', 0)
    gap_range_val = analysis.get('gap_range', [0.1, 0.30])
    convergence = analysis.get('convergence', {})
    lookback_used = analysis.get('lookback_used', len(sha_list))
    src_count = analysis.get('source_candle_count', 0)
    src_last_time = analysis.get('last_source_candle_time', '-')
    rates_source = analysis.get('rates_source', 'unknown')
    synthetic_bar = analysis.get('synthetic_bar', False)
    tick_rebuilt = analysis.get('tick_rebuilt', False)

    # Overall bias (includes trend)
    total_buy = sha_buy + price_buy + trend_buy
    total_sell = sha_sell + price_sell + trend_sell
    is_bullish = total_buy >= total_sell
    bias_text = 'BULLISH' if is_bullish else 'BEARISH'
    bias_icon = '📈' if is_bullish else '📉'
    bias_color = '#00d2a0' if is_bullish else '#e74c3c'
    trend_bg = 'rgba(0, 210, 160, 0.08)' if is_bullish else 'rgba(231, 76, 60, 0.08)'

    # Column header style
    col_hdr = {
        'fontSize': '0.65rem', 'color': COLORS['text_dim'],
        'fontWeight': '600', 'letterSpacing': '0.5px',
    }

    # Divider line
    row_divider = html.Hr(style={
        'border': 'none',
        'borderTop': f'1px solid {COLORS["divider"]}',
        'margin': '0',
    })

    return html.Div(
        style={
            'background': COLORS['card_solid'],
            'borderRadius': '12px',
            'overflow': 'hidden',
            'border': f'1px solid {COLORS["card_border"]}',
        },
        children=[
            # ── Header bar ──
            html.Div(
                style={
                    'display': 'flex', 'justifyContent': 'space-between',
                    'alignItems': 'center', 'padding': '10px 16px',
                    'background': trend_bg,
                    'borderBottom': f'2px solid {bias_color}',
                },
                children=[
                    html.Span(symbol, style={
                        'fontWeight': '700', 'fontSize': '0.95rem',
                        'color': COLORS['text'], 'letterSpacing': '1px',
                    }),
                    html.Span(f'{bias_icon} {bias_text}', style={
                        'color': bias_color, 'fontWeight': '700',
                        'fontSize': '0.8rem',
                        'background': COLORS['card_solid'],
                        'padding': '2px 10px', 'borderRadius': '10px',
                    }),
                ],
            ),
            # ── Column headers ──
            html.Div(
                style={
                    'display': 'grid',
                    'gridTemplateColumns': '64px 1fr 1fr',
                    'gap': '8px', 'padding': '8px 16px 0',
                },
                children=[
                    html.Span(''),
                    html.Span('POWER', style=col_hdr),
                    html.Span('CANDLES', style=col_hdr),
                ],
            ),
            # ── Signal + Trend + Price + RSI + Gap rows ──
            html.Div(style={'padding': '0 16px 10px'}, children=[
                _signal_row('Signal', '🔵', '#5dade2', sha_buy, sha_list),
                row_divider,
                _signal_row('Trend', '🟣', '#a78bfa', trend_buy, trend_list),
                row_divider,
                _signal_row('Price', '🔴', '#e74c3c', price_buy, price_list),
                row_divider,
                _build_rsi_row(rsi_value, rsi_mtf=rsi_mtf, rsi_mtf_blocked=rsi_mtf_blocked),
                row_divider,
                _build_gap_row(gap_pct, gap_range_val, convergence),
            ]),
            # ── Legend ──
            html.Div(
                style={
                    'padding': '8px 16px 10px',
                    'borderTop': f'1px solid {COLORS["divider"]}',
                    'display': 'flex',
                    'flexWrap': 'wrap',
                    'gap': '16px',
                    'alignItems': 'center',
                },
                children=[
                    html.Span('LEGEND', style={
                        'fontSize': '0.6rem', 'color': COLORS['text_dim'],
                        'fontWeight': '700', 'letterSpacing': '1px',
                        'marginRight': '4px',
                    }),
                    # Candle dots legend
                    html.Div([
                        html.Span(style={
                            'display': 'inline-block', 'width': '8px', 'height': '8px',
                            'borderRadius': '50%', 'background': '#00d2a0',
                            'marginRight': '4px', 'verticalAlign': 'middle',
                        }),
                        html.Span('Bullish', style={
                            'fontSize': '0.65rem', 'color': COLORS['text_secondary'],
                            'verticalAlign': 'middle',
                        }),
                    ], style={'display': 'inline-flex', 'alignItems': 'center'}),
                    html.Div([
                        html.Span(style={
                            'display': 'inline-block', 'width': '8px', 'height': '8px',
                            'borderRadius': '50%', 'background': '#e74c3c',
                            'marginRight': '4px', 'verticalAlign': 'middle',
                        }),
                        html.Span('Bearish', style={
                            'fontSize': '0.65rem', 'color': COLORS['text_secondary'],
                            'verticalAlign': 'middle',
                        }),
                    ], style={'display': 'inline-flex', 'alignItems': 'center'}),
                    # Divider
                    html.Span('│', style={
                        'color': COLORS['text_muted'], 'fontSize': '0.75rem',
                    }),
                    # RSI legend
                    html.Span('RSI:', style={
                        'fontSize': '0.6rem', 'color': COLORS['text_dim'],
                        'fontWeight': '600', 'letterSpacing': '0.5px',
                    }),
                    html.Div([
                        html.Span(style={
                            'display': 'inline-block', 'width': '8px', 'height': '8px',
                            'borderRadius': '50%', 'background': '#e74c3c',
                            'marginRight': '3px',
                        }),
                        html.Span('≤30 Over-sold', style={
                            'fontSize': '0.6rem', 'color': COLORS['text_dim'],
                            'marginRight': '8px',
                        }),
                        html.Span(style={
                            'display': 'inline-block', 'width': '8px', 'height': '8px',
                            'borderRadius': '50%', 'background': '#00d2a0',
                            'marginRight': '3px',
                        }),
                        html.Span('≥70 Over-bought', style={
                            'fontSize': '0.6rem', 'color': COLORS['text_dim'],
                        }),
                    ], style={'display': 'inline-flex', 'alignItems': 'center'}),
                ],
            ),
            # ── Footer timestamp ──
            html.Div(
                f'{last_updated}  |  LKB:{lookback_used}  SRC:{src_count}  LAST:{src_last_time}  |  SRC_API:{rates_source}  SYN:{synthetic_bar}  REBUILD:{tick_rebuilt}',
                style={
                'fontSize': '0.65rem', 'color': COLORS['text_muted'],
                'padding': '4px 16px 8px', 'textAlign': 'right',
                'fontFamily': "'JetBrains Mono', monospace",
            }),
        ],
    )


# ─── Daily Trade Functions ───

def load_daily_trade_data(symbol):
    """Load the most recent daily trade log for a specific symbol."""
    try:
        symbol_dir = os.path.join(DAILY_TRADE_DIR, symbol)
        if not os.path.isdir(symbol_dir):
            return None
        pattern = os.path.join(symbol_dir, '*.json')
        files = [
            f for f in glob.glob(pattern)
            if os.path.basename(f) != HISTORICAL_SUMMARY_FILENAME
        ]
        if not files:
            return None
        latest = max(files, key=os.path.getmtime)
        with open(latest, 'r') as f:
            data = json.load(f)

        symbol_json = load_symbol_data(symbol)
        market_is_open = True
        if symbol_json:
            market_is_open = symbol_json.get('market_status', {}).get('is_open', True)

        if not market_is_open:
            file_server_date = data.get('server_date', '')
            try:
                file_date = datetime.strptime(file_server_date, '%Y-%m-%d').date()
                if file_date != datetime.now(tz=timezone.utc).date():
                    return None
            except (ValueError, TypeError):
                pass

        return data
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return None


def load_daily_trade_data_for_date(symbol, date_str):
    """Load daily trade data for a specific date (YYYY-MM-DD) for a symbol."""
    try:
        symbol_dir = os.path.join(DAILY_TRADE_DIR, symbol)
        if not os.path.isdir(symbol_dir):
            return None
        # Try matching by server_date inside each JSON file
        pattern = os.path.join(symbol_dir, '*.json')
        files = [
            f for f in glob.glob(pattern)
            if os.path.basename(f) != HISTORICAL_SUMMARY_FILENAME
        ]
        for fpath in files:
            try:
                with open(fpath, 'r') as f:
                    data = json.load(f)
                if data.get('server_date', '') == date_str:
                    return data
            except (json.JSONDecodeError, IOError):
                continue
        return None
    except Exception:
        return None


def get_available_daily_dates(symbol, max_days=7):
    """Return a list of (date_str, label) for the last `max_days` days."""
    today = datetime.now(tz=timezone.utc).date()
    result = []
    for i in range(max_days):
        d = today - timedelta(days=i)
        ds = d.strftime('%Y-%m-%d')
        if d == today:
            label = f'Today ({ds})'
        else:
            label = ds
        result.append({'label': label, 'value': ds})
    return result


def load_historical_summary(symbol):
    """Load the historical summary (last 10 years) for a specific symbol"""
    path = os.path.join(DAILY_TRADE_DIR, symbol, HISTORICAL_SUMMARY_FILENAME)
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def load_today_all_symbols_pl():
    """Calculate today's total P/L across all symbols by scanning per-symbol folders"""
    total_pl = 0.0
    total_deals = 0
    try:
        if not os.path.isdir(DAILY_TRADE_DIR):
            return 0, 0
        for entry in os.listdir(DAILY_TRADE_DIR):
            folder_path = os.path.join(DAILY_TRADE_DIR, entry)
            if not os.path.isdir(folder_path):
                continue
            data = load_daily_trade_data(entry)
            if data:
                total_pl += data.get('total_profit', 0)
                total_deals += data.get('deal_count', 0)
    except Exception:
        pass
    return round(total_pl, 2), total_deals


def _build_daily_chart(deals):
    """Build the Plotly chart (bar + cumulative) from a list of deals. Returns a Dash component."""
    if not deals:
        return html.Div([
            html.Div('📭', style={'fontSize': '32px', 'marginBottom': '8px', 'opacity': '0.5'}),
            html.Div('No closed deals for this day', style={
                'color': COLORS['text_dim'], 'fontSize': '13px',
            }),
        ], style={'textAlign': 'center', 'padding': '48px 0'})

    sorted_deals = sorted(deals, key=lambda d: d.get('time', ''))

    labels = []
    profits = []
    volumes = []
    colors = []
    hover_texts = []
    cumulative_profit = 0
    cum_profits = []
    peak = 0
    peaks = []
    drawdowns = []
    dd_pcts = []

    for i, deal in enumerate(sorted_deals, 1):
        try:
            t = datetime.fromisoformat(deal['time']).strftime('%H:%M')
        except (ValueError, TypeError):
            t = f'#{i}'
        labels.append(f'{t}')
        profit = deal.get('net_profit', deal.get('profit', 0))
        profits.append(profit)
        vol = deal.get('volume', 0)
        volumes.append(vol)
        colors.append(COLORS['buy'] if profit >= 0 else COLORS['sell'])
        cumulative_profit += profit
        cum_profits.append(round(cumulative_profit, 2))
        if cumulative_profit > peak:
            peak = cumulative_profit
        peaks.append(round(peak, 2))
        dd = peak - cumulative_profit
        drawdowns.append(round(dd, 2))
        dd_pct = (dd / peak * 100) if peak > 0 else 0
        dd_pcts.append(round(dd_pct, 2))
        raw_profit = deal.get('profit', 0)
        commission = deal.get('commission', 0)
        swap = deal.get('swap', 0)
        fee = deal.get('fee', 0)
        hover_texts.append(
            f"Time: {t}<br>"
            f"Type: {deal.get('type', 'N/A')}<br>"
            f"Volume: {vol}<br>"
            f"Gross Profit: ${raw_profit:.2f}<br>"
            f"Commission: ${commission:.2f}<br>"
            f"Swap: ${swap:.2f}<br>"
            f"Fee: ${fee:.2f}<br>"
            f"Net P/L: ${profit:.2f}<br>"
            f"Cumulative: ${cumulative_profit:.2f}<br>"
            f"Peak: ${peak:.2f}<br>"
            f"Drawdown: ${dd:.2f} ({dd_pct:.1f}%)"
        )

    max_dd = max(drawdowns) if drawdowns else 0
    max_dd_pct = max(dd_pcts) if dd_pcts else 0

    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.45, 0.55],
        vertical_spacing=0.14,
        subplot_titles=['Profit/Loss per Deal', 'Cumulative P/L & Drawdown'],
    )

    n_deals = len(sorted_deals)
    show_bar_text = n_deals <= GRAPH_TEXT_LABEL_THRESHOLD
    show_cum_text = n_deals <= GRAPH_CUM_LABEL_THRESHOLD

    fig.add_trace(go.Bar(
        x=labels, y=profits,
        marker=dict(color=colors, line=dict(width=0)),
        text=[f'${p:.2f}' for p in profits] if show_bar_text else None,
        textposition='outside' if show_bar_text else None,
        textfont=dict(size=10, color=COLORS['text_secondary'], family="'Inter', sans-serif") if show_bar_text else None,
        hovertext=hover_texts,
        hoverinfo='text',
        showlegend=False,
    ), row=1, col=1)

    cum_color = COLORS['positive'] if cumulative_profit >= 0 else COLORS['negative']
    _r, _g, _b = int(cum_color[1:3], 16), int(cum_color[3:5], 16), int(cum_color[5:7], 16)
    cum_fill = f'rgba({_r},{_g},{_b},0.05)'

    cum_mode = 'lines+markers+text' if show_cum_text else 'lines'
    cum_marker = dict(size=5, color=cum_color, line=dict(width=1, color=COLORS['bg'])) if show_cum_text else dict(size=0)
    fig.add_trace(go.Scatter(
        x=labels, y=cum_profits,
        mode=cum_mode,
        line=dict(color=cum_color, width=2, shape='spline'),
        marker=cum_marker,
        text=[f'${c:.0f}' for c in cum_profits] if show_cum_text else None,
        textposition='top center' if show_cum_text else None,
        textfont=dict(size=9, color=COLORS['text_dim'], family="'Inter', sans-serif") if show_cum_text else None,
        showlegend=False,
        fill='tozeroy',
        fillcolor=cum_fill,
        name='Cumulative P/L',
    ), row=2, col=1)

    # Peak line (gold dashed)
    fig.add_trace(go.Scatter(
        x=labels, y=peaks,
        mode='lines',
        line=dict(color=COLORS['accent'], width=1.5, dash='dot'),
        showlegend=False,
        name='Peak',
        hoverinfo='skip',
    ), row=2, col=1)

    # Drawdown fill — shade between peak and cumulative P/L
    fig.add_trace(go.Scatter(
        x=labels, y=peaks,
        mode='lines',
        line=dict(width=0),
        showlegend=False,
        hoverinfo='skip',
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=labels, y=cum_profits,
        mode='lines',
        line=dict(width=0),
        fill='tonexty',
        fillcolor='rgba(224, 85, 85, 0.15)',
        showlegend=False,
        hoverinfo='skip',
        name='Drawdown',
    ), row=2, col=1)

    fig.add_hline(y=0, line_dash='dot', line_color=COLORS['text_muted'],
                   opacity=0.5, row=2, col=1)

    fig.update_layout(
        height=480,
        margin=dict(l=50, r=20, t=30, b=30),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color=COLORS['text_secondary'], size=11, family="'Inter', sans-serif"),
    )
    tick_step = max(1, n_deals // 30) if n_deals > 40 else None
    for i in range(1, 3):
        fig.update_xaxes(showgrid=False, row=i, col=1,
                         tickfont=dict(size=9, color=COLORS['text_dim']),
                         dtick=tick_step,
                         tickangle=-45 if n_deals > 40 else 0)
        fig.update_yaxes(
            showgrid=True, gridcolor=COLORS['chart_grid'],
            gridwidth=0.5, zeroline=True,
            zerolinecolor=COLORS['text_muted'], zerolinewidth=0.5,
            row=i, col=1,
            tickfont=dict(size=10, color=COLORS['text_dim']),
        )
    for ann in fig['layout']['annotations']:
        ann['font'] = dict(size=11, color=COLORS['text_dim'], family="'Inter', sans-serif")

    # Max drawdown summary strip
    dd_summary = html.Div([
        html.Span('Max Drawdown: ', style={'color': COLORS['text_dim'], 'fontSize': '11px'}),
        html.Span(f'${max_dd:.2f}', style={'color': COLORS['sell'], 'fontSize': '12px', 'fontWeight': '700',
                                            'fontFamily': "'JetBrains Mono', monospace"}),
        html.Span(f'  ({max_dd_pct:.1f}%)', style={'color': COLORS['text_dim'], 'fontSize': '11px', 'marginLeft': '4px'}),
    ], style={'padding': '6px 14px 2px', 'display': 'flex', 'alignItems': 'center', 'gap': '2px'}) if max_dd > 0 else None

    return html.Div([
        dcc.Graph(
            figure=fig,
            config={'displayModeBar': False},
            style={'height': '480px'},
        ),
        dd_summary,
    ]) if dd_summary else dcc.Graph(
        figure=fig,
        config={'displayModeBar': False},
        style={'height': '480px'},
    )


def build_daily_trades_section(symbol, selected_date=None):
    """Build daily trades chart and metrics for a symbol — premium version with day selector"""
    today_str = datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')
    active_date = selected_date if selected_date else today_str
    is_today = (active_date == today_str)

    if is_today:
        daily_data = load_daily_trade_data(symbol)
    else:
        daily_data = load_daily_trade_data_for_date(symbol, active_date)

    historical = load_historical_summary(symbol)

    deals = daily_data.get('deals', []) if daily_data else []
    sym_total = daily_data.get('total_profit', 0) if daily_data else 0
    sym_avg = daily_data.get('avg_profit', 0) if daily_data else 0
    sym_count = daily_data.get('deal_count', 0) if daily_data else 0
    hist_total = historical.get('total_profit', 0) if historical else 0
    hist_count = historical.get('total_deals', 0) if historical else 0

    all_sym_pl, all_sym_deals = load_today_all_symbols_pl()

    if is_today:
        day_label = 'Today'
    else:
        try:
            d = datetime.strptime(active_date, '%Y-%m-%d')
            day_label = d.strftime('%d %b')
        except (ValueError, TypeError):
            day_label = active_date

    metrics_row = html.Div([
        make_metric_card(
            f'{symbol} P/L {day_label}',
            f'${sym_total:,.2f}',
            COLORS['positive'] if sym_total >= 0 else COLORS['negative'],
            f'{sym_count} deals', icon='📊',
        ),
        make_metric_card(
            f'{symbol} Avg Profit',
            f'${sym_avg:,.2f}',
            COLORS['positive'] if sym_avg >= 0 else COLORS['negative'],
            'per deal', icon='📉',
        ),
        make_metric_card(
            f'{symbol} Lifetime P/L',
            f'${hist_total:,.2f}',
            COLORS['positive'] if hist_total >= 0 else COLORS['negative'],
            f'{hist_count} deals (10y)', icon='🏦',
        ),
        make_metric_card(
            'All Symbols Today',
            f'${all_sym_pl:,.2f}',
            COLORS['positive'] if all_sym_pl >= 0 else COLORS['negative'],
            f'{all_sym_deals} deals total', icon='🌐',
        ),
    ], style={'display': 'flex', 'gap': '12px', 'flexWrap': 'wrap', 'marginBottom': '16px'})

    # Build the chart for the selected date
    chart = _build_daily_chart(deals)

    # Day selector dropdown — last 7 days
    available_dates = get_available_daily_dates(symbol, max_days=7)
    default_date = active_date

    day_dropdown = dcc.Dropdown(
        id='daily-day-selector',
        options=available_dates,
        value=default_date,
        clearable=False,
        searchable=True,
        placeholder='Select day...',
        style={
            'width': '260px',
            'fontSize': '13px',
        },
    )

    return html.Div([
        html.Div([
            html.Div([
                html.Span('📈', style={'fontSize': '14px'}),
                html.Span('Daily Trade Log', style={**SECTION_TITLE_STYLE, 'fontSize': '13px'}),
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '8px'}),
            day_dropdown,
        ], style={
            'display': 'flex', 'justifyContent': 'space-between',
            'alignItems': 'center', 'marginBottom': '10px',
        }),
        html.Div(id='daily-metrics-container', children=[metrics_row]),
        html.Div([chart], id='daily-chart-container', style={
            'background': COLORS['card'],
            'border': f'1px solid {COLORS["card_border"]}',
            'borderRadius': '10px',
            'padding': '12px 14px',
        }),
    ])


# ─── Strategy Log Functions ───

def load_strategy_log(symbol):
    """Load strategy log entries for a symbol"""
    log_path = os.path.join(JSON_DIR, 'logs', f'{symbol}_{STRATEGY_LOG_FILENAME}')
    try:
        with open(log_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _event_badge_config(event):
    """Return (color, bg, icon) for a strategy log event"""
    mapping = {
        'BUY_EXECUTED':       (COLORS['buy'],     COLORS['buy_soft'],  '⚡'),
        'SELL_EXECUTED':      (COLORS['sell'],     COLORS['sell_soft'], '⚡'),
        'BUY_MORE_EXECUTED':  (COLORS['buy'],     COLORS['buy_soft'],  '⚡'),
        'SELL_MORE_EXECUTED': (COLORS['sell'],     COLORS['sell_soft'], '⚡'),
        'CLOSE_BUY':          (COLORS['warning'],  'rgba(255,217,61,0.12)', '✕'),
        'CLOSE_SELL':         (COLORS['warning'],  'rgba(255,217,61,0.12)', '✕'),
        'BUY_SIGNAL':         ('#5dade2',          'rgba(93,173,226,0.12)',  '◦'),
        'SELL_SIGNAL':        ('#e57373',          'rgba(229,115,115,0.12)', '◦'),
    }
    return mapping.get(event, (COLORS['text_dim'], 'rgba(255,255,255,0.04)', '•'))


def _tag_color(tag):
    """Return color for a log tag"""
    return {
        'ENTRY': COLORS['buy'],
        'EXIT': COLORS['warning'],
        'SIGNAL': COLORS['accent'],
        'ERROR': COLORS['sell'],
    }.get(tag, COLORS['text_dim'])


def build_strategy_log_section(symbol):
    """Build the Strategy Log panel with clickable/hoverable entries"""
    log_entries = load_strategy_log(symbol)

    if not log_entries:
        return html.Div([
            html.Div([
                html.Span('📋', style={'fontSize': '14px'}),
                html.Span('Strategy Log', style={**SECTION_TITLE_STYLE, 'fontSize': '13px'}),
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '8px', 'marginBottom': '10px'}),
            html.Div([
                html.Div('📭', style={'fontSize': '24px', 'marginBottom': '6px', 'opacity': '0.4'}),
                html.Div('No strategy events yet', style={
                    'color': COLORS['text_dim'], 'fontSize': '12px',
                }),
            ], style={
                'textAlign': 'center', 'padding': '32px 0',
                'background': COLORS['card'],
                'border': f'1px solid {COLORS["card_border"]}',
                'borderRadius': '10px',
            }),
        ])

    rows = []
    for entry in log_entries:
        event = entry.get('event', '')
        tag = entry.get('tag', '')
        details = entry.get('details', {})
        evt_color, evt_bg, evt_icon = _event_badge_config(event)
        t_color = _tag_color(tag)

        # Parse time
        try:
            dt = datetime.fromisoformat(entry.get('time', ''))
            time_str = dt.strftime('%H:%M:%S')
        except (ValueError, TypeError):
            time_str = '--:--:--'

        # Build detail chips for inline preview
        chips = []
        if details.get('qty'):
            chips.append(f"qty: {details['qty']}")
        if details.get('fibo_level'):
            chips.append(f"fibo: {details['fibo_level']}")
        if details.get('total_profit') is not None and tag == 'EXIT':
            chips.append(f"P/L: ${details['total_profit']}")
        if details.get('positions_closed'):
            chips.append(f"closed: {details['positions_closed']}")
        if details.get('note'):
            chips.append(details['note'])

        chip_text = '  •  '.join(chips) if chips else ''

        # Build full-detail key-value rows for the expandable section
        # Show only meaningful fields, skip nested dicts like raw response
        _detail_display_keys = [
            ('symbol', 'Symbol'),
            ('qty', 'Volume'),
            ('fibo_level', 'Fibo Level'),
            ('total_volume', 'Total Volume'),
            ('total_profit', 'Total P/L'),
            ('first_profit', 'First P/L'),
            ('positions_closed', 'Positions Closed'),
            ('note', 'Note'),
            ('message', 'Message'),
            ('comment', 'Comment'),
        ]
        detail_rows = []
        for key, label in _detail_display_keys:
            val = details.get(key)
            if val is None:
                continue
            # Format money values
            if 'profit' in key.lower():
                val_str = f'${val}'
                val_color = COLORS['positive'] if float(val) >= 0 else COLORS['negative']
            else:
                val_str = str(val)
                val_color = COLORS['text_secondary']
            detail_rows.append(
                html.Div([
                    html.Span(label, style={
                        'fontSize': '10px', 'color': COLORS['text_dim'],
                        'minWidth': '100px', 'flexShrink': '0',
                        'fontWeight': '500', 'letterSpacing': '0.3px',
                    }),
                    html.Span(val_str, style={
                        'fontSize': '11px', 'color': val_color,
                        'fontFamily': "'JetBrains Mono', monospace",
                        'fontWeight': '500',
                    }),
                ], style={'display': 'flex', 'gap': '12px', 'padding': '3px 0'})
            )
        # Parse response string for retcode / comment if present
        resp_raw = details.get('response', '')
        if isinstance(resp_raw, str) and 'retcode' in resp_raw:
            for rk, rl in [('retcode', 'Retcode'), ('comment', 'Comment')]:
                if rk == 'comment':
                    m = re.search(r"comment='([^']*)", resp_raw)
                else:
                    m = re.search(rf'{rk}=([^,)]+)', resp_raw)
                if m:
                    detail_rows.append(
                        html.Div([
                            html.Span(rl, style={
                                'fontSize': '10px', 'color': COLORS['text_dim'],
                                'minWidth': '100px', 'flexShrink': '0',
                                'fontWeight': '500',
                            }),
                            html.Span(m.group(1).strip(), style={
                                'fontSize': '11px', 'color': COLORS['text_secondary'],
                                'fontFamily': "'JetBrains Mono', monospace",
                            }),
                        ], style={'display': 'flex', 'gap': '12px', 'padding': '3px 0'})
                    )
        # If response is a dict (close_response), extract key fields
        if isinstance(resp_raw, dict):
            for rk, rl in [('message', 'Message'), ('closed_count', 'Closed'), ('failed_count', 'Failed')]:
                rv = resp_raw.get(rk)
                if rv is not None:
                    detail_rows.append(
                        html.Div([
                            html.Span(rl, style={
                                'fontSize': '10px', 'color': COLORS['text_dim'],
                                'minWidth': '100px', 'flexShrink': '0',
                                'fontWeight': '500',
                            }),
                            html.Span(str(rv), style={
                                'fontSize': '11px', 'color': COLORS['text_secondary'],
                                'fontFamily': "'JetBrains Mono', monospace",
                            }),
                        ], style={'display': 'flex', 'gap': '12px', 'padding': '3px 0'})
                    )

        row = html.Div([
            # Timestamp
            html.Span(time_str, style={
                'fontSize': '11px', 'color': COLORS['text_dim'],
                'fontFamily': "'JetBrains Mono', monospace",
                'minWidth': '60px', 'flexShrink': '0',
            }),
            # Event badge
            html.Span(f'{evt_icon} {event}', style={
                'background': evt_bg,
                'color': evt_color,
                'padding': '3px 10px',
                'borderRadius': '10px',
                'fontSize': '11px',
                'fontWeight': '700',
                'letterSpacing': '0.3px',
                'whiteSpace': 'nowrap',
                'flexShrink': '0',
            }),
            # Tag
            html.Span(tag, style={
                'fontSize': '9px',
                'fontWeight': '700',
                'color': t_color,
                'letterSpacing': '1px',
                'flexShrink': '0',
            }),
            # Inline summary chips
            html.Span(chip_text, style={
                'fontSize': '11px',
                'color': COLORS['text_secondary'],
                'fontFamily': "'JetBrains Mono', monospace",
                'overflow': 'hidden',
                'textOverflow': 'ellipsis',
                'whiteSpace': 'nowrap',
                'flex': '1',
                'minWidth': '0',
            }) if chip_text else html.Span(),
        ], style={
            'display': 'flex', 'alignItems': 'center', 'gap': '10px',
            'padding': '8px 14px',
            'borderBottom': f'1px solid {COLORS["divider"]}',
            'cursor': 'pointer',
            'transition': 'background 0.15s',
        },
        # The detail block is in a sibling <details> below
        )

        # Expandable detail block (click to expand on desktop, tap on touch)
        detail_block = html.Details([
            html.Summary(row, style={
                'listStyleType': 'none',
                'outline': 'none',
            }),
            html.Div(detail_rows, style={
                'background': 'rgba(0,0,0,0.25)',
                'borderRadius': '8px',
                'padding': '10px 14px',
                'margin': '0 14px 8px 14px',
                'maxHeight': '180px',
                'overflow': 'auto',
            }) if detail_rows else html.Div(),
        ], style={'margin': '0'})

        rows.append(detail_block)

    return html.Div([
        html.Div([
            html.Span('📋', style={'fontSize': '14px'}),
            html.Span('Strategy Log', style={**SECTION_TITLE_STYLE, 'fontSize': '13px'}),
            html.Span(f'{len(log_entries)} events', style={
                'fontSize': '9px', 'color': COLORS['text_dim'],
                'marginLeft': '8px', 'background': 'rgba(255,255,255,0.04)',
                'padding': '2px 8px', 'borderRadius': '8px',
            }),
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '8px', 'marginBottom': '10px'}),
        html.Div(rows, style={
            'background': COLORS['card'],
            'border': f'1px solid {COLORS["card_border"]}',
            'borderRadius': '10px',
            'maxHeight': '400px',
            'overflowY': 'auto',
            'overflowX': 'hidden',
        }),
    ])


def build_symbol_tab_content(symbol, selected_date=None):
    """Build complete content for a single symbol tab — premium version"""
    data = load_symbol_data(symbol)

    if data is None:
        skeleton_bar = lambda w: html.Div(style={
            'height': '12px', 'width': w, 'borderRadius': '8px',
            'background': f'linear-gradient(90deg, {COLORS["card_border"]}00, {COLORS["card_border"]}, {COLORS["card_border"]}00)',
            'marginBottom': '12px',
        })
        return html.Div([
            html.Div([
                html.H2(symbol, style={
                    'margin': '0 0 24px 0', 'fontSize': '28px', 'fontWeight': '700',
                    'color': COLORS['text'],
                    'background': f'linear-gradient(135deg, {COLORS["text"]}, {COLORS["accent"]})',
                    'WebkitBackgroundClip': 'text',
                    'WebkitTextFillColor': 'transparent',
                }),
                html.Div([
                    skeleton_bar('60%'), skeleton_bar('45%'), skeleton_bar('80%'),
                    html.Div(style={'height': '20px'}),
                    skeleton_bar('50%'), skeleton_bar('70%'),
                ]),
                html.Div(f'Connecting to {symbol}...', style={
                    'textAlign': 'center', 'color': COLORS['text_dim'],
                    'fontSize': '13px', 'marginTop': '40px',
                    'fontStyle': 'italic',
                }),
            ], className='skeleton-pulse', style={'marginTop': '40px'}),
        ])

    analysis = data.get('analysis', {})
    last_updated = data.get('last_updated', '')

    try:
        dt = datetime.fromisoformat(last_updated)
        time_str = dt.strftime('%H:%M:%S')
        date_str = dt.strftime('%d %b %Y')
    except (ValueError, TypeError):
        time_str = '--:--:--'
        date_str = ''

    mkt = data.get('market_status', {})
    mkt_is_open = mkt.get('is_open', False)
    mkt_status = mkt.get('status', 'UNKNOWN')
    mkt_minutes = mkt.get('minutes_since_last')
    mkt_color = COLORS['buy'] if mkt_is_open else COLORS['sell']
    mkt_glow = COLORS['buy_glow'] if mkt_is_open else COLORS['sell_glow']
    mkt_sub = f'{mkt_minutes}m since last candle' if mkt_minutes is not None else ''

    return html.Div([
        # ── Header row ──
        html.Div([
            html.Div([
                html.H2(symbol, style={
                    'margin': '0', 'fontSize': '22px', 'fontWeight': '800',
                    'color': COLORS['text'],
                    'letterSpacing': '1px',
                }),
                html.Span(f'{date_str}  •  {time_str}', style={
                    'fontSize': '11px', 'color': COLORS['text_dim'],
                    'marginLeft': '14px', 'fontWeight': '400',
                    'fontFamily': "'JetBrains Mono', monospace",
                }),
            ], style={'display': 'flex', 'alignItems': 'baseline'}),
            # Market status badge
            html.Div([
                html.Div(style={
                    'width': '8px', 'height': '8px', 'borderRadius': '50%',
                    'background': mkt_color,
                    'boxShadow': f'0 0 10px {mkt_glow}',
                    'marginRight': '10px',
                }),
                html.Span(mkt_status, style={
                    'background': f'{mkt_color}18',
                    'color': mkt_color,
                    'padding': '5px 16px',
                    'borderRadius': '24px',
                    'fontSize': '11px',
                    'fontWeight': '700',
                    'letterSpacing': '1px',
                    'border': f'1px solid {mkt_color}33',
                }),
                html.Span(f'  {mkt_sub}', style={
                    'fontSize': '11px', 'color': COLORS['text_dim'], 'marginLeft': '10px',
                }) if mkt_sub else None,
            ], style={'display': 'flex', 'alignItems': 'center'}),
        ], style={
            'display': 'flex', 'justifyContent': 'space-between',
            'alignItems': 'center', 'marginBottom': '16px',
            'paddingBottom': '14px',
            'borderBottom': f'1px solid {COLORS["divider"]}',
        }),

        # ── Top row: Signal badges + Positions ──
        html.Div([
            build_signal_section(data),
            html.Div(style={'flex': '1'}),
        ], style={'display': 'flex', 'gap': '12px', 'alignItems': 'center', 'marginBottom': '12px'}),

        build_positions_section(data),

        # ── Recent Activity (order / close responses) ──
        build_activity_section(data),

        html.Div(style={'height': '16px'}),

        # ── SHA Signal Analysis (compact table panel) ──
        html.Div([
            html.Div([
                html.Span('🎯', style={'fontSize': '14px'}),
                html.Span('SHA Signal Analysis', style={**SECTION_TITLE_STYLE, 'fontSize': '13px'}),
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '8px', 'marginBottom': '10px'}),
            build_sha_analysis_panel(symbol, analysis, last_updated),
        ]),

        html.Div(style={'height': '16px'}),

        # Daily Trade Log section
        build_daily_trades_section(symbol, selected_date=selected_date),

        html.Div(style={'height': '16px'}),

        # Strategy Log section
        build_strategy_log_section(symbol),

        html.Div(style={'height': '16px'}),

        # Raw JSON
        html.Details([
            html.Summary('Raw JSON Data', style={
                'color': COLORS['text_dim'], 'cursor': 'pointer', 'fontSize': '12px',
                'padding': '10px 0', 'fontWeight': '500', 'letterSpacing': '0.5px',
                'outline': 'none',
            }),
            html.Pre(
                json.dumps(data, indent=2, default=str),
                style={
                    **CARD_STYLE,
                    'fontSize': '11px',
                    'color': COLORS['text_dim'],
                    'maxHeight': '300px',
                    'overflow': 'auto',
                    'marginTop': '8px',
                    'fontFamily': "'JetBrains Mono', 'SF Mono', monospace",
                    'lineHeight': '1.6',
                },
            ),
        ]),
    ])


# ─── App Setup ───
app = dash.Dash(
    __name__,
    title='Alcadeias Trading Dashboard',
    update_title=None,
    suppress_callback_exceptions=True,
    assets_folder='assets',
)
app.index_string = '''<!DOCTYPE html>
<html>
<head>
{%metas%}
<title>{%title%}</title>
<link rel="icon" type="image/png" href="/assets/alcadeias.png">
<link rel="shortcut icon" type="image/png" href="/assets/alcadeias.png">
{%css%}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
    /* === Reset & Base — Alcadeias Angel Theme === */
    *, *::before, *::after { box-sizing: border-box; }
    body {
        margin: 0;
        padding: 0;
        background: #060b18;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }

    /* === Hide Dash Loading === */
    ._dash-loading-callback,
    .dash-loading,
    ._dash-loading,
    div._dash-loading-callback--is-loading {
        visibility: hidden !important;
    }

    /* === Custom Scrollbar — gold accent === */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb {
        background: rgba(212, 168, 67, 0.30);
        border-radius: 10px;
    }
    ::-webkit-scrollbar-thumb:hover { background: rgba(212, 168, 67, 0.55); }

    /* === Animations === */
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes pulse {
        0%, 100% { opacity: 0.3; }
        50% { opacity: 0.7; }
    }
    @keyframes shimmer {
        0% { background-position: -200% 0; }
        100% { background-position: 200% 0; }
    }
    @keyframes glow {
        0%, 100% { opacity: 0.6; }
        50% { opacity: 1; }
    }
    @keyframes haloRotate {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    @keyframes divinePulse {
        0%, 100% { box-shadow: 0 0 8px rgba(212,168,67,0.2), 0 0 20px rgba(74,142,204,0.1); }
        50% { box-shadow: 0 0 16px rgba(212,168,67,0.4), 0 0 40px rgba(74,142,204,0.2); }
    }

    #tab-content {
        animation: fadeIn 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .skeleton-pulse {
        animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }

    /* === Gradient Top Bar — gold / royal blue shimmer === */
    .gradient-bar {
        height: 3px;
        background: linear-gradient(90deg, #d4a843, #4a8ecc, #f0e6c0, #4a8ecc, #d4a843);
        background-size: 300% auto;
        animation: shimmer 5s linear infinite;
    }

    /* === Text Selection — golden === */
    ::selection {
        background: rgba(212, 168, 67, 0.3);
        color: #f0ede4;
    }

    /* === Details Marker === */
    details > summary { list-style-type: none; }
    details > summary::-webkit-details-marker { display: none; }
    details > summary::before {
        content: '▸ ';
        color: #5c6478;
        transition: transform 0.2s;
    }
    details[open] > summary::before {
        content: '▾ ';
    }

    /* === Strategy Log Row Hover === */
    details > summary > div:hover {
        background: rgba(192, 168, 100, 0.06) !important;
    }

    /* === Plotly Tooltips === */
    .plotly .hoverlayer .hovertext {
        font-family: 'Inter', sans-serif !important;
    }

    /* === Dark Dropdown Override — Alcadeias Gold Theme === */
    .dash-dropdown,
    .dash-dropdown * {
        box-sizing: border-box !important;
    }
    /* Main dropdown container / input area */
    .dash-dropdown .Select-control,
    :not(#daily-day-selector) > .Select > .Select-control {
        background-color: #0a1025 !important;
        background: #0a1025 !important;
        border: 1px solid rgba(192, 168, 100, 0.25) !important;
        color: #f0ede4 !important;
    }
    .dash-dropdown .Select-multi-value-wrapper {
        background: transparent !important;
    }
    /* Menu / dropdown list */
    .dash-dropdown .Select-menu-outer,
    :not(#daily-day-selector) > .Select > .Select-menu-outer,
    .dash-dropdown [class*="menu"] {
        background-color: #0c1328 !important;
        background: #0c1328 !important;
        border: 1px solid rgba(192, 168, 100, 0.25) !important;
        z-index: 999 !important;
    }
    /* Options in the list */
    .dash-dropdown .Select-option,
    :not(#daily-day-selector) > .Select .Select-option,
    :not(#daily-day-selector) > .Select .VirtualizedSelectOption {
        background-color: #0c1328 !important;
        background: #0c1328 !important;
        color: #f0ede4 !important;
    }
    :not(#daily-day-selector) > .Select .VirtualizedSelectFocusedOption,
    :not(#daily-day-selector) > .Select .Select-option.is-focused {
        background-color: #1a2540 !important;
        background: #1a2540 !important;
    }
    /* Selected value chips / tags */
    .dash-dropdown .Select-value,
    :not(#daily-day-selector) > .Select .Select-value {
        background-color: #162040 !important;
        background: #162040 !important;
        border: 1px solid rgba(212, 168, 67, 0.40) !important;
        color: #ffffff !important;
    }
    /* Value labels */
    .dash-dropdown .Select-value-label,
    :not(#daily-day-selector) > .Select .Select-value-label {
        color: #ffffff !important;
        font-weight: 600 !important;
        font-size: 12px !important;
    }
    /* Input text */
    .dash-dropdown .Select-input input,
    :not(#daily-day-selector) > .Select .Select-input input {
        color: #f0ede4 !important;
        background: transparent !important;
    }
    /* Placeholder */
    :not(#daily-day-selector) > .Select .Select-placeholder {
        color: #5c6478 !important;
    }
    /* Arrow / chevron */
    :not(#daily-day-selector) > .Select .Select-arrow-zone .Select-arrow {
        border-color: #5c6478 transparent transparent !important;
    }
    /* Clear button */
    :not(#daily-day-selector) > .Select .Select-clear-zone {
        color: #5c6478 !important;
    }
    /* No results text */
    :not(#daily-day-selector) > .Select .Select-noresults {
        background-color: #0c1328 !important;
        background: #0c1328 !important;
        color: #5c6478 !important;
    }

    /* === ALL Dropdowns and selects on page — global dark theme === */
    .Select, .Select div, .Select span,
    [class*="dropdown"] [class*="control"],
    [class*="dropdown"] [class*="menu"],
    [class*="dropdown"] [class*="option"],
    select {
        font-family: 'Inter', sans-serif !important;
    }
    select, select option {
        background-color: #0c1328 !important;
        background: #0c1328 !important;
        color: #f0ede4 !important;
        border-color: rgba(192, 168, 100, 0.25) !important;
    }

    /* === Mode Toggle Buttons === */
    /* (removed — mode is now read-only, set via start_job.bat) */

    /* === Mascot container glow === */
    .mascot-container {
        animation: divinePulse 3s ease-in-out infinite;
        border-radius: 14px;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    /* === Daily Day Selector — FULL WHITE THEME (like clean dropdown) === */
    #daily-day-selector,
    #daily-day-selector * {
        box-sizing: border-box !important;
    }
    #daily-day-selector .Select-control {
        background-color: #0d1530 !important;
        background: #0d1530 !important;
        border: 1px solid rgba(192, 168, 100, 0.3) !important;
        border-radius: 20px !important;
        cursor: pointer !important;
        min-height: 36px !important;
    }
    #daily-day-selector .Select-value {
        background: transparent !important;
        background-color: transparent !important;
        border: none !important;
    }
    #daily-day-selector .Select-value-label {
        color: #f0ede4 !important;
        font-weight: 600 !important;
        font-size: 13px !important;
    }
    #daily-day-selector .Select-placeholder {
        color: #5c6478 !important;
    }
    #daily-day-selector .Select-input,
    #daily-day-selector .Select-input > input,
    #daily-day-selector input {
        color: #1a1a2e !important;
        background: transparent !important;
    }
    #daily-day-selector .Select-multi-value-wrapper {
        background: transparent !important;
    }
    #daily-day-selector .Select-arrow-zone .Select-arrow {
        border-color: #7a7060 transparent transparent !important;
    }
    /* WHITE menu & options */
    #daily-day-selector .Select-menu-outer {
        background-color: #ffffff !important;
        background: #ffffff !important;
        border: 1px solid #d0d0d0 !important;
        border-radius: 10px !important;
        z-index: 99999 !important;
        box-shadow: 0 6px 24px rgba(0   ,0,0,0.18) !important;
        margin-top: 4px !important;
        overflow: hidden !important;
    }
    #daily-day-selector .Select-menu {
        background-color: #ffffff !important;
        background: #ffffff !important;
        max-height: 300px !important;
    }
    #daily-day-selector .Select-option,
    #daily-day-selector .VirtualizedSelectOption {
        background-color: #ffffff !important;
        background: #ffffff !important;
        color: #1a1a2e !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        padding: 11px 16px !important;
        border-bottom: 1px solid #f0f0f0 !important;
        cursor: pointer !important;
    }
    #daily-day-selector .VirtualizedSelectFocusedOption,
    #daily-day-selector .Select-option.is-focused,
    #daily-day-selector .Select-option:hover,
    #daily-day-selector .VirtualizedSelectOption:hover {
        background-color: #f3f0ff !important;
        background: #f3f0ff !important;
        color: #5b21b6 !important;
    }
    #daily-day-selector .Select-option.is-selected {
        background-color: #f3f0ff !important;
        background: #f3f0ff !important;
        color: #5b21b6 !important;
        font-weight: 600 !important;
    }
    #daily-day-selector .Select-noresults {
        background: #ffffff !important;
        color: #999 !important;
    }
    /* ARIA role targets (for portaled menus) */
    #daily-day-selector div[role="listbox"],
    #daily-day-selector div[role="listbox"] * {
        background-color: #ffffff !important;
        background: #ffffff !important;
    }
    #daily-day-selector div[role="option"] {
        background-color: #ffffff !important;
        background: #ffffff !important;
        color: #1a1a2e !important;
        font-size: 14px !important;
        padding: 11px 16px !important;
    }
    #daily-day-selector div[role="option"]:hover,
    #daily-day-selector div[role="option"][class*="isFocused"] {
        background-color: #f3f0ff !important;
        background: #f3f0ff !important;
        color: #5b21b6 !important;
    }
    #daily-day-selector div[role="option"][aria-selected="true"] {
        background-color: #f3f0ff !important;
        background: #f3f0ff !important;
        color: #5b21b6 !important;
        font-weight: 600 !important;
    }
    /* Scrollbar inside dropdown */
    #daily-day-selector .Select-menu::-webkit-scrollbar {
        width: 6px !important;
    }
    #daily-day-selector .Select-menu::-webkit-scrollbar-track {
        background: #f5f5f5 !important;
    }
    #daily-day-selector .Select-menu::-webkit-scrollbar-thumb {
        background: #ccc !important;
        border-radius: 10px !important;
    }
    #daily-day-selector .Select-menu-outer::-webkit-scrollbar {
        width: 6px !important;
    }
    #daily-day-selector .Select-menu-outer::-webkit-scrollbar-track {
        background: #f5f5f5 !important;
    }
    #daily-day-selector .Select-menu-outer::-webkit-scrollbar-thumb {
        background: #ccc !important;
        border-radius: 10px !important;
    }
</style>
</head>
<body>
{%app_entry%}
<footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>
'''

# ─── Load symbols configuration at startup ───
_symbols_config = load_symbols_config()
_all_symbols = _symbols_config.get('_symbol_names', [])
_active_config = load_active_config()
_current_mode = _active_config.get('mode', 'demo')


def _build_tabs(symbols):
    """Build the dcc.Tabs component for the given symbol list"""
    _TAB_STYLE = {
        'background': 'transparent',
        'color': COLORS['text_dim'],
        'border': 'none',
        'borderBottom': '2px solid transparent',
        'padding': '14px 28px',
        'fontSize': '12px',
        'fontWeight': '600',
        'letterSpacing': '1.5px',
        'transition': 'all 0.3s ease',
        'fontFamily': "'Inter', sans-serif",
    }
    _TAB_SELECTED = {
        'background': 'transparent',
        'color': COLORS['text'],
        'border': 'none',
        'borderBottom': f'2px solid {COLORS["tab_active"]}',
        'padding': '14px 28px',
        'fontSize': '12px',
        'fontWeight': '700',
        'letterSpacing': '1.5px',
        'fontFamily': "'Inter', sans-serif",
        'boxShadow': f'0 2px 12px {COLORS["accent_glow"]}',
    }
    if not symbols:
        return dcc.Tabs(
            id='symbol-tabs',
            value='',
            children=[],
            style={'display': 'none'},
        )
    return dcc.Tabs(
        id='symbol-tabs',
        value=symbols[0],
        children=[
            dcc.Tab(label=s, value=s, style=_TAB_STYLE, selected_style=_TAB_SELECTED)
            for s in symbols
        ],
        style={'borderBottom': f'1px solid {COLORS["divider"]}', 'background': COLORS['tab_bg']},
    )


app.layout = html.Div([
    # Auto-refresh
    dcc.Interval(id='refresh-interval', interval=REFRESH_INTERVAL, n_intervals=0),
    # Cache to skip redundant DOM rebuilds
    dcc.Store(id='data-hash', data=''),
    # Persist selected daily date across refreshes
    dcc.Store(id='selected-daily-date', data=None),

    # ── Top gradient accent line — divine gold/blue ──
    html.Div(className='gradient-bar'),

    # ── Header — Alcadeias Mascot + Branding ──
    html.Div([
        html.Div([
            # Alcadeias, Lord of Spirits — mascot image
            html.Div(
                html.Img(
                    src=_MASCOT_B64,
                    style={
                        'width': '64px', 'height': '64px',
                        'objectFit': 'contain',
                        'display': 'block',
                        'filter': 'drop-shadow(0 0 8px rgba(212,168,67,0.35))',
                    },
                ),
                className='mascot-container',
                style={
                    'width': '68px', 'height': '68px',
                    'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center',
                    'background': 'radial-gradient(circle, rgba(212,168,67,0.08) 0%, rgba(74,142,204,0.04) 50%, transparent 75%)',
                    'marginRight': '14px', 'flexShrink': '0',
                },
            ),
            html.Div([
                html.Span('ALCADEIAS', style={
                    'fontSize': '19px', 'fontWeight': '800', 'letterSpacing': '3.5px',
                    'background': 'linear-gradient(135deg, #f0e6c0, #d4a843, #4a8ecc)',
                    'WebkitBackgroundClip': 'text',
                    'WebkitTextFillColor': 'transparent',
                }),
                html.Div('Lord of Spirits · Trading Dashboard', style={
                    'fontSize': '9px', 'color': '#7a7060',
                    'letterSpacing': '2px', 'textTransform': 'uppercase',
                    'marginTop': '2px', 'fontWeight': '500',
                }),
            ]),
        ], style={'display': 'flex', 'alignItems': 'center'}),
        html.Div(id='account-info', style={
            'display': 'flex', 'gap': '24px', 'alignItems': 'center',
        }),
        html.Div(id='header-time', style={
            'fontSize': '11px', 'color': '#7a7060',
            'fontFamily': "'JetBrains Mono', monospace",
            'fontWeight': '400',
        }),
    ], style={
        'display': 'flex',
        'justifyContent': 'space-between',
        'alignItems': 'center',
        'padding': '12px 32px',
        'background': 'linear-gradient(180deg, rgba(6,11,24,0.97) 0%, rgba(10,16,37,0.95) 100%)',
        'backdropFilter': 'blur(20px)',
        'WebkitBackdropFilter': 'blur(20px)',
        'borderBottom': f'1px solid {COLORS["divider"]}',
        'color': COLORS['text'],
    }),

    # ── Control Bar: Mode Badge (read-only) + Symbol Selector ──
    html.Div([
        # Left: Mode badge (read-only — set by start_job.bat)
        html.Div([
            html.Span('MODE', style={
                'fontSize': '9px', 'fontWeight': '600', 'color': COLORS['text_dim'],
                'letterSpacing': '1.5px', 'marginRight': '12px',
            }),
            html.Span(_current_mode.upper(), id='mode-indicator', style={
                'fontSize': '11px', 'fontWeight': '700', 'letterSpacing': '1.2px',
                'color': COLORS['buy'] if _current_mode == 'demo' else COLORS['sell'],
                'background': f'{COLORS["buy"] if _current_mode == "demo" else COLORS["sell"]}18',
                'padding': '4px 14px', 'borderRadius': '8px',
                'border': f'1px solid {COLORS["buy"] if _current_mode == "demo" else COLORS["sell"]}33',
            }),
        ], style={'display': 'flex', 'alignItems': 'center'}),

        # Right: Symbols badge (read-only — set by symbols.json)
        html.Div([
            html.Span('SYMBOLS', style={
                'fontSize': '9px', 'fontWeight': '600', 'color': COLORS['text_dim'],
                'letterSpacing': '1.5px', 'marginRight': '12px', 'flexShrink': '0',
                'whiteSpace': 'nowrap',
            }),
            html.Span(
                ', '.join(_all_symbols),
                style={
                    'fontSize': '11px', 'fontWeight': '600', 'letterSpacing': '0.5px',
                    'color': COLORS['text'],
                    'background': 'rgba(192, 168, 100, 0.10)',
                    'padding': '6px 16px', 'borderRadius': '8px',
                    'border': '1px solid rgba(192, 168, 100, 0.25)',
                },
            ),
        ], style={'display': 'flex', 'alignItems': 'center'}),
    ], style={
        'display': 'flex',
        'justifyContent': 'space-between',
        'alignItems': 'center',
        'padding': '10px 32px',
        'background': COLORS['bg_secondary'],
        'borderBottom': f'1px solid {COLORS["divider"]}',
        'gap': '24px',
    }),

    # ── Tabs (always shows all symbols from symbols.json) ──
    html.Div(
        _build_tabs(_all_symbols),
        id='tabs-container',
        style={'padding': '0 32px', 'background': COLORS['tab_bg']},
    ),

    # ── Content ──
    html.Div(id='tab-content', style={
        'padding': '28px 32px 48px 32px',
        'maxWidth': '1280px',
        'margin': '0 auto',
    }),

    # ── Footer — angelic divider ──
    html.Div([
        html.Div(style={
            'height': '1px',
            'background': f'linear-gradient(90deg, transparent, rgba(212,168,67,0.18), rgba(74,142,204,0.12), transparent)',
            'marginBottom': '16px',
        }),
        html.Div([
            html.Span('✦', style={'color': '#d4a843', 'fontSize': '10px', 'marginRight': '8px', 'opacity': '0.5'}),
            html.Span('Alcadeias · Lord of Spirits', style={
                'fontSize': '10px',
                'background': 'linear-gradient(90deg, #d4a843, #4a8ecc)',
                'WebkitBackgroundClip': 'text',
                'WebkitTextFillColor': 'transparent',
                'letterSpacing': '2.5px',
                'textTransform': 'uppercase',
                'fontWeight': '600',
            }),
            html.Span('✦', style={'color': '#4a8ecc', 'fontSize': '10px', 'marginLeft': '8px', 'opacity': '0.5'}),
        ], style={
            'textAlign': 'center',
            'paddingBottom': '18px',
            'display': 'flex', 'justifyContent': 'center', 'alignItems': 'center',
        }),
    ], style={'padding': '0 32px'}),

], style={
    'background': COLORS['bg'],
    'minHeight': '100vh',
    'fontFamily': "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    'color': COLORS['text'],
})


# ─── Daily Day Selector Callback ───
@app.callback(
    [Output('daily-metrics-container', 'children'),
     Output('daily-chart-container', 'children'),
     Output('selected-daily-date', 'data')],
    [Input('daily-day-selector', 'value'),
     Input('symbol-tabs', 'value')],
    prevent_initial_call=True,
)
def update_daily_day(selected_date, selected_symbol):
    """Update daily trade chart and metrics when a different day is selected."""
    if not selected_symbol:
        return dash.no_update, dash.no_update, dash.no_update

    today_str = datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')
    is_today = (not selected_date) or (selected_date == today_str)

    if is_today:
        daily_data = load_daily_trade_data(selected_symbol)
    else:
        daily_data = load_daily_trade_data_for_date(selected_symbol, selected_date)

    historical = load_historical_summary(selected_symbol)

    deals = daily_data.get('deals', []) if daily_data else []
    sym_total = daily_data.get('total_profit', 0) if daily_data else 0
    sym_avg = daily_data.get('avg_profit', 0) if daily_data else 0
    sym_count = daily_data.get('deal_count', 0) if daily_data else 0
    hist_total = historical.get('total_profit', 0) if historical else 0
    hist_count = historical.get('total_deals', 0) if historical else 0

    all_sym_pl, all_sym_deals = load_today_all_symbols_pl()

    # Date label for the metrics cards
    if is_today:
        day_label = 'Today'
    else:
        try:
            d = datetime.strptime(selected_date, '%Y-%m-%d')
            day_label = d.strftime('%d %b')
        except (ValueError, TypeError):
            day_label = selected_date

    metrics_row = html.Div([
        make_metric_card(
            f'{selected_symbol} P/L {day_label}',
            f'${sym_total:,.2f}',
            COLORS['positive'] if sym_total >= 0 else COLORS['negative'],
            f'{sym_count} deals', icon='📊',
        ),
        make_metric_card(
            f'{selected_symbol} Avg Profit',
            f'${sym_avg:,.2f}',
            COLORS['positive'] if sym_avg >= 0 else COLORS['negative'],
            'per deal', icon='📉',
        ),
        make_metric_card(
            f'{selected_symbol} Lifetime P/L',
            f'${hist_total:,.2f}',
            COLORS['positive'] if hist_total >= 0 else COLORS['negative'],
            f'{hist_count} deals (10y)', icon='🏦',
        ),
        make_metric_card(
            'All Symbols Today',
            f'${all_sym_pl:,.2f}',
            COLORS['positive'] if all_sym_pl >= 0 else COLORS['negative'],
            f'{all_sym_deals} deals total', icon='🌐',
        ),
    ], style={'display': 'flex', 'gap': '12px', 'flexWrap': 'wrap', 'marginBottom': '16px'})

    chart = _build_daily_chart(deals)

    return [metrics_row], [chart], selected_date


# ─── Main Content Callback ───
@app.callback(
    [Output('tab-content', 'children'),
     Output('account-info', 'children'),
     Output('header-time', 'children'),
     Output('data-hash', 'data'),
     Output('mode-indicator', 'children'),
     Output('mode-indicator', 'style')],
    [Input('symbol-tabs', 'value'),
     Input('refresh-interval', 'n_intervals')],
    [dash.State('data-hash', 'data'),
     dash.State('selected-daily-date', 'data')],
)
def update_content(selected_symbol, n, prev_hash, stored_date):
    """Single callback: refreshes content only when data changes or tab switches"""
    import hashlib

    # Read current mode from active_config (bot writes this)
    _cfg = load_active_config()
    _mode = _cfg.get('mode', 'demo')
    _mode_color = COLORS['buy'] if _mode == 'demo' else COLORS['sell']
    _mode_style = {
        'fontSize': '11px', 'fontWeight': '700', 'letterSpacing': '1.2px',
        'color': _mode_color,
        'background': f'{_mode_color}18',
        'padding': '4px 14px', 'borderRadius': '8px',
        'border': f'1px solid {_mode_color}33',
    }

    if not selected_symbol:
        return html.Div([
            html.Div('⚠', style={'fontSize': '48px', 'marginBottom': '12px', 'opacity': '0.4'}),
            html.Div('No symbols configured', style={
                'color': COLORS['text_dim'], 'fontSize': '16px',
            }),
        ], style={
            'textAlign': 'center', 'marginTop': '120px',
        }), html.Div(), '', '', _mode.upper(), _mode_style

    # Load raw data to check if anything changed
    symbol_data = load_symbol_data(selected_symbol)
    account = load_account_data()
    daily = load_daily_trade_data(selected_symbol)
    historical = load_historical_summary(selected_symbol)
    strategy_log = load_strategy_log(selected_symbol)

    # Build a quick hash of the data to detect changes
    raw = json.dumps({'s': symbol_data, 'a': account, 'd': daily, 'h': historical, 'l': strategy_log},
                     default=str, sort_keys=True)
    current_hash = hashlib.md5(raw.encode()).hexdigest()

    # Check if this is a tab switch or data actually changed
    triggered = callback_context.triggered[0]['prop_id'] if callback_context.triggered else ''
    is_tab_switch = 'symbol-tabs' in triggered

    if not is_tab_switch and current_hash == prev_hash:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, _mode.upper(), _mode_style

    # Build account info display
    balance = account.get('balance', 0)
    equity = account.get('equity', 0)
    margin = account.get('margin', 0)
    drawdown = account.get('drawdown', 0)

    equity_color = COLORS['positive'] if equity >= balance else COLORS['negative']
    drawdown_color = COLORS['negative'] if drawdown > 5 else COLORS['text_secondary']

    def account_stat(label, val, color=COLORS['text']):
        return html.Div([
            html.Div(label, style={
                'fontSize': '9px', 'color': COLORS['text_dim'],
                'textTransform': 'uppercase', 'letterSpacing': '1px',
                'fontWeight': '500',
            }),
            html.Div(val, style={
                'fontSize': '14px', 'fontWeight': '700', 'color': color,
                'fontFamily': "'JetBrains Mono', monospace",
                'letterSpacing': '-0.3px',
            }),
        ], style={'textAlign': 'right'})

    account_display = html.Div([
        account_stat('Balance', f'${balance:,.2f}'),
        html.Div(style={
            'width': '1px', 'height': '28px',
            'background': COLORS['divider'],
        }),
        account_stat('Equity', f'${equity:,.2f}', equity_color),
        html.Div(style={
            'width': '1px', 'height': '28px',
            'background': COLORS['divider'],
        }),
        account_stat('Margin', f'${margin:,.2f}'),
        html.Div(style={
            'width': '1px', 'height': '28px',
            'background': COLORS['divider'],
        }),
        account_stat('Drawdown', f'{drawdown:.2f}%', drawdown_color),
    ], style={'display': 'flex', 'gap': '20px', 'alignItems': 'center'})

    # On tab switch reset to today, otherwise preserve selected date
    active_date = None if is_tab_switch else stored_date
    content = build_symbol_tab_content(selected_symbol, selected_date=active_date)

    # Use server time from symbol data if available
    server_time_str = symbol_data.get('server_time') if symbol_data else None
    if server_time_str:
        try:
            server_dt = datetime.fromisoformat(server_time_str)
            time_display = server_dt.strftime('Server  %d %b %Y  •  %H:%M:%S UTC')
        except (ValueError, TypeError):
            time_display = datetime.now().strftime('Refresh  %H:%M:%S')
    else:
        time_display = datetime.now().strftime('Refresh  %H:%M:%S')

    return content, account_display, time_display, current_hash, _mode.upper(), _mode_style


if __name__ == '__main__':
    app.run(debug=True, host=DASHBOARD_HOST, port=DASHBOARD_PORT)
