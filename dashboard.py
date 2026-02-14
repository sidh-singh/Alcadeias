import json
import os
import glob
import re
from datetime import datetime, timezone

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
    """Load all available symbols from symbols.json"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'symbols.json')
        with open(config_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {'symbols': []}


def load_active_config():
    """Load active configuration (mode + per-mode selected symbols)"""
    try:
        with open(ACTIVE_CONFIG_PATH, 'r') as f:
            cfg = json.load(f)
        # Migrate old format (single active_symbols list) → per-mode lists
        if 'active_symbols' in cfg and 'demo_symbols' not in cfg:
            cfg['demo_symbols'] = cfg.pop('active_symbols')
            cfg.setdefault('live_symbols', cfg['demo_symbols'][:])
            save_active_config(cfg)
        return cfg
    except (FileNotFoundError, json.JSONDecodeError):
        symbols_cfg = load_symbols_config()
        all_syms = symbols_cfg.get('symbols', [])
        return {
            'mode': 'demo',
            'demo_symbols': all_syms[:],
            'live_symbols': all_syms[:],
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


def _crossover_badge(val):
    """Compact colored badge for a crossover value — Ballom style."""
    cfg = {
        3:  ('🔥 +3', '#009d7a', 'rgba(0, 157, 122, 0.12)'),
        2:  ('⚡ +2', '#00d2a0', 'rgba(0, 210, 160, 0.12)'),
        1:  ('💨 +1', '#4de8c8', 'rgba(77, 232, 200, 0.12)'),
        -1: ('💨 −1', '#ee7b6e', 'rgba(238, 123, 110, 0.12)'),
        -2: ('⚡ −2', '#e74c3c', 'rgba(231, 76, 60, 0.12)'),
        -3: ('🔥 −3', '#c0392b', 'rgba(192, 57, 43, 0.12)'),
    }
    emoji_txt, color, bg = cfg.get(val, (str(val), '#888', 'rgba(255,255,255,0.04)'))
    return html.Span(emoji_txt, style={
        'color': color, 'background': bg,
        'padding': '3px 10px', 'borderRadius': '10px',
        'fontSize': '0.78rem', 'fontWeight': '600',
        'whiteSpace': 'nowrap',
        'fontFamily': "'JetBrains Mono', monospace",
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


def _cross_dots(cross_list, max_items=7):
    """Render crossover values as uniform circle dots with green/red light-medium-dark shading."""
    green_map = {1: '#4de8c8', 2: '#00d2a0', 3: '#009d7a'}
    red_map   = {1: '#ee7b6e', 2: '#e74c3c', 3: '#c0392b'}
    dots = []
    for i, v in enumerate(cross_list[:max_items]):
        if v > 0:
            c = green_map.get(v, '#81c784')
        elif v < 0:
            c = red_map.get(abs(v), '#e57373')
        else:
            c = '#555'
        opacity = max(0.35, 1.0 - (i * 0.09))
        dots.append(html.Span(style={
            'display': 'inline-block', 'width': '10px', 'height': '10px',
            'borderRadius': '50%', 'background': c,
            'marginRight': '3px', 'opacity': str(opacity),
        }))
    return html.Div(dots, style={'display': 'inline-flex', 'alignItems': 'center'})


def _cross_power_bar(cross_list, max_items=7):
    """Power bar for crossover — each segment colored by its value's green/red shade."""
    green_map = {1: '#4de8c8', 2: '#00d2a0', 3: '#009d7a'}
    red_map   = {1: '#ee7b6e', 2: '#e74c3c', 3: '#c0392b'}
    bull_count = sum(1 for v in cross_list[:max_items] if v > 0)
    segs = []
    for i in range(max_items):
        if i < len(cross_list):
            v = cross_list[i]
            if v > 0:
                c = green_map.get(v, '#81c784')
            elif v < 0:
                c = red_map.get(abs(v), '#e57373')
            else:
                c = 'rgba(255,255,255,0.06)'
        else:
            c = 'rgba(255,255,255,0.06)'
        segs.append(html.Span(style={
            'display': 'inline-block', 'width': '8px', 'height': '16px',
            'borderRadius': '2px', 'background': c, 'marginRight': '2px',
        }))
    p_color = '#00d2a0' if bull_count >= 5 else '#f39c12' if bull_count >= 3 else '#e74c3c'
    return html.Div([
        *segs,
        html.Span(f' {bull_count}', style={
            'fontSize': '0.75rem', 'fontWeight': '700', 'marginLeft': '4px',
            'color': p_color if bull_count > 0 else COLORS['text_dim'],
            'fontFamily': "'JetBrains Mono', monospace",
        }),
    ], style={'display': 'inline-flex', 'alignItems': 'center'})


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


