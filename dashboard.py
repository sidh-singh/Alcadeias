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


# ─── Configuration ───
JSON_DIR = r'C:\Alcadeias'
DAILY_TRADE_DIR = os.path.join(JSON_DIR, 'daily_trade')
REFRESH_INTERVAL = 5000  # ms

# ─── Premium Color Palette ───
COLORS = {
    # Backgrounds
    'bg': '#0a0e1a',
    'bg_secondary': '#0f1423',
    'card': 'rgba(17, 22, 40, 0.85)',
    'card_solid': '#111628',
    'card_border': 'rgba(99, 115, 171, 0.12)',
    'card_hover': 'rgba(99, 115, 171, 0.08)',
    # Text
    'text': '#e8ecf4',
    'text_secondary': '#a3adc4',
    'text_dim': '#5a6580',
    'text_muted': '#3d4660',
    # Accents
    'accent': '#7c6cf0',
    'accent_glow': 'rgba(124, 108, 240, 0.25)',
    'accent_soft': 'rgba(124, 108, 240, 0.12)',
    # Signals
    'buy': '#00d2a0',
    'buy_soft': 'rgba(0, 210, 160, 0.12)',
    'buy_glow': 'rgba(0, 210, 160, 0.3)',
    'sell': '#ff6b6b',
    'sell_soft': 'rgba(255, 107, 107, 0.12)',
    'sell_glow': 'rgba(255, 107, 107, 0.3)',
    # Status
    'positive': '#00d2a0',
    'negative': '#ff6b6b',
    'warning': '#ffd93d',
    'neutral': '#5a6580',
    # UI
    'header_bg': 'rgba(10, 14, 26, 0.95)',
    'tab_bg': '#0f1423',
    'tab_active': '#7c6cf0',
    'chart_grid': 'rgba(99, 115, 171, 0.08)',
    'divider': 'rgba(99, 115, 171, 0.1)',
    'gradient_start': '#7c6cf0',
    'gradient_end': '#00d2a0',
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
        for f in files if os.path.basename(f) != 'account.json'
    ]


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
    """Build signal status section — clean and consistent across all tabs"""
    signal = data.get('signal', {})
    buy_status = signal.get('buy_status', 'DO_NOTHING')
    sell_status = signal.get('sell_status', 'DO_NOTHING')

    return html.Div([
        html.Div([
            html.Span('⚡', style={'fontSize': '14px'}),
            html.Span('Signals', style={**SECTION_TITLE_STYLE, 'fontSize': '13px'}),
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '8px', 'marginBottom': '10px'}),
        html.Div([
            html.Div([
                html.Div('BUY', style={
                    'fontSize': '9px', 'color': COLORS['text_dim'],
                    'textTransform': 'uppercase', 'letterSpacing': '1.5px',
                    'marginBottom': '8px', 'fontWeight': '500',
                }),
                make_signal_badge(buy_status),
            ], style={
                'textAlign': 'center', 'flex': '1',
                'padding': '14px 12px',
                'borderRight': f'1px solid {COLORS["divider"]}',
            }),
            html.Div([
                html.Div('SELL', style={
                    'fontSize': '9px', 'color': COLORS['text_dim'],
                    'textTransform': 'uppercase', 'letterSpacing': '1.5px',
                    'marginBottom': '8px', 'fontWeight': '500',
                }),
                make_signal_badge(sell_status),
            ], style={
                'textAlign': 'center', 'flex': '1',
                'padding': '14px 12px',
            }),
        ], style={
            'background': COLORS['card'],
            'border': f'1px solid {COLORS["card_border"]}',
            'borderRadius': '10px',
            'display': 'flex',
            'overflow': 'hidden',
            'padding': '0',
        }),
    ])


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


def _cross_color(v):
    """Get color for a crossover value"""
    if v >= 3: return '#00d2a0'
    if v == 2: return '#00e6b8'
    if v == 1: return '#7cd9c0'
    if v == -1: return '#ff8e8e'
    if v == -2: return '#ff6b6b'
    if v <= -3: return '#e53e3e'
    return COLORS['neutral']


def _cross_icon(v):
    """Get icon for a crossover value"""
    if v >= 2: return '🔥'
    if v == 1: return '➡️'
    if v == -1: return '➡️'
    if v <= -2: return '🔥'
    return '➡️'


def _make_power_blocks(power_list, strength):
    """Build compact colored block segments from power list + strength number"""
    blocks = []
    for v in power_list:
        c = COLORS['buy'] if v == 1 else COLORS['sell']
        blocks.append(html.Span(style={
            'display': 'inline-block',
            'width': '10px', 'height': '16px',
            'background': c,
            'borderRadius': '2px',
            'marginRight': '1px',
        }))
    return html.Div([
        html.Span(blocks, style={'display': 'inline-flex', 'alignItems': 'center', 'marginRight': '8px'}),
        html.Span(str(strength), style={
            'fontFamily': "'JetBrains Mono', monospace",
            'fontWeight': '700', 'fontSize': '13px',
            'color': COLORS['buy'] if strength > 0 else COLORS['text_dim'],
        }),
    ], style={'display': 'flex', 'alignItems': 'center'})


