import json
import os
import glob
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
    """Create a premium metric card with glassmorphism"""
    accent = color or COLORS['text']
    return html.Div([
        html.Div([
            html.Span(icon or '', style={
                'fontSize': '13px',
                'marginRight': '6px',
                'opacity': '0.7',
            }) if icon else None,
            html.Span(title, style={
                'fontSize': '10px',
                'color': COLORS['text_dim'],
                'textTransform': 'uppercase',
                'letterSpacing': '1.2px',
                'fontWeight': '500',
            }),
        ], style={'display': 'flex', 'alignItems': 'center', 'marginBottom': '8px'}),
        html.Div(value, style={
            'fontSize': '20px',
            'fontWeight': '700',
            'color': accent,
            'fontFamily': "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace",
            'letterSpacing': '-0.5px',
        }),
        html.Div(sub, style={
            'fontSize': '10px',
            'color': COLORS['text_dim'],
            'marginTop': '4px',
            'fontWeight': '400',
        }) if sub else None,
    ], style={
        'background': COLORS['card'],
        'backdropFilter': 'blur(16px)',
        'WebkitBackdropFilter': 'blur(16px)',
        'border': f'1px solid {COLORS["card_border"]}',
        'borderRadius': '14px',
        'padding': '16px 20px',
        'minWidth': '140px',
        'flex': '1',
        'borderTop': f'2px solid {accent}22',
        'transition': 'all 0.3s ease',
    })


def build_positions_section(data):
    """Build the buy/sell position details section with premium styling"""
    pos = data.get('positions', {})
    buy = pos.get('buy', {})
    sell = pos.get('sell', {})

    def pos_row(label, p, color, glow_color):
        count = p.get('count', 0)
        if count == 0:
            return html.Div([
                html.Div([
                    html.Div(style={
                        'width': '8px', 'height': '8px', 'borderRadius': '50%',
                        'background': color, 'marginRight': '10px',
                        'boxShadow': f'0 0 8px {glow_color}',
                    }),
                    html.Span(label, style={
                        'fontWeight': '600', 'fontSize': '14px', 'letterSpacing': '0.5px',
                    }),
                ], style={'display': 'flex', 'alignItems': 'center', 'marginBottom': '12px'}),
                html.Div('No open positions', style={
                    'color': COLORS['text_dim'], 'fontSize': '13px',
                    'paddingLeft': '18px', 'fontStyle': 'italic',
                }),
            ], style={
                **CARD_STYLE,
                'flex': '1',
                'borderLeft': f'3px solid {color}33',
            })

        profit_color = COLORS['positive'] if p.get('total_profit', 0) >= 0 else COLORS['negative']

        return html.Div([
            html.Div([
                html.Div(style={
                    'width': '8px', 'height': '8px', 'borderRadius': '50%',
                    'background': color, 'marginRight': '10px',
                    'boxShadow': f'0 0 8px {glow_color}',
                }),
                html.Span(label, style={
                    'fontWeight': '600', 'fontSize': '14px', 'letterSpacing': '0.5px',
                }),
                html.Span(f'{count} position{"s" if count > 1 else ""}', style={
                    'marginLeft': 'auto', 'color': COLORS['text_dim'],
                    'fontSize': '11px', 'fontWeight': '500',
                    'background': COLORS['card_hover'],
                    'padding': '3px 10px', 'borderRadius': '12px',
                }),
            ], style={'display': 'flex', 'alignItems': 'center', 'marginBottom': '16px'}),
            html.Div([
                make_metric_card('Total P/L', f"${p.get('total_profit', 0):.2f}", profit_color, icon='💰'),
                make_metric_card('Volume', f"{p.get('total_volume', 0):.2f}", icon='📦'),
                make_metric_card('First P/L', f"${p.get('first_profit', 0):.2f}",
                                 COLORS['positive'] if p.get('first_profit', 0) >= 0 else COLORS['negative'],
                                 f"Vol: {p.get('first_volume', 0):.2f}"),
                make_metric_card('Last P/L', f"${p.get('last_profit', 0):.2f}",
                                 COLORS['positive'] if p.get('last_profit', 0) >= 0 else COLORS['negative'],
                                 f"Vol: {p.get('last_volume', 0):.2f}"),
            ], style={'display': 'flex', 'gap': '10px', 'flexWrap': 'wrap'}),
        ], style={
            **CARD_STYLE,
            'flex': '1',
            'borderLeft': f'3px solid {color}55',
        })

    return html.Div([
        html.Div([
            html.Span('📊', style={'fontSize': '18px'}),
            html.Span('Position Details', style=SECTION_TITLE_STYLE),
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '10px', 'marginBottom': '16px'}),
        html.Div([
            pos_row('BUY', buy, COLORS['buy'], COLORS['buy_glow']),
            pos_row('SELL', sell, COLORS['sell'], COLORS['sell_glow']),
        ], style={'display': 'flex', 'gap': '16px', 'flexWrap': 'wrap'}),
    ])