def _build_gap_row(gap_pct, gap_range):
    """Build the SHA gap% row with range indicator."""
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

    return html.Div(
        style={
            'display': 'grid',
            'gridTemplateColumns': '64px 1fr 1fr',
            'gap': '8px', 'alignItems': 'center',
            'padding': '8px 0',
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
    )


def build_sha_analysis_panel(symbol, analysis, last_updated=''):
    """Build clean SHA analysis card — Ballom-inspired grid layout."""
    sha_list = analysis.get('sha_power_list', [])
    price_list = analysis.get('price_power_list', [])
    crossover = analysis.get('crossover', [])
    sha_buy = analysis.get('sha_buy_strength', 0)
    sha_sell = analysis.get('sha_sell_strength', 0)
    price_buy = analysis.get('price_buy_strength', 0)
    price_sell = analysis.get('price_sell_strength', 0)

    # Trend SHA data
    trend_list = analysis.get('sha_trend_power_list', [])
    trend_buy = analysis.get('sha_trend_buy_strength', 0)
    trend_sell = analysis.get('sha_trend_sell_strength', 0)

    # Gap% data
    gap_pct = analysis.get('current_gap_pct', 0)
    gap_range_val = analysis.get('gap_range', [0.1, 0.30])

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

    # Crossover row — same 3-column grid as SHA / Price
    cross_row = html.Div(
        style={
            'display': 'grid',
            'gridTemplateColumns': '64px 1fr 1fr',
            'gap': '8px', 'alignItems': 'center',
            'padding': '8px 0',
        },
        children=[
            html.Span('🔀 Cross', style={
                'fontWeight': '700', 'fontSize': '0.82rem', 'color': '#f39c12',
            }),
            _cross_power_bar(crossover),
            _cross_dots(crossover),
        ],
    )

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
            # ── Signal + Trend + Price + Cross + Gap rows ──
            html.Div(style={'padding': '0 16px 10px'}, children=[
                _signal_row('Signal', '🔵', '#5dade2', sha_buy, sha_list),
                row_divider,
                _signal_row('Trend', '🟣', '#a78bfa', trend_buy, trend_list),
                row_divider,
                _signal_row('Price', '🔴', '#e74c3c', price_buy, price_list),
                row_divider,
                cross_row,
                row_divider,
                _build_gap_row(gap_pct, gap_range_val),
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
                    # Crossover intensity legend
                    html.Span('Cross:', style={
                        'fontSize': '0.6rem', 'color': COLORS['text_dim'],
                        'fontWeight': '600', 'letterSpacing': '0.5px',
                    }),
                    html.Div([
                        html.Span(style={
                            'display': 'inline-block', 'width': '8px', 'height': '8px',
                            'borderRadius': '50%', 'background': '#4de8c8',
                            'marginRight': '3px',
                        }),
                        html.Span('Light', style={
                            'fontSize': '0.6rem', 'color': COLORS['text_dim'],
                            'marginRight': '8px',
                        }),
                        html.Span(style={
                            'display': 'inline-block', 'width': '8px', 'height': '8px',
                            'borderRadius': '50%', 'background': '#00d2a0',
                            'marginRight': '3px',
                        }),
                        html.Span('Medium', style={
                            'fontSize': '0.6rem', 'color': COLORS['text_dim'],
                            'marginRight': '8px',
                        }),
                        html.Span(style={
                            'display': 'inline-block', 'width': '8px', 'height': '8px',
                            'borderRadius': '50%', 'background': '#009d7a',
                            'marginRight': '3px',
                        }),
                        html.Span('Strong', style={
                            'fontSize': '0.6rem', 'color': COLORS['text_dim'],
                        }),
                    ], style={'display': 'inline-flex', 'alignItems': 'center'}),
                    html.Div([
                        html.Span(style={
                            'display': 'inline-block', 'width': '8px', 'height': '8px',
                            'borderRadius': '50%', 'background': '#ee7b6e',
                            'marginRight': '3px',
                        }),
                        html.Span('Light', style={
                            'fontSize': '0.6rem', 'color': COLORS['text_dim'],
                            'marginRight': '8px',
                        }),
                        html.Span(style={
                            'display': 'inline-block', 'width': '8px', 'height': '8px',
                            'borderRadius': '50%', 'background': '#e74c3c',
                            'marginRight': '3px',
                        }),
                        html.Span('Medium', style={
                            'fontSize': '0.6rem', 'color': COLORS['text_dim'],
                            'marginRight': '8px',
                        }),
                        html.Span(style={
                            'display': 'inline-block', 'width': '8px', 'height': '8px',
                            'borderRadius': '50%', 'background': '#c0392b',
                            'marginRight': '3px',
                        }),
                        html.Span('Strong', style={
                            'fontSize': '0.6rem', 'color': COLORS['text_dim'],
                        }),
                    ], style={'display': 'inline-flex', 'alignItems': 'center'}),
                ],
            ),
            # ── Footer timestamp ──
            html.Div(last_updated, style={
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


def build_daily_trades_section(symbol):
    """Build daily trades chart and metrics for a symbol — premium version"""
    daily_data = load_daily_trade_data(symbol)
    historical = load_historical_summary(symbol)

    today_deals = []
    if daily_data:
        today_deals = daily_data.get('deals', [])

    sym_total = daily_data.get('total_profit', 0) if daily_data else 0
    sym_avg = daily_data.get('avg_profit', 0) if daily_data else 0
    sym_count = daily_data.get('deal_count', 0) if daily_data else 0
    hist_total = historical.get('total_profit', 0) if historical else 0
    hist_count = historical.get('total_deals', 0) if historical else 0

    all_sym_pl, all_sym_deals = load_today_all_symbols_pl()

    metrics_row = html.Div([
        make_metric_card(
            f'{symbol} P/L Today',
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

    if today_deals:
        sorted_deals = sorted(today_deals, key=lambda d: d.get('time', ''))

        labels = []
        profits = []
        volumes = []
        colors = []
        hover_texts = []
        cumulative_profit = 0
        cum_profits = []

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
                f"Cumulative: ${cumulative_profit:.2f}"
            )

        fig = make_subplots(
            rows=2, cols=1,
            row_heights=[0.55, 0.45],
            vertical_spacing=0.14,
            subplot_titles=['Profit/Loss per Deal', 'Cumulative P/L'],
        )

        n_deals = len(sorted_deals)
        show_bar_text = n_deals <= GRAPH_TEXT_LABEL_THRESHOLD
        show_cum_text = n_deals <= GRAPH_CUM_LABEL_THRESHOLD

        fig.add_trace(go.Bar(
            x=labels, y=profits,
            marker=dict(
                color=colors,
                line=dict(width=0),
            ),
            text=[f'${p:.2f}' for p in profits] if show_bar_text else None,
            textposition='outside' if show_bar_text else None,
            textfont=dict(size=10, color=COLORS['text_secondary'], family="'Inter', sans-serif") if show_bar_text else None,
            hovertext=hover_texts,
            hoverinfo='text',
            showlegend=False,
        ), row=1, col=1)

        cum_color = COLORS['positive'] if cumulative_profit >= 0 else COLORS['negative']
        # Convert hex to rgba for fillcolor (Plotly doesn't support 8-digit hex)
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
        ), row=2, col=1)

        fig.add_hline(y=0, line_dash='dot', line_color=COLORS['text_muted'],
                       opacity=0.5, row=2, col=1)

        fig.update_layout(
            height=420,
            margin=dict(l=50, r=20, t=30, b=30),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color=COLORS['text_secondary'], size=11, family="'Inter', sans-serif"),
        )
        # Reduce x-axis tick density for many deals
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

        chart = dcc.Graph(
            figure=fig,
            config={'displayModeBar': False},
            style={'height': '420px'},
        )
    else:
        chart = html.Div([
            html.Div('📭', style={'fontSize': '32px', 'marginBottom': '8px', 'opacity': '0.5'}),
            html.Div('No closed deals today for this symbol', style={
                'color': COLORS['text_dim'], 'fontSize': '13px',
            }),
        ], style={
            'textAlign': 'center', 'padding': '48px 0',
        })

    return html.Div([
        html.Div([
            html.Span('📈', style={'fontSize': '14px'}),
            html.Span('Daily Trade Log', style={**SECTION_TITLE_STYLE, 'fontSize': '13px'}),
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '8px', 'marginBottom': '10px'}),
        metrics_row,
        html.Div([chart], style={
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


def build_symbol_tab_content(symbol):
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
        build_daily_trades_section(symbol),

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
)

app.css.append_css({'external_url': ''})
app.index_string = '''<!DOCTYPE html>
<html>
<head>
{%metas%}
<title>{%title%}</title>
{%favicon%}
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

    /* === Dark Dropdown — Alcadeias Gold Theme === */
    .Select-control {
        background-color: #0c1328 !important;
        border-color: rgba(192, 168, 100, 0.2) !important;
        color: #f0ede4 !important;
    }
    .Select-menu-outer {
        background-color: #0c1328 !important;
        border-color: rgba(192, 168, 100, 0.2) !important;
        z-index: 999 !important;
    }
    .Select-option,
    .VirtualizedSelectOption {
        background-color: #0c1328 !important;
        color: #f0ede4 !important;
    }
    .VirtualizedSelectFocusedOption,
    .Select-option.is-focused {
        background-color: rgba(212, 168, 67, 0.15) !important;
    }
    .Select-value {
        background-color: #1a2540 !important;
        border-color: rgba(212, 168, 67, 0.35) !important;
        color: #f0ede4 !important;
    }
    .Select-value-label {
        color: #f0ede4 !important;
        font-weight: 600 !important;
    }
    .Select-input input {
        color: #f0ede4 !important;
    }
    .Select-placeholder {
        color: #5c6478 !important;
    }
    .Select-arrow-zone .Select-arrow {
        border-color: #5c6478 transparent transparent !important;
    }
    .Select-clear-zone {
        color: #5c6478 !important;
    }
    .Select-multi-value-wrapper .Select-value .Select-value-icon {
        border-right-color: rgba(212, 168, 67, 0.35) !important;
        color: #b8b0a0 !important;
    }
    .Select-multi-value-wrapper .Select-value .Select-value-icon:hover {
        color: #e05555 !important;
        background-color: rgba(224, 85, 85, 0.15) !important;
    }
    .Select-noresults {
        background-color: #0c1328 !important;
        color: #5c6478 !important;
    }
    /* Dash-specific dropdown overrides */
    .dash-dropdown .Select--multi .Select-value {
        background-color: #1a2540 !important;
        border: 1px solid rgba(212, 168, 67, 0.35) !important;
        color: #f0ede4 !important;
    }
    .dash-dropdown .Select-control {
        background-color: #0a0f20 !important;
        border: 1px solid rgba(192, 168, 100, 0.22) !important;
    }
    .dash-dropdown .Select-menu-outer {
        background-color: #0c1328 !important;
    }
    .dash-dropdown .Select-option {
        background-color: #0c1328 !important;
        color: #f0ede4 !important;
    }
    .dash-dropdown .Select-option:hover,
    .dash-dropdown .Select-option.is-focused {
        background-color: #1a2540 !important;
    }

    /* === Mode Toggle Buttons === */
    .mode-btn {
        border: none;
        padding: 6px 18px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.2px;
        cursor: pointer;
        border-radius: 8px;
        transition: all 0.25s ease;
        font-family: 'Inter', sans-serif;
        outline: none;
    }
    .mode-btn:hover {
        filter: brightness(1.15);
    }

    /* === Mascot container glow === */
    .mascot-container {
        animation: divinePulse 3s ease-in-out infinite;
        border-radius: 14px;
        display: flex;
        align-items: center;
        justify-content: center;
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
_all_symbols = _symbols_config.get('symbols', [])
_active_config = load_active_config()
_current_mode = _active_config.get('mode', 'demo')
# Per-mode symbol lists
_demo_symbols = _active_config.get('demo_symbols', _all_symbols[:])
_live_symbols = _active_config.get('live_symbols', _all_symbols[:])
_demo_symbols = [s for s in _demo_symbols if s in _all_symbols] or _all_symbols[:]
_live_symbols = [s for s in _live_symbols if s in _all_symbols] or _all_symbols[:]
_active_symbols = _demo_symbols if _current_mode == 'demo' else _live_symbols


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
        return html.Div('No symbols selected', style={
            'color': COLORS['text_dim'], 'fontSize': '13px',
            'padding': '16px 32px', 'textAlign': 'center',
            'background': COLORS['tab_bg'],
        })
    return dcc.Tabs(
        id='symbol-tabs',
        value=symbols[0],
        children=[
            dcc.Tab(label=s, value=s, style=_TAB_STYLE, selected_style=_TAB_SELECTED)
            for s in symbols
        ],
        style={'borderBottom': f'1px solid {COLORS["divider"]}', 'background': COLORS['tab_bg']},
    )


def _mode_btn_style(mode, is_active):
    """Return inline style dict for a mode toggle button"""
    if mode == 'demo':
        active_bg, active_glow = COLORS['buy'], COLORS['buy_glow']
    else:
        active_bg, active_glow = COLORS['sell'], COLORS['sell_glow']
    if is_active:
        return {
            'background': active_bg, 'color': '#fff',
            'boxShadow': f'0 0 14px {active_glow}',
        }
    return {
        'background': 'transparent', 'color': COLORS['text_dim'],
        'boxShadow': 'none',
    }


app.layout = html.Div([
    # Auto-refresh
    dcc.Interval(id='refresh-interval', interval=REFRESH_INTERVAL, n_intervals=0),
    # Cache to skip redundant DOM rebuilds
    dcc.Store(id='data-hash', data=''),

    # ── Top gradient accent line — divine gold/blue ──
    html.Div(className='gradient-bar'),

    # ── Header — Alcadeias Mascot + Branding ──
    html.Div([
        html.Div([
            # SVG Mascot — Alcadeias Lord of Spirits (12500-power Angel Command)
            html.Div(
                dash.html.Iframe(
                    srcDoc='''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="54" height="54">
  <defs>
    <linearGradient id="gArmor" x1="0" y1="0" x2="0.5" y2="1">
      <stop offset="0%" stop-color="#f5ecd0"/>
      <stop offset="35%" stop-color="#d4a843"/>
      <stop offset="70%" stop-color="#b8922e"/>
      <stop offset="100%" stop-color="#4a6ea0"/>
    </linearGradient>
    <linearGradient id="gWingL" x1="1" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#f0e6c0"/>
      <stop offset="30%" stop-color="#d4a843"/>
      <stop offset="60%" stop-color="#4a8ecc"/>
      <stop offset="100%" stop-color="#2a5a8a"/>
    </linearGradient>
    <linearGradient id="gWingR" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#f0e6c0"/>
      <stop offset="30%" stop-color="#d4a843"/>
      <stop offset="60%" stop-color="#4a8ecc"/>
      <stop offset="100%" stop-color="#2a5a8a"/>
    </linearGradient>
    <linearGradient id="gHelm" x1="0.5" y1="0" x2="0.5" y2="1">
      <stop offset="0%" stop-color="#4a8ecc"/>
      <stop offset="50%" stop-color="#2a5a8a"/>
      <stop offset="100%" stop-color="#1a3a5a"/>
    </linearGradient>
    <radialGradient id="gOrb" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="40%" stop-color="#fffbe6"/>
      <stop offset="100%" stop-color="#d4a843"/>
    </radialGradient>
    <filter id="glow"><feGaussianBlur stdDeviation="1.5" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="aura"><feGaussianBlur stdDeviation="3" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>
  <!-- WINGS — 5 blade-feather spikes each side -->
  <!-- Left wing blades -->
  <path d="M40 48 L6 10 L16 30 L26 42 Z" fill="url(#gWingL)" opacity="0.92"/>
  <path d="M38 52 L2 22 L12 38 L28 50 Z" fill="url(#gWingL)" opacity="0.85"/>
  <path d="M36 56 L4 36 L14 46 L30 56 Z" fill="url(#gWingL)" opacity="0.78"/>
  <path d="M38 60 L8 46 L18 54 L32 60 Z" fill="url(#gWingL)" opacity="0.70"/>
  <path d="M40 64 L14 56 L24 62 L36 66 Z" fill="url(#gWingL)" opacity="0.60"/>
  <!-- Right wing blades -->
  <path d="M80 48 L114 10 L104 30 L94 42 Z" fill="url(#gWingR)" opacity="0.92"/>
  <path d="M82 52 L118 22 L108 38 L92 50 Z" fill="url(#gWingR)" opacity="0.85"/>
  <path d="M84 56 L116 36 L106 46 L90 56 Z" fill="url(#gWingR)" opacity="0.78"/>
  <path d="M82 60 L112 46 L102 54 L88 60 Z" fill="url(#gWingR)" opacity="0.70"/>
  <path d="M80 64 L106 56 L96 62 L84 66 Z" fill="url(#gWingR)" opacity="0.60"/>
  <!-- Wing inner membrane -->
  <path d="M42 50 L20 18 L30 40 L42 55 Z" fill="#4a8ecc" opacity="0.25"/>
  <path d="M78 50 L100 18 L90 40 L78 55 Z" fill="#4a8ecc" opacity="0.25"/>
  <!-- BODY ARMOR -->
  <path d="M60 30 L48 48 L44 74 L50 92 L60 98 L70 92 L76 74 L72 48 Z" fill="url(#gArmor)" stroke="#c0a864" stroke-width="0.7" filter="url(#glow)"/>
  <!-- Chest plate lines -->
  <path d="M54 48 L60 44 L66 48" fill="none" stroke="#f0e6c0" stroke-width="0.5" opacity="0.6"/>
  <path d="M52 55 L60 50 L68 55" fill="none" stroke="#f0e6c0" stroke-width="0.4" opacity="0.5"/>
  <!-- SHOULDER SPIKES — golden blades -->
  <path d="M48 46 L28 34 L42 48 Z" fill="#d4a843" stroke="#c0a864" stroke-width="0.4"/>
  <path d="M46 42 L22 26 L40 44 Z" fill="#b8922e" stroke="#c0a864" stroke-width="0.3" opacity="0.85"/>
  <path d="M44 40 L26 22 L38 42 Z" fill="#d4a843" opacity="0.7"/>
  <path d="M72 46 L92 34 L78 48 Z" fill="#d4a843" stroke="#c0a864" stroke-width="0.4"/>
  <path d="M74 42 L98 26 L80 44 Z" fill="#b8922e" stroke="#c0a864" stroke-width="0.3" opacity="0.85"/>
  <path d="M76 40 L94 22 L82 42 Z" fill="#d4a843" opacity="0.7"/>
  <!-- HIP / WAIST SPIKES -->
  <path d="M46 72 L32 76 L44 74 Z" fill="#b8922e" opacity="0.7"/>
  <path d="M74 72 L88 76 L76 74 Z" fill="#b8922e" opacity="0.7"/>
  <!-- HELM — angular blue with gold trim -->
  <path d="M60 22 L50 34 L54 38 L60 36 L66 38 L70 34 Z" fill="url(#gHelm)" stroke="#d4a843" stroke-width="0.8"/>
  <!-- Helm visor slit -->
  <line x1="54" y1="32" x2="66" y2="32" stroke="#f0e6c0" stroke-width="0.6" opacity="0.8"/>
  <!-- Helm crest — tall golden blade -->
  <path d="M60 22 L57 8 L60 14 L63 8 Z" fill="#d4a843" stroke="#f0e6c0" stroke-width="0.4" filter="url(#glow)"/>
  <!-- Helm side horns -->
  <path d="M52 30 L44 18 L50 28 Z" fill="#d4a843" opacity="0.8"/>
  <path d="M68 30 L76 18 L70 28 Z" fill="#d4a843" opacity="0.8"/>
  <!-- CORE ORB — divine light sphere -->
  <circle cx="60" cy="58" r="7" fill="url(#gOrb)" filter="url(#aura)" opacity="0.95"/>
  <circle cx="60" cy="58" r="3.5" fill="#fff" opacity="0.98"/>
  <!-- Orb energy rays -->
  <line x1="60" y1="50" x2="60" y2="44" stroke="#f0e6c0" stroke-width="1" opacity="0.7" filter="url(#glow)"/>
  <line x1="67" y1="54" x2="74" y2="48" stroke="#f0e6c0" stroke-width="0.8" opacity="0.6"/>
  <line x1="53" y1="54" x2="46" y2="48" stroke="#f0e6c0" stroke-width="0.8" opacity="0.6"/>
  <line x1="67" y1="62" x2="74" y2="68" stroke="#f0e6c0" stroke-width="0.8" opacity="0.5"/>
  <line x1="53" y1="62" x2="46" y2="68" stroke="#f0e6c0" stroke-width="0.8" opacity="0.5"/>
  <line x1="60" y1="66" x2="60" y2="72" stroke="#f0e6c0" stroke-width="0.6" opacity="0.4"/>
  <line x1="65" y1="52" x2="70" y2="50" stroke="#fffbe6" stroke-width="0.5" opacity="0.5"/>
  <line x1="55" y1="52" x2="50" y2="50" stroke="#fffbe6" stroke-width="0.5" opacity="0.5"/>
  <!-- CAPE / lower drape -->
  <path d="M50 88 L46 108 L54 100 L60 110 L66 100 L74 108 L70 88" fill="none" stroke="#4a8ecc" stroke-width="0.6" opacity="0.4"/>
</svg>''',
                    style={
                        'border': 'none', 'width': '54px', 'height': '54px',
                        'background': 'transparent', 'display': 'block',
                        'overflow': 'hidden',
                    },
                ),
                className='mascot-container',
                style={
                    'width': '58px', 'height': '58px',
                    'background': 'radial-gradient(circle, rgba(212,168,67,0.10) 0%, rgba(74,142,204,0.05) 50%, transparent 75%)',
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

    # ── Control Bar: Mode Toggle + Symbol Selector ──
    html.Div([
        # Left: Mode toggle
        html.Div([
            html.Span('MODE', style={
                'fontSize': '9px', 'fontWeight': '600', 'color': COLORS['text_dim'],
                'letterSpacing': '1.5px', 'marginRight': '12px',
            }),
            html.Div([
                html.Button('DEMO', id='btn-mode-demo', n_clicks=0, className='mode-btn',
                            style=_mode_btn_style('demo', _current_mode == 'demo')),
                html.Button('LIVE', id='btn-mode-live', n_clicks=0, className='mode-btn',
                            style=_mode_btn_style('live', _current_mode == 'live')),
            ], style={
                'display': 'flex', 'gap': '4px',
                'background': 'rgba(255,255,255,0.03)',
                'borderRadius': '10px', 'padding': '3px',
                'border': f'1px solid {COLORS["card_border"]}',
            }),
            html.Span(_current_mode.upper(), id='mode-indicator', style={
                'fontSize': '9px', 'fontWeight': '700', 'letterSpacing': '1px',
                'marginLeft': '10px',
                'color': COLORS['buy'] if _current_mode == 'demo' else COLORS['sell'],
                'background': f'{COLORS["buy"] if _current_mode == "demo" else COLORS["sell"]}18',
                'padding': '2px 8px', 'borderRadius': '8px',
                'border': f'1px solid {COLORS["buy"] if _current_mode == "demo" else COLORS["sell"]}33',
            }),
        ], style={'display': 'flex', 'alignItems': 'center'}),

        # Right: Symbol selector dropdown (per-mode)
        html.Div([
            html.Span(id='symbols-label', children=f'SYMBOLS ({_current_mode.upper()})', style={
                'fontSize': '9px', 'fontWeight': '600', 'color': COLORS['text_dim'],
                'letterSpacing': '1.5px', 'marginRight': '12px', 'flexShrink': '0',
                'whiteSpace': 'nowrap',
            }),
            dcc.Dropdown(
                id='symbol-selector',
                options=[{'label': s, 'value': s} for s in _all_symbols],
                value=_active_symbols,
                multi=True,
                placeholder='Select symbols to trade...',
                style={'minWidth': '320px', 'flex': '1'},
                className='dash-dropdown',
            ),
        ], style={'display': 'flex', 'alignItems': 'center', 'flex': '1', 'maxWidth': '580px'}),
    ], style={
        'display': 'flex',
        'justifyContent': 'space-between',
        'alignItems': 'center',
        'padding': '10px 32px',
        'background': COLORS['bg_secondary'],
        'borderBottom': f'1px solid {COLORS["divider"]}',
        'gap': '24px',
    }),

    # ── Tabs (dynamic – updated by symbol-selector callback) ──
    html.Div(
        _build_tabs(_active_symbols),
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


# ─── Mode Toggle Callback ───
@app.callback(
    [Output('btn-mode-demo', 'style'),
     Output('btn-mode-live', 'style'),
     Output('mode-indicator', 'children'),
     Output('mode-indicator', 'style'),
     Output('symbol-selector', 'value'),
     Output('symbols-label', 'children'),
     Output('tabs-container', 'children')],
    [Input('btn-mode-demo', 'n_clicks'),
     Input('btn-mode-live', 'n_clicks')],
    prevent_initial_call=True,
)
def toggle_mode(demo_clicks, live_clicks):
    """Toggle between DEMO and LIVE mode, swap symbol dropdown values, and persist."""
    triggered = callback_context.triggered[0]['prop_id'] if callback_context.triggered else ''
    config = load_active_config()
    if 'btn-mode-live' in triggered:
        config['mode'] = 'live'
    elif 'btn-mode-demo' in triggered:
        config['mode'] = 'demo'
    mode = config.get('mode', 'demo')
    save_active_config(config)

    demo_style = _mode_btn_style('demo', mode == 'demo')
    live_style = _mode_btn_style('live', mode == 'live')

    indicator_color = COLORS['buy'] if mode == 'demo' else COLORS['sell']
    indicator_style = {
        'fontSize': '9px', 'fontWeight': '700', 'letterSpacing': '1px',
        'marginLeft': '10px',
        'color': indicator_color,
        'background': f'{indicator_color}18',
        'padding': '2px 8px', 'borderRadius': '8px',
        'border': f'1px solid {indicator_color}33',
    }

    # Load the correct per-mode symbol list
    key = 'demo_symbols' if mode == 'demo' else 'live_symbols'
    syms = config.get(key, _all_symbols[:])
    syms = [s for s in syms if s in _all_symbols] or _all_symbols[:]
    label = f'SYMBOLS ({mode.upper()})'
    tabs = _build_tabs(syms)

    return demo_style, live_style, mode.upper(), indicator_style, syms, label, tabs


# ─── Symbol Selector Callback ───
@app.callback(
    Output('tabs-container', 'children', allow_duplicate=True),
    [Input('symbol-selector', 'value')],
    prevent_initial_call=True,
)
def update_symbol_tabs(selected_symbols):
    """Update tabs when symbols are selected/deselected and persist per-mode to active_config.json."""
    if not selected_symbols:
        selected_symbols = []

    config = load_active_config()
    mode = config.get('mode', 'demo')
    key = 'demo_symbols' if mode == 'demo' else 'live_symbols'
    config[key] = selected_symbols
    save_active_config(config)

    return _build_tabs(selected_symbols)


# ─── Main Content Callback ───
@app.callback(
    [Output('tab-content', 'children'),
     Output('account-info', 'children'),
     Output('header-time', 'children'),
     Output('data-hash', 'data')],
    [Input('symbol-tabs', 'value'),
     Input('refresh-interval', 'n_intervals')],
    [dash.State('data-hash', 'data')],
)
def update_content(selected_symbol, n, prev_hash):
    """Single callback: refreshes content only when data changes or tab switches"""
    import hashlib

    if not selected_symbol:
        return html.Div([
            html.Div('⚠', style={'fontSize': '48px', 'marginBottom': '12px', 'opacity': '0.4'}),
            html.Div('No symbols configured', style={
                'color': COLORS['text_dim'], 'fontSize': '16px',
            }),
        ], style={
            'textAlign': 'center', 'marginTop': '120px',
        }), html.Div(), '', ''

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
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

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

    content = build_symbol_tab_content(selected_symbol)

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

    return content, account_display, time_display, current_hash


if __name__ == '__main__':
    app.run(debug=True, host=DASHBOARD_HOST, port=DASHBOARD_PORT)