def _make_candle_dots(power_list):
    """Build colored dots for each candle"""
    dots = []
    for v in power_list:
        c = COLORS['buy'] if v == 1 else COLORS['sell']
        dots.append(html.Span('●', style={
            'color': c, 'fontSize': '11px', 'marginRight': '2px',
        }))
    return html.Div(dots, style={'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap'})


def _make_cross_bar(value):
    """Build a horizontal progress bar for crossover value"""
    color = _cross_color(value)
    icon = _cross_icon(value)
    abs_val = abs(value) if value != 0 else 0
    pct = min(abs_val / 3 * 100, 100)
    return html.Div([
        html.Span(icon, style={'fontSize': '11px', 'marginRight': '6px'}),
        html.Div([
            html.Div(style={
                'width': f'{pct}%', 'minWidth': '4px',
                'height': '100%',
                'background': color,
                'borderRadius': '4px',
                'transition': 'width 0.4s ease',
            }),
        ], style={
            'flex': '1', 'height': '14px',
            'background': 'rgba(255,255,255,0.04)',
            'borderRadius': '4px', 'overflow': 'hidden',
        }),
        html.Span(f'{value:+d}' if value != 0 else '0', style={
            'fontFamily': "'JetBrains Mono', monospace",
            'fontWeight': '700', 'fontSize': '12px',
            'color': color, 'marginLeft': '8px', 'minWidth': '24px',
        }),
    ], style={'display': 'flex', 'alignItems': 'center', 'width': '100%'})