def build_signal_section(data):
    """Build signal status section with premium styling"""
    signal = data.get('signal', {})
    buy_status = signal.get('buy_status', 'DO_NOTHING')
    sell_status = signal.get('sell_status', 'DO_NOTHING')
    order_resp = data.get('order_response')
    close_resp = data.get('close_response')

    children = [
        html.Div([
            html.Span('⚡', style={'fontSize': '18px'}),
            html.Span('Signal Status', style=SECTION_TITLE_STYLE),
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '10px', 'marginBottom': '16px'}),
        html.Div([
            html.Div([
                html.Div('BUY SIGNAL', style={
                    'fontSize': '10px', 'color': COLORS['text_dim'],
                    'textTransform': 'uppercase', 'letterSpacing': '1.5px',
                    'marginBottom': '12px', 'fontWeight': '500',
                }),
                make_signal_badge(buy_status),
            ], style={
                'textAlign': 'center', 'flex': '1',
                'padding': '24px 16px',
                'borderRight': f'1px solid {COLORS["divider"]}',
            }),
            html.Div([
                html.Div('SELL SIGNAL', style={
                    'fontSize': '10px', 'color': COLORS['text_dim'],
                    'textTransform': 'uppercase', 'letterSpacing': '1.5px',
                    'marginBottom': '12px', 'fontWeight': '500',
                }),
                make_signal_badge(sell_status),
            ], style={
                'textAlign': 'center', 'flex': '1',
                'padding': '24px 16px',
            }),
        ], style={
            **CARD_STYLE,
            'display': 'flex',
            'overflow': 'hidden',
            'padding': '0',
        }),
    ]

    if order_resp:
        children.append(html.Div([
            html.Div('LAST ORDER RESPONSE', style={
                'fontSize': '10px', 'color': COLORS['text_dim'],
                'textTransform': 'uppercase', 'letterSpacing': '1.5px', 'marginBottom': '10px',
                'fontWeight': '500',
            }),
            html.Code(str(order_resp), style={
                'fontSize': '12px', 'color': COLORS['warning'],
                'wordBreak': 'break-all', 'whiteSpace': 'pre-wrap',
                'fontFamily': "'JetBrains Mono', 'SF Mono', monospace",
            }),
        ], style={
            **CARD_STYLE,
            'marginTop': '12px',
        }))

    if close_resp:
        status_color = COLORS['buy'] if close_resp.get('success') else COLORS['sell']

        children.append(html.Div([
            html.Div('CLOSE POSITIONS RESPONSE', style={
                'fontSize': '10px', 'color': COLORS['text_dim'],
                'textTransform': 'uppercase', 'letterSpacing': '1.5px', 'marginBottom': '14px',
                'fontWeight': '500',
            }),
            html.Div([
                html.Div([
                    html.Div('Status', style={'fontSize': '10px', 'color': COLORS['text_dim']}),
                    html.Div(close_resp.get('message', 'N/A'), style={
                        'fontSize': '13px', 'color': status_color, 'fontWeight': '600'
                    }),
                ], style={'marginBottom': '12px'}),
                html.Div([
                    make_metric_card('Total', str(close_resp.get('total_positions', 0)), COLORS['text']),
                    make_metric_card('Filtered', str(close_resp.get('filtered_count', 0)), COLORS['accent']),
                    make_metric_card('Closed', str(close_resp.get('closed_count', 0)), COLORS['buy']),
                    make_metric_card('Failed', str(close_resp.get('failed_count', 0)), COLORS['sell']),
                ], style={'display': 'flex', 'gap': '10px', 'flexWrap': 'wrap', 'marginBottom': '12px'}),
                html.Div([
                    html.Div('Closed Tickets: ', style={
                        'fontSize': '11px', 'color': COLORS['text_dim'], 'display': 'inline',
                    }),
                    html.Code(str(close_resp.get('closed_tickets', [])), style={
                        'fontSize': '11px', 'color': COLORS['positive'],
                        'fontFamily': "'JetBrains Mono', monospace",
                    }),
                ], style={'marginBottom': '8px'}) if close_resp.get('closed_tickets') else None,
                html.Div([
                    html.Div('Errors:', style={
                        'fontSize': '11px', 'color': COLORS['negative'], 'marginBottom': '4px',
                    }),
                    html.Div([
                        html.Div(f'• {err}', style={
                            'fontSize': '11px', 'color': COLORS['text_dim'], 'marginLeft': '8px',
                        })
                        for err in close_resp.get('errors', [])
                    ]),
                ]) if close_resp.get('errors') else None,
            ]),
        ], style={
            **CARD_STYLE,
            'marginTop': '12px',
        }))

    return html.Div(children)