def build_sha_analysis_panel(symbol, analysis, last_updated=''):
    """Build compact SHA analysis panel with table layout matching screenshot style"""
    sha_list = analysis.get('sha_power_list', [])
    price_list = analysis.get('price_power_list', [])
    crossover = analysis.get('crossover', [])
    sha_buy = analysis.get('sha_buy_strength', 0)
    sha_sell = analysis.get('sha_sell_strength', 0)
    price_buy = analysis.get('price_buy_strength', 0)
    price_sell = analysis.get('price_sell_strength', 0)

    # Overall bias
    total_buy = sha_buy + price_buy
    total_sell = sha_sell + price_sell
    is_bullish = total_buy >= total_sell
    bias_text = 'BULLISH' if is_bullish else 'BEARISH'
    bias_color = COLORS['buy'] if is_bullish else COLORS['sell']

    # Latest crossover value (most recent = index 0)
    latest_cross = crossover[0] if crossover else 0
    # Sum crossover for overall signal
    cross_sum = sum(crossover) if crossover else 0

    # Column header style
    col_hdr = {
        'fontSize': '9px', 'color': COLORS['text_dim'],
        'textTransform': 'uppercase', 'letterSpacing': '1.5px',
        'fontWeight': '600', 'padding': '6px 0',
    }

    # Row builder
    def make_row(icon_color, label, power_list, strength, cross_val):
        return html.Div([
            # Label
            html.Div([
                html.Span('●', style={'color': icon_color, 'fontSize': '10px', 'marginRight': '8px'}),
                html.Span(label, style={
                    'fontWeight': '600', 'fontSize': '12px',
                    'color': COLORS['text'], 'letterSpacing': '0.5px',
                }),
            ], style={'display': 'flex', 'alignItems': 'center', 'minWidth': '70px', 'width': '70px'}),
            # Power blocks
            html.Div([
                _make_power_blocks(power_list, strength),
            ], style={'flex': '1.2', 'padding': '0 10px'}),
            # Candle dots
            html.Div([
                _make_candle_dots(power_list),
            ], style={'flex': '1.2', 'padding': '0 10px'}),
            # Cross bar
            html.Div([
                _make_cross_bar(cross_val),
            ], style={'flex': '1.5', 'padding': '0 4px'}),
        ], style={
            'display': 'flex', 'alignItems': 'center',
            'padding': '8px 16px',
            'borderBottom': f'1px solid {COLORS["divider"]}',
        })

    return html.Div([
        # ── Header bar ──
        html.Div([
            html.Span(symbol, style={
                'fontWeight': '700', 'fontSize': '14px',
                'letterSpacing': '1px', 'color': '#fff',
            }),
            html.Span([
                html.Span('◼ ', style={'fontSize': '8px'}),
                html.Span(bias_text),
            ], style={
                'fontSize': '11px', 'fontWeight': '700',
                'letterSpacing': '1px', 'color': '#fff',
                'background': 'rgba(255,255,255,0.15)',
                'padding': '3px 12px', 'borderRadius': '4px',
            }),
        ], style={
            'display': 'flex', 'justifyContent': 'space-between',
            'alignItems': 'center',
            'padding': '10px 16px',
            'background': f'linear-gradient(135deg, {bias_color}, {bias_color}cc)',
            'borderRadius': '12px 12px 0 0',
        }),
        # ── Column headers ──
        html.Div([
            html.Div('', style={'minWidth': '70px', 'width': '70px'}),
            html.Div('POWER', style={**col_hdr, 'flex': '1.2', 'padding': '0 10px'}),
            html.Div('CANDLES', style={**col_hdr, 'flex': '1.2', 'padding': '0 10px'}),
            html.Div('CROSS', style={**col_hdr, 'flex': '1.5', 'padding': '0 4px'}),
        ], style={
            'display': 'flex', 'alignItems': 'center',
            'padding': '6px 16px',
            'background': 'rgba(255,255,255,0.02)',
            'borderBottom': f'1px solid {COLORS["divider"]}',
        }),
        # ── Data rows ──
        make_row('#5b9bf5', 'SHA', sha_list, sha_buy, latest_cross),
        make_row('#ff6b6b', 'Price', price_list, price_buy, cross_sum),
        make_row('#ffa940', 'IDX', sha_list, sha_buy + price_buy, latest_cross + cross_sum),
        # ── Footer timestamp ──
        html.Div(last_updated, style={
            'fontSize': '10px', 'color': COLORS['text_muted'],
            'textAlign': 'right', 'padding': '6px 16px 8px',
            'fontFamily': "'JetBrains Mono', monospace",
        }),
    ], style={
        'background': COLORS['card_solid'],
        'border': f'1px solid {COLORS["card_border"]}',
        'borderRadius': '12px',
        'overflow': 'hidden',
    })


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
            if os.path.basename(f) != 'historical_summary.json'
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
    path = os.path.join(DAILY_TRADE_DIR, symbol, 'historical_summary.json')
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

        fig.add_trace(go.Bar(
            x=labels, y=profits,
            marker=dict(
                color=colors,
                line=dict(width=0),
            ),
            text=[f'${p:.2f}' for p in profits],
            textposition='outside',
            textfont=dict(size=10, color=COLORS['text_secondary'], family="'Inter', sans-serif"),
            hovertext=hover_texts,
            hoverinfo='text',
            showlegend=False,
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=labels, y=profits,
            mode='markers',
            marker=dict(
                size=[max(v * 80, 6) for v in volumes],
                color=colors,
                opacity=0.2,
                line=dict(width=0),
            ),
            hoverinfo='skip',
            showlegend=False,
        ), row=1, col=1)

        cum_color = COLORS['positive'] if cumulative_profit >= 0 else COLORS['negative']
        # Convert hex to rgba for fillcolor (Plotly doesn't support 8-digit hex)
        _r, _g, _b = int(cum_color[1:3], 16), int(cum_color[3:5], 16), int(cum_color[5:7], 16)
        cum_fill = f'rgba({_r},{_g},{_b},0.05)'
        fig.add_trace(go.Scatter(
            x=labels, y=cum_profits,
            mode='lines+markers+text',
            line=dict(color=cum_color, width=2.5, shape='spline'),
            marker=dict(size=7, color=cum_color, line=dict(width=2, color=COLORS['bg'])),
            text=[f'${c:.0f}' for c in cum_profits],
            textposition='top center',
            textfont=dict(size=9, color=COLORS['text_dim'], family="'Inter', sans-serif"),
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
        for i in range(1, 3):
            fig.update_xaxes(showgrid=False, row=i, col=1,
                             tickfont=dict(size=10, color=COLORS['text_dim']))
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

        # ── Top row: Signals + Positions side by side ──
        html.Div([
            html.Div([build_signal_section(data)], style={'flex': '1'}),
            html.Div([build_positions_section(data)], style={'flex': '1'}),
        ], style={'display': 'flex', 'gap': '16px', 'flexWrap': 'wrap'}),

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
    /* === Reset & Base === */
    *, *::before, *::after { box-sizing: border-box; }
    body {
        margin: 0;
        padding: 0;
        background: #0a0e1a;
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

    /* === Custom Scrollbar === */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb {
        background: rgba(124, 108, 240, 0.25);
        border-radius: 10px;
    }
    ::-webkit-scrollbar-thumb:hover { background: rgba(124, 108, 240, 0.45); }

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

    #tab-content {
        animation: fadeIn 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .skeleton-pulse {
        animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }

    /* === Gradient Top Bar === */
    .gradient-bar {
        height: 2px;
        background: linear-gradient(90deg, #7c6cf0, #00d2a0, #7c6cf0);
        background-size: 200% auto;
        animation: shimmer 4s linear infinite;
    }

    /* === Text Selection === */
    ::selection {
        background: rgba(124, 108, 240, 0.3);
        color: #e8ecf4;
    }

    /* === Details Marker === */
    details > summary { list-style-type: none; }
    details > summary::-webkit-details-marker { display: none; }
    details > summary::before {
        content: '▸ ';
        color: #5a6580;
        transition: transform 0.2s;
    }
    details[open] > summary::before {
        content: '▾ ';
    }

    /* === Plotly Tooltips === */
    .plotly .hoverlayer .hovertext {
        font-family: 'Inter', sans-serif !important;
    }
</style>
</head>
<body>
{%app_entry%}
<footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>
'''

# Load symbols once at startup
_startup_symbols = get_available_symbols()
if not _startup_symbols:
    try:
        _config_path = os.path.join(os.path.dirname(__file__), 'symbols.json')
        with open(_config_path, 'r') as _f:
            _startup_symbols = json.load(_f).get('symbols', [])
    except Exception:
        _startup_symbols = []

app.layout = html.Div([
    # Auto-refresh
    dcc.Interval(id='refresh-interval', interval=REFRESH_INTERVAL, n_intervals=0),
    # Cache to skip redundant DOM rebuilds
    dcc.Store(id='data-hash', data=''),

    # ── Top gradient accent line ──
    html.Div(className='gradient-bar'),

    # ── Header ──
    html.Div([
        html.Div([
            # Logo mark with gradient
            html.Div(style={
                'width': '32px', 'height': '32px', 'borderRadius': '10px',
                'background': 'linear-gradient(135deg, #7c6cf0, #00d2a0)',
                'boxShadow': '0 4px 15px rgba(124, 108, 240, 0.25)',
                'marginRight': '14px',
            }),
            html.Div([
                html.Span('ALCADEIAS', style={
                    'fontSize': '18px', 'fontWeight': '800', 'letterSpacing': '3px',
                    'background': 'linear-gradient(135deg, #e8ecf4, #7c6cf0)',
                    'WebkitBackgroundClip': 'text',
                    'WebkitTextFillColor': 'transparent',
                }),
                html.Div('Trading Dashboard', style={
                    'fontSize': '10px', 'color': '#5a6580',
                    'letterSpacing': '2px', 'textTransform': 'uppercase',
                    'marginTop': '1px',
                }),
            ]),
        ], style={'display': 'flex', 'alignItems': 'center'}),
        html.Div(id='account-info', style={
            'display': 'flex', 'gap': '24px', 'alignItems': 'center',
        }),
        html.Div(id='header-time', style={
            'fontSize': '11px', 'color': '#5a6580',
            'fontFamily': "'JetBrains Mono', monospace",
            'fontWeight': '400',
        }),
    ], style={
        'display': 'flex',
        'justifyContent': 'space-between',
        'alignItems': 'center',
        'padding': '14px 32px',
        'background': 'rgba(10, 14, 26, 0.95)',
        'backdropFilter': 'blur(20px)',
        'WebkitBackdropFilter': 'blur(20px)',
        'borderBottom': f'1px solid {COLORS["divider"]}',
        'color': COLORS['text'],
    }),

    # ── Tabs ──
    html.Div(
        dcc.Tabs(
            id='symbol-tabs',
            value=_startup_symbols[0] if _startup_symbols else '',
            children=[
                dcc.Tab(
                    label=s,
                    value=s,
                    style={
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
                    },
                    selected_style={
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
                    },
                )
                for s in _startup_symbols
            ],
            style={
                'borderBottom': f'1px solid {COLORS["divider"]}',
                'background': COLORS['tab_bg'],
            },
        ),
        style={'padding': '0 32px', 'background': COLORS['tab_bg']},
    ),

    # ── Content ──
    html.Div(id='tab-content', style={
        'padding': '28px 32px 48px 32px',
        'maxWidth': '1280px',
        'margin': '0 auto',
    }),

    # ── Footer ──
    html.Div([
        html.Div(style={
            'height': '1px',
            'background': f'linear-gradient(90deg, transparent, {COLORS["divider"]}, transparent)',
            'marginBottom': '16px',
        }),
        html.Div('Alcadeias Trading System', style={
            'textAlign': 'center',
            'fontSize': '10px',
            'color': COLORS['text_muted'],
            'letterSpacing': '2px',
            'textTransform': 'uppercase',
            'paddingBottom': '16px',
        }),
    ], style={'padding': '0 32px'}),

], style={
    'background': COLORS['bg'],
    'minHeight': '100vh',
    'fontFamily': "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    'color': COLORS['text'],
})


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

    # Build a quick hash of the data to detect changes
    raw = json.dumps({'s': symbol_data, 'a': account, 'd': daily, 'h': historical},
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
    app.run(debug=True, host='0.0.0.0', port=8050)