def build_sha_strength_chart(analysis):
    """Build SHA strength gauge chart with premium styling"""
    buy_str = analysis.get('sha_buy_strength', 0)
    sell_str = analysis.get('sha_sell_strength', 0)
    total = buy_str + sell_str or 1

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=[buy_str], y=['SHA'],
        orientation='h', name='Bullish',
        marker=dict(
            color=COLORS['buy'],
            line=dict(width=0),
        ),
        text=[f'{buy_str}/{total}'], textposition='inside',
        textfont=dict(color='white', size=13, family="'Inter', sans-serif"),
    ))
    fig.add_trace(go.Bar(
        x=[sell_str], y=['SHA'],
        orientation='h', name='Bearish',
        marker=dict(
            color=COLORS['sell'],
            line=dict(width=0),
        ),
        text=[f'{sell_str}/{total}'], textposition='inside',
        textfont=dict(color='white', size=13, family="'Inter', sans-serif"),
    ))

    p_buy = analysis.get('price_buy_strength', 0)
    p_sell = analysis.get('price_sell_strength', 0)
    p_total = p_buy + p_sell or 1

    fig.add_trace(go.Bar(
        x=[p_buy], y=['Price'],
        orientation='h', name='Price Bull',
        marker=dict(color='#00e6b8', line=dict(width=0)),
        showlegend=False,
        text=[f'{p_buy}/{p_total}'], textposition='inside',
        textfont=dict(color='#0a0e1a', size=13, family="'Inter', sans-serif"),
    ))
    fig.add_trace(go.Bar(
        x=[p_sell], y=['Price'],
        orientation='h', name='Price Bear',
        marker=dict(color='#ff8e8e', line=dict(width=0)),
        showlegend=False,
        text=[f'{p_sell}/{p_total}'], textposition='inside',
        textfont=dict(color='#0a0e1a', size=13, family="'Inter', sans-serif"),
    ))

    fig.update_layout(
        barmode='stack',
        height=130,
        margin=dict(l=60, r=20, t=10, b=10),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color=COLORS['text_secondary'], size=12, family="'Inter', sans-serif"),
        legend=dict(
            orientation='h', y=-0.3,
            font=dict(size=11, color=COLORS['text_secondary']),
            bgcolor='rgba(0,0,0,0)',
        ),
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(showgrid=False),
        bargap=0.35,
    )

    return fig


def build_power_list_chart(analysis):
    """Build the SHA/Price power list heatmap with crossover — premium version"""
    sha_list = analysis.get('sha_power_list', [])
    price_list = analysis.get('price_power_list', [])
    crossover = analysis.get('crossover', [])
    n = len(sha_list)

    labels = [f'C-{i+1}' for i in range(n)]

    fig = make_subplots(
        rows=3, cols=1,
        row_heights=[0.33, 0.33, 0.34],
        vertical_spacing=0.10,
        subplot_titles=['SHA Power (1=Bull, 0=Bear)', 'Price Power (1=Bull, 0=Bear)', 'Crossover'],
    )

    # SHA power
    sha_colors = [COLORS['buy'] if v == 1 else COLORS['sell'] for v in sha_list]
    fig.add_trace(go.Bar(
        x=labels, y=[1]*n,
        marker=dict(color=sha_colors, line=dict(width=1, color='rgba(10,14,26,0.5)')),
        text=[str(v) for v in sha_list],
        textposition='inside',
        textfont=dict(size=13, color='white', family="'Inter', sans-serif"),
        showlegend=False,
    ), row=1, col=1)

    # Price power
    price_colors = [COLORS['buy'] if v == 1 else COLORS['sell'] for v in price_list]
    fig.add_trace(go.Bar(
        x=labels, y=[1]*n,
        marker=dict(color=price_colors, line=dict(width=1, color='rgba(10,14,26,0.5)')),
        text=[str(v) for v in price_list],
        textposition='inside',
        textfont=dict(size=13, color='white', family="'Inter', sans-serif"),
        showlegend=False,
    ), row=2, col=1)

    # Crossover
    cross_colors = []
    for v in crossover:
        if v == 3:
            cross_colors.append('#00d2a0')
        elif v == 2:
            cross_colors.append('#00e6b8')
        elif v == 1:
            cross_colors.append('#7cd9c0')
        elif v == -1:
            cross_colors.append('#ff8e8e')
        elif v == -2:
            cross_colors.append('#ff6b6b')
        elif v == -3:
            cross_colors.append('#e53e3e')
        else:
            cross_colors.append(COLORS['neutral'])

    fig.add_trace(go.Bar(
        x=labels,
        y=[abs(v) for v in crossover],
        marker=dict(color=cross_colors, line=dict(width=1, color='rgba(10,14,26,0.5)')),
        text=[str(v) for v in crossover],
        textposition='inside',
        textfont=dict(size=13, color='white', family="'Inter', sans-serif"),
        showlegend=False,
    ), row=3, col=1)

    fig.update_layout(
        height=380,
        margin=dict(l=30, r=20, t=30, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color=COLORS['text_secondary'], size=11, family="'Inter', sans-serif"),
        bargap=0.15,
    )

    for i in range(1, 4):
        fig.update_yaxes(showticklabels=False, showgrid=False, zeroline=False, row=i, col=1)
        fig.update_xaxes(showgrid=False, row=i, col=1, tickfont=dict(size=10, color=COLORS['text_dim']))

    for ann in fig['layout']['annotations']:
        ann['font'] = dict(size=11, color=COLORS['text_dim'], family="'Inter', sans-serif")

    return fig


def build_crossover_legend():
    """Crossover value legend with premium pills"""
    items = [
        ('+3', 'Strong Bull', '#00d2a0'),
        ('+2', 'Overlap Bull', '#00e6b8'),
        ('+1', 'Weak Bull', '#7cd9c0'),
        ('-1', 'Weak Bear', '#ff8e8e'),
        ('-2', 'Overlap Bear', '#ff6b6b'),
        ('-3', 'Strong Bear', '#e53e3e'),
    ]
    return html.Div([
        html.Div([
            html.Span(style={
                'width': '10px', 'height': '10px', 'borderRadius': '3px',
                'background': c, 'display': 'inline-block', 'marginRight': '6px',
                'boxShadow': f'0 0 6px {c}44',
            }),
            html.Span(f'{val} ', style={
                'fontWeight': '600', 'fontSize': '11px', 'color': COLORS['text'],
                'fontFamily': "'JetBrains Mono', monospace",
            }),
            html.Span(label, style={
                'fontSize': '10px', 'color': COLORS['text_dim'],
            }),
        ], style={
            'display': 'inline-flex', 'alignItems': 'center',
            'marginRight': '16px', 'padding': '4px 0',
        })
        for val, label, c in items
    ], style={
        'marginTop': '8px', 'padding': '10px 0',
        'borderTop': f'1px solid {COLORS["divider"]}',
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
            fillcolor=f'{cum_color}08',
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
            html.Span('📈', style={'fontSize': '18px'}),
            html.Span('Daily Trade Log', style=SECTION_TITLE_STYLE),
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '10px', 'marginBottom': '16px'}),
        metrics_row,
        html.Div([chart], style=CARD_STYLE),
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
                    'margin': '0', 'fontSize': '28px', 'fontWeight': '800',
                    'color': COLORS['text'],
                    'letterSpacing': '1px',
                }),
                html.Span(f'{date_str}  •  {time_str}', style={
                    'fontSize': '12px', 'color': COLORS['text_dim'],
                    'marginLeft': '16px', 'fontWeight': '400',
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
            'alignItems': 'center', 'marginBottom': '28px',
            'paddingBottom': '20px',
            'borderBottom': f'1px solid {COLORS["divider"]}',
        }),

        # Signal section
        build_signal_section(data),

        html.Div(style={'height': '24px'}),

        # Positions section
        build_positions_section(data),

        html.Div(style={'height': '24px'}),

        # Analysis section
        html.Div([
            html.Div([
                html.Span('🔬', style={'fontSize': '18px'}),
                html.Span('SHA Indicator Analysis', style=SECTION_TITLE_STYLE),
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '10px', 'marginBottom': '16px'}),

            # Strength bar
            html.Div([
                html.Div('STRENGTH', style={
                    'fontSize': '10px', 'color': COLORS['text_dim'],
                    'textTransform': 'uppercase', 'letterSpacing': '1.5px',
                    'marginBottom': '10px', 'fontWeight': '500',
                }),
                dcc.Graph(
                    figure=build_sha_strength_chart(analysis),
                    config={'displayModeBar': False},
                    style={'height': '130px'},
                ),
            ], style=CARD_STYLE),

            html.Div(style={'height': '14px'}),

            # Power lists + Crossover
            html.Div([
                html.Div('CANDLE-BY-CANDLE ANALYSIS (latest → oldest)', style={
                    'fontSize': '10px', 'color': COLORS['text_dim'],
                    'textTransform': 'uppercase', 'letterSpacing': '1.5px',
                    'marginBottom': '6px', 'fontWeight': '500',
                }),
                dcc.Graph(
                    figure=build_power_list_chart(analysis),
                    config={'displayModeBar': False},
                    style={'height': '380px'},
                ),
                build_crossover_legend(),
            ], style=CARD_STYLE),
        ]),

        html.Div(style={'height': '24px'}),

        # Daily Trade Log section
        build_daily_trades_section(symbol),

        html.Div(style={'height': '24px'}),

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
