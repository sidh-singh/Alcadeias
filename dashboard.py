import json
import os
import glob
from datetime import datetime

import dash
from dash import dcc, html, callback_context
from dash.dependencies import Input, Output
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ─── Configuration ───
JSON_DIR = r'C:\Alcadeias'
DAILY_TRADE_DIR = os.path.join(JSON_DIR, 'daily_trade')
REFRESH_INTERVAL = 5000  # ms

# ─── Color Palette ───
COLORS = {
    'bg': '#0f1117',
    'card': '#1a1d27',
    'card_border': '#2a2d3a',
    'text': '#e1e4eb',
    'text_dim': '#8b8fa3',
    'accent': '#6c5ce7',
    'buy': '#00b894',
    'sell': '#e17055',
    'neutral': '#636e72',
    'warning': '#fdcb6e',
    'header_bg': '#161922',
    'tab_bg': '#1e2130',
    'tab_active': '#6c5ce7',
    'positive': '#00cec9',
    'negative': '#ff7675',
    'chart_grid': '#2d3047',
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
    """Create a styled signal badge"""
    color_map = {
        'BUY': COLORS['buy'],
        'SELL': COLORS['sell'],
        'CLOSE_BUY': COLORS['warning'],
        'CLOSE_SELL': COLORS['warning'],
        'BUY_MORE': '#00b894',
        'SELL_MORE': '#e17055',
        'DO_NOTHING': COLORS['neutral'],
    }
    color = color_map.get(status, COLORS['neutral'])
    return html.Span(status, style={
        'background': color,
        'color': '#fff',
        'padding': '4px 14px',
        'borderRadius': '20px',
        'fontSize': '13px',
        'fontWeight': '700',
        'letterSpacing': '0.5px',
    })


def make_metric_card(title, value, color=None, sub=None):
    """Create a small metric card"""
    return html.Div([
        html.Div(title, style={
            'fontSize': '11px',
            'color': COLORS['text_dim'],
            'textTransform': 'uppercase',
            'letterSpacing': '1px',
            'marginBottom': '4px',
        }),
        html.Div(value, style={
            'fontSize': '22px',
            'fontWeight': '700',
            'color': color or COLORS['text'],
        }),
        html.Div(sub, style={
            'fontSize': '11px',
            'color': COLORS['text_dim'],
            'marginTop': '2px',
        }) if sub else None,
    ], style={
        'background': COLORS['card'],
        'border': f'1px solid {COLORS["card_border"]}',
        'borderRadius': '10px',
        'padding': '14px 18px',
        'minWidth': '140px',
    })


def build_positions_section(data):
    """Build the buy/sell position details section"""
    pos = data.get('positions', {})
    buy = pos.get('buy', {})
    sell = pos.get('sell', {})

    def pos_row(label, p, color):
        count = p.get('count', 0)
        if count == 0:
            return html.Div([
                html.Div([
                    html.Span('●', style={'color': color, 'marginRight': '8px', 'fontSize': '14px'}),
                    html.Span(label, style={'fontWeight': '600', 'fontSize': '15px'}),
                ], style={'display': 'flex', 'alignItems': 'center', 'marginBottom': '10px'}),
                html.Div('No open positions', style={
                    'color': COLORS['text_dim'], 'fontSize': '13px', 'paddingLeft': '22px'
                }),
            ], style={
                'background': COLORS['card'],
                'border': f'1px solid {COLORS["card_border"]}',
                'borderRadius': '12px',
                'padding': '18px',
                'flex': '1',
            })

        profit_color = COLORS['positive'] if p.get('total_profit', 0) >= 0 else COLORS['negative']

        return html.Div([
            html.Div([
                html.Span('●', style={'color': color, 'marginRight': '8px', 'fontSize': '14px'}),
                html.Span(label, style={'fontWeight': '600', 'fontSize': '15px'}),
                html.Span(f'{count} position{"s" if count > 1 else ""}', style={
                    'marginLeft': 'auto', 'color': COLORS['text_dim'], 'fontSize': '12px',
                }),
            ], style={'display': 'flex', 'alignItems': 'center', 'marginBottom': '14px'}),
            html.Div([
                make_metric_card('Total Profit', f"${p.get('total_profit', 0):.2f}", profit_color),
                make_metric_card('Total Volume', f"{p.get('total_volume', 0):.2f}"),
                make_metric_card('First P/L', f"${p.get('first_profit', 0):.2f}",
                                 COLORS['positive'] if p.get('first_profit', 0) >= 0 else COLORS['negative'],
                                 f"Vol: {p.get('first_volume', 0):.2f}"),
                make_metric_card('Last P/L', f"${p.get('last_profit', 0):.2f}",
                                 COLORS['positive'] if p.get('last_profit', 0) >= 0 else COLORS['negative'],
                                 f"Vol: {p.get('last_volume', 0):.2f}"),
            ], style={'display': 'flex', 'gap': '10px', 'flexWrap': 'wrap'}),
        ], style={
            'background': COLORS['card'],
            'border': f'1px solid {COLORS["card_border"]}',
            'borderRadius': '12px',
            'padding': '18px',
            'flex': '1',
        })

    return html.Div([
        html.H3('📊 Position Details', style={
            'color': COLORS['text'], 'fontSize': '16px', 'marginBottom': '14px', 'fontWeight': '600',
        }),
        html.Div([
            pos_row('BUY', buy, COLORS['buy']),
            pos_row('SELL', sell, COLORS['sell']),
        ], style={'display': 'flex', 'gap': '16px', 'flexWrap': 'wrap'}),
    ])


def build_signal_section(data):
    """Build signal status section"""
    signal = data.get('signal', {})
    buy_status = signal.get('buy_status', 'DO_NOTHING')
    sell_status = signal.get('sell_status', 'DO_NOTHING')
    order_resp = data.get('order_response')
    close_resp = data.get('close_response')

    children = [
        html.H3('⚡ Signal Status', style={
            'color': COLORS['text'], 'fontSize': '16px', 'marginBottom': '14px', 'fontWeight': '600',
        }),
        html.Div([
            html.Div([
                html.Div('BUY SIGNAL', style={
                    'fontSize': '11px', 'color': COLORS['text_dim'],
                    'textTransform': 'uppercase', 'letterSpacing': '1px', 'marginBottom': '8px',
                }),
                make_signal_badge(buy_status),
            ], style={'textAlign': 'center', 'flex': '1'}),
            html.Div([
                html.Div('SELL SIGNAL', style={
                    'fontSize': '11px', 'color': COLORS['text_dim'],
                    'textTransform': 'uppercase', 'letterSpacing': '1px', 'marginBottom': '8px',
                }),
                make_signal_badge(sell_status),
            ], style={'textAlign': 'center', 'flex': '1'}),
        ], style={
            'display': 'flex', 'gap': '20px',
            'background': COLORS['card'],
            'border': f'1px solid {COLORS["card_border"]}',
            'borderRadius': '12px',
            'padding': '20px',
        }),
    ]

    if order_resp:
        children.append(html.Div([
            html.Div('LAST ORDER RESPONSE', style={
                'fontSize': '11px', 'color': COLORS['text_dim'],
                'textTransform': 'uppercase', 'letterSpacing': '1px', 'marginBottom': '8px',
            }),
            html.Code(str(order_resp), style={
                'fontSize': '12px', 'color': COLORS['warning'],
                'wordBreak': 'break-all', 'whiteSpace': 'pre-wrap',
            }),
        ], style={
            'background': COLORS['card'],
            'border': f'1px solid {COLORS["card_border"]}',
            'borderRadius': '12px',
            'padding': '16px',
            'marginTop': '12px',
        }))

    if close_resp:
        # Determine color based on success
        status_color = COLORS['buy'] if close_resp.get('success') else COLORS['sell']
        
        children.append(html.Div([
            html.Div('CLOSE POSITIONS RESPONSE', style={
                'fontSize': '11px', 'color': COLORS['text_dim'],
                'textTransform': 'uppercase', 'letterSpacing': '1px', 'marginBottom': '12px',
            }),
            html.Div([
                html.Div([
                    html.Div('Status', style={'fontSize': '10px', 'color': COLORS['text_dim']}),
                    html.Div(close_resp.get('message', 'N/A'), style={
                        'fontSize': '13px', 'color': status_color, 'fontWeight': '600'
                    }),
                ], style={'marginBottom': '10px'}),
                html.Div([
                    make_metric_card('Total Positions', str(close_resp.get('total_positions', 0)), COLORS['text']),
                    make_metric_card('Filtered', str(close_resp.get('filtered_count', 0)), COLORS['accent']),
                    make_metric_card('Closed', str(close_resp.get('closed_count', 0)), COLORS['buy']),
                    make_metric_card('Failed', str(close_resp.get('failed_count', 0)), COLORS['sell']),
                ], style={'display': 'flex', 'gap': '10px', 'flexWrap': 'wrap', 'marginBottom': '10px'}),
                html.Div([
                    html.Div('Closed Tickets: ', style={'fontSize': '11px', 'color': COLORS['text_dim'], 'display': 'inline'}),
                    html.Code(str(close_resp.get('closed_tickets', [])), style={
                        'fontSize': '11px', 'color': COLORS['positive']
                    }),
                ], style={'marginBottom': '8px'}) if close_resp.get('closed_tickets') else None,
                html.Div([
                    html.Div('Errors:', style={'fontSize': '11px', 'color': COLORS['negative'], 'marginBottom': '4px'}),
                    html.Div([
                        html.Div(f'• {err}', style={'fontSize': '11px', 'color': COLORS['text_dim'], 'marginLeft': '8px'})
                        for err in close_resp.get('errors', [])
                    ]),
                ]) if close_resp.get('errors') else None,
            ], style={'fontSize': '12px'}),
        ], style={
            'background': COLORS['card'],
            'border': f'1px solid {COLORS["card_border"]}',
            'borderRadius': '12px',
            'padding': '16px',
            'marginTop': '12px',
        }))

    return html.Div(children)


def build_sha_strength_chart(analysis):
    """Build SHA strength gauge chart"""
    buy_str = analysis.get('sha_buy_strength', 0)
    sell_str = analysis.get('sha_sell_strength', 0)
    total = buy_str + sell_str or 1

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=[buy_str], y=['SHA'],
        orientation='h', name='Bullish',
        marker_color=COLORS['buy'],
        text=[f'{buy_str}/{total}'], textposition='inside',
        textfont=dict(color='white', size=13, family='monospace'),
    ))
    fig.add_trace(go.Bar(
        x=[sell_str], y=['SHA'],
        orientation='h', name='Bearish',
        marker_color=COLORS['sell'],
        text=[f'{sell_str}/{total}'], textposition='inside',
        textfont=dict(color='white', size=13, family='monospace'),
    ))

    p_buy = analysis.get('price_buy_strength', 0)
    p_sell = analysis.get('price_sell_strength', 0)
    p_total = p_buy + p_sell or 1

    fig.add_trace(go.Bar(
        x=[p_buy], y=['Price'],
        orientation='h', name='Price Bull',
        marker_color='#55efc4', showlegend=False,
        text=[f'{p_buy}/{p_total}'], textposition='inside',
        textfont=dict(color='#1a1d27', size=13, family='monospace'),
    ))
    fig.add_trace(go.Bar(
        x=[p_sell], y=['Price'],
        orientation='h', name='Price Bear',
        marker_color='#fab1a0', showlegend=False,
        text=[f'{p_sell}/{p_total}'], textposition='inside',
        textfont=dict(color='#1a1d27', size=13, family='monospace'),
    ))

    fig.update_layout(
        barmode='stack',
        height=130,
        margin=dict(l=60, r=20, t=10, b=10),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color=COLORS['text'], size=12),
        legend=dict(
            orientation='h', y=-0.3,
            font=dict(size=11), bgcolor='rgba(0,0,0,0)',
        ),
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(showgrid=False),
    )

    return fig


def build_power_list_chart(analysis):
    """Build the SHA/Price power list heatmap with crossover"""
    sha_list = analysis.get('sha_power_list', [])
    price_list = analysis.get('price_power_list', [])
    crossover = analysis.get('crossover', [])
    n = len(sha_list)

    labels = [f'C-{i+1}' for i in range(n)]

    fig = make_subplots(
        rows=3, cols=1,
        row_heights=[0.33, 0.33, 0.34],
        vertical_spacing=0.08,
        subplot_titles=['SHA Power (1=Bull, 0=Bear)', 'Price Power (1=Bull, 0=Bear)', 'Crossover'],
    )

    # SHA power heatmap as bar
    sha_colors = [COLORS['buy'] if v == 1 else COLORS['sell'] for v in sha_list]
    fig.add_trace(go.Bar(
        x=labels, y=[1]*n,
        marker_color=sha_colors,
        text=[str(v) for v in sha_list],
        textposition='inside',
        textfont=dict(size=14, color='white', family='monospace'),
        showlegend=False,
    ), row=1, col=1)

    # Price power
    price_colors = [COLORS['buy'] if v == 1 else COLORS['sell'] for v in price_list]
    fig.add_trace(go.Bar(
        x=labels, y=[1]*n,
        marker_color=price_colors,
        text=[str(v) for v in price_list],
        textposition='inside',
        textfont=dict(size=14, color='white', family='monospace'),
        showlegend=False,
    ), row=2, col=1)

    # Crossover
    cross_colors = []
    for v in crossover:
        if v == 3:
            cross_colors.append('#00b894')
        elif v == 2:
            cross_colors.append('#55efc4')
        elif v == 1:
            cross_colors.append('#81ecec')
        elif v == -1:
            cross_colors.append('#fab1a0')
        elif v == -2:
            cross_colors.append('#e17055')
        elif v == -3:
            cross_colors.append('#d63031')
        else:
            cross_colors.append(COLORS['neutral'])

    fig.add_trace(go.Bar(
        x=labels,
        y=[abs(v) for v in crossover],
        marker_color=cross_colors,
        text=[str(v) for v in crossover],
        textposition='inside',
        textfont=dict(size=14, color='white', family='monospace'),
        showlegend=False,
    ), row=3, col=1)

    fig.update_layout(
        height=380,
        margin=dict(l=30, r=20, t=30, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color=COLORS['text'], size=11),
    )

    for i in range(1, 4):
        fig.update_yaxes(showticklabels=False, showgrid=False, zeroline=False, row=i, col=1)
        fig.update_xaxes(showgrid=False, row=i, col=1)

    # Style subplot titles
    for ann in fig['layout']['annotations']:
        ann['font'] = dict(size=12, color=COLORS['text_dim'])

    return fig


def build_crossover_legend():
    """Crossover value legend"""
    items = [
        ('+3', 'Strong Bull', '#00b894'),
        ('+2', 'Overlap Bull', '#55efc4'),
        ('+1', 'Weak Bull', '#81ecec'),
        ('-1', 'Weak Bear', '#fab1a0'),
        ('-2', 'Overlap Bear', '#e17055'),
        ('-3', 'Strong Bear', '#d63031'),
    ]
    return html.Div([
        html.Div([
            html.Span('■', style={'color': c, 'marginRight': '4px', 'fontSize': '12px'}),
            html.Span(f'{val} ', style={'fontWeight': '600', 'fontSize': '11px', 'color': COLORS['text']}),
            html.Span(label, style={'fontSize': '11px', 'color': COLORS['text_dim']}),
        ], style={'display': 'inline-flex', 'alignItems': 'center', 'marginRight': '14px'})
        for val, label, c in items
    ], style={'marginTop': '6px', 'padding': '8px 0'})


# ─── Daily Trade Functions ───

def load_daily_trade_data():
    """Load today's daily trade log"""
    now = datetime.now()
    filename = now.strftime('%d_%b_%Y').lower() + '.json'
    path = os.path.join(DAILY_TRADE_DIR, filename)
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def load_historical_summary():
    """Load the historical summary (last 10 years)"""
    path = os.path.join(DAILY_TRADE_DIR, 'historical_summary.json')
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def build_daily_trades_section(symbol):
    """Build daily trades chart and metrics for a symbol"""
    daily_data = load_daily_trade_data()
    historical = load_historical_summary()

    # Extract today's deals for this symbol
    today_deals = []
    symbol_summary = {}
    overall_summary = {}
    if daily_data:
        symbol_data = daily_data.get('symbols', {}).get(symbol, {})
        today_deals = symbol_data.get('deals', [])
        symbol_summary = symbol_data
        overall_summary = daily_data.get('summary', {})

    # ── Metric Cards ──
    today_total = overall_summary.get('total_profit', 0)
    today_avg = overall_summary.get('avg_profit', 0)
    today_count = overall_summary.get('total_deals', 0)
    hist_total = historical.get('total_profit', 0) if historical else 0
    hist_count = historical.get('total_deals', 0) if historical else 0

    metrics_row = html.Div([
        make_metric_card(
            'Today Total P/L',
            f'${today_total:,.2f}',
            COLORS['positive'] if today_total >= 0 else COLORS['negative'],
            f'{today_count} deals',
        ),
        make_metric_card(
            'Today Avg Profit',
            f'${today_avg:,.2f}',
            COLORS['positive'] if today_avg >= 0 else COLORS['negative'],
            'per deal',
        ),
        make_metric_card(
            f'{symbol} P/L Today',
            f'${symbol_summary.get("total_profit", 0):,.2f}',
            COLORS['positive'] if symbol_summary.get('total_profit', 0) >= 0 else COLORS['negative'],
            f'{symbol_summary.get("deal_count", 0)} deals',
        ),
        make_metric_card(
            'Lifetime P/L',
            f'${hist_total:,.2f}',
            COLORS['positive'] if hist_total >= 0 else COLORS['negative'],
            f'{hist_count} deals (last 10y)',
        ),
    ], style={'display': 'flex', 'gap': '12px', 'flexWrap': 'wrap', 'marginBottom': '16px'})

    # ── Position vs Profit/Loss Chart ──
    if today_deals:
        # Sort deals by time
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
            # Use net_profit (profit + commission + swap + fee) to match MT5's actual P/L
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
            vertical_spacing=0.12,
            subplot_titles=['Profit/Loss per Deal', 'Cumulative P/L'],
        )

        # Bar chart: profit per deal
        fig.add_trace(go.Bar(
            x=labels, y=profits,
            marker_color=colors,
            text=[f'${p:.2f}' for p in profits],
            textposition='outside',
            textfont=dict(size=10, color=COLORS['text']),
            hovertext=hover_texts,
            hoverinfo='text',
            showlegend=False,
        ), row=1, col=1)

        # Volume as bubble size on profit bars
        fig.add_trace(go.Scatter(
            x=labels, y=profits,
            mode='markers',
            marker=dict(
                size=[max(v * 80, 6) for v in volumes],
                color=colors,
                opacity=0.3,
                line=dict(width=0),
            ),
            hoverinfo='skip',
            showlegend=False,
        ), row=1, col=1)

        # Cumulative P/L line
        cum_color = COLORS['positive'] if cumulative_profit >= 0 else COLORS['negative']
        fig.add_trace(go.Scatter(
            x=labels, y=cum_profits,
            mode='lines+markers+text',
            line=dict(color=cum_color, width=2),
            marker=dict(size=6, color=cum_color),
            text=[f'${c:.0f}' for c in cum_profits],
            textposition='top center',
            textfont=dict(size=9, color=COLORS['text_dim']),
            showlegend=False,
        ), row=2, col=1)

        # Zero line for cumulative
        fig.add_hline(y=0, line_dash='dot', line_color=COLORS['text_dim'],
                       opacity=0.4, row=2, col=1)

        fig.update_layout(
            height=420,
            margin=dict(l=50, r=20, t=30, b=30),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color=COLORS['text'], size=11),
        )
        for i in range(1, 3):
            fig.update_xaxes(showgrid=False, row=i, col=1)
            fig.update_yaxes(
                showgrid=True, gridcolor=COLORS['chart_grid'],
                gridwidth=0.5, zeroline=True,
                zerolinecolor=COLORS['text_dim'], zerolinewidth=0.5,
                row=i, col=1,
            )
        for ann in fig['layout']['annotations']:
            ann['font'] = dict(size=12, color=COLORS['text_dim'])

        chart = dcc.Graph(
            figure=fig,
            config={'displayModeBar': False},
            style={'height': '420px'},
        )
    else:
        chart = html.Div(
            'No closed deals today for this symbol.',
            style={
                'textAlign': 'center', 'color': COLORS['text_dim'],
                'padding': '40px 0', 'fontSize': '14px',
            },
        )

    return html.Div([
        html.H3('📈 Daily Trade Log', style={
            'color': COLORS['text'], 'fontSize': '16px', 'marginBottom': '14px', 'fontWeight': '600',
        }),
        metrics_row,
        html.Div([
            chart,
        ], style={
            'background': COLORS['card'],
            'border': f'1px solid {COLORS["card_border"]}',
            'borderRadius': '12px',
            'padding': '16px',
        }),
    ])


def build_symbol_tab_content(symbol):
    """Build complete content for a single symbol tab"""
    data = load_symbol_data(symbol)

    if data is None:
        # Smooth skeleton placeholder instead of loading screen
        skeleton_bar = lambda w: html.Div(style={
            'height': '14px', 'width': w, 'borderRadius': '6px',
            'background': COLORS['card_border'], 'marginBottom': '10px',
        })
        return html.Div([
            html.Div([
                html.H2(symbol, style={
                    'margin': '0 0 20px 0', 'fontSize': '24px', 'fontWeight': '700',
                    'color': COLORS['text'],
                }),
                html.Div([
                    skeleton_bar('60%'), skeleton_bar('45%'), skeleton_bar('80%'),
                    html.Div(style={'height': '20px'}),
                    skeleton_bar('50%'), skeleton_bar('70%'),
                ]),
                html.Div(f'Connecting to {symbol}...', style={
                    'textAlign': 'center', 'color': COLORS['text_dim'],
                    'fontSize': '13px', 'marginTop': '30px',
                }),
            ], className='skeleton-pulse', style={'marginTop': '30px'}),
        ])

    analysis = data.get('analysis', {})
    last_updated = data.get('last_updated', '')

    # Parse timestamp
    try:
        dt = datetime.fromisoformat(last_updated)
        time_str = dt.strftime('%H:%M:%S')
        date_str = dt.strftime('%d %b %Y')
    except (ValueError, TypeError):
        time_str = '--:--:--'
        date_str = ''

    # Market status
    mkt = data.get('market_status', {})
    mkt_is_open = mkt.get('is_open', False)
    mkt_status = mkt.get('status', 'UNKNOWN')
    mkt_minutes = mkt.get('minutes_since_last')
    mkt_message = mkt.get('message', '')
    mkt_color = COLORS['buy'] if mkt_is_open else COLORS['sell']
    mkt_icon = '🟢' if mkt_is_open else '🔴'
    mkt_sub = f'{mkt_minutes}m since last candle' if mkt_minutes is not None else ''

    return html.Div([
        # Header row
        html.Div([
            html.Div([
                html.H2(symbol, style={
                    'margin': '0', 'fontSize': '24px', 'fontWeight': '700', 'color': COLORS['text'],
                }),
                html.Span(f'{date_str}  •  {time_str}', style={
                    'fontSize': '12px', 'color': COLORS['text_dim'], 'marginLeft': '14px',
                }),
            ], style={'display': 'flex', 'alignItems': 'baseline'}),
            # Market status badge
            html.Div([
                html.Span(f'{mkt_icon} ', style={'fontSize': '14px'}),
                html.Span(mkt_status, style={
                    'background': mkt_color,
                    'color': '#fff',
                    'padding': '4px 14px',
                    'borderRadius': '20px',
                    'fontSize': '12px',
                    'fontWeight': '700',
                    'letterSpacing': '1px',
                }),
                html.Span(f'  {mkt_sub}', style={
                    'fontSize': '11px', 'color': COLORS['text_dim'], 'marginLeft': '8px',
                }) if mkt_sub else None,
            ], style={'display': 'flex', 'alignItems': 'center'}),
        ], style={
            'display': 'flex', 'justifyContent': 'space-between',
            'alignItems': 'center', 'marginBottom': '20px',
        }),

        # Signal section
        build_signal_section(data),

        html.Div(style={'height': '20px'}),

        # Positions section
        build_positions_section(data),

        html.Div(style={'height': '20px'}),

        # Analysis section
        html.Div([
            html.H3('🔬 SHA Indicator Analysis', style={
                'color': COLORS['text'], 'fontSize': '16px', 'marginBottom': '14px', 'fontWeight': '600',
            }),

            # Strength bar
            html.Div([
                html.Div('STRENGTH', style={
                    'fontSize': '11px', 'color': COLORS['text_dim'],
                    'textTransform': 'uppercase', 'letterSpacing': '1px', 'marginBottom': '8px',
                }),
                dcc.Graph(
                    figure=build_sha_strength_chart(analysis),
                    config={'displayModeBar': False},
                    style={'height': '130px'},
                ),
            ], style={
                'background': COLORS['card'],
                'border': f'1px solid {COLORS["card_border"]}',
                'borderRadius': '12px',
                'padding': '16px',
            }),

            html.Div(style={'height': '12px'}),

            # Power lists + Crossover
            html.Div([
                html.Div('CANDLE-BY-CANDLE ANALYSIS (latest → oldest)', style={
                    'fontSize': '11px', 'color': COLORS['text_dim'],
                    'textTransform': 'uppercase', 'letterSpacing': '1px', 'marginBottom': '4px',
                }),
                dcc.Graph(
                    figure=build_power_list_chart(analysis),
                    config={'displayModeBar': False},
                    style={'height': '380px'},
                ),
                build_crossover_legend(),
            ], style={
                'background': COLORS['card'],
                'border': f'1px solid {COLORS["card_border"]}',
                'borderRadius': '12px',
                'padding': '16px',
            }),
        ]),

        html.Div(style={'height': '20px'}),

        # Daily Trade Log section
        build_daily_trades_section(symbol),

        html.Div(style={'height': '20px'}),

        # Raw JSON
        html.Details([
            html.Summary('Raw JSON Data', style={
                'color': COLORS['text_dim'], 'cursor': 'pointer', 'fontSize': '13px',
            }),
            html.Pre(
                json.dumps(data, indent=2, default=str),
                style={
                    'background': COLORS['card'],
                    'border': f'1px solid {COLORS["card_border"]}',
                    'borderRadius': '8px',
                    'padding': '14px',
                    'fontSize': '11px',
                    'color': COLORS['text_dim'],
                    'maxHeight': '300px',
                    'overflow': 'auto',
                    'marginTop': '8px',
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

# Hide the default Dash loading overlay that causes flash on every callback
app.css.append_css({'external_url': ''})
app.index_string = '''<!DOCTYPE html>
<html>
<head>
{%metas%}
<title>{%title%}</title>
{%favicon%}
{%css%}
<style>
._dash-loading-callback { visibility: hidden !important; }
.dash-loading { visibility: hidden !important; }
._dash-loading { visibility: hidden !important; }
div._dash-loading-callback--is-loading { visibility: hidden !important; }

/* Smooth content transitions */
#tab-content {
    animation: fadeIn 0.3s ease-in;
}
@keyframes fadeIn {
    from { opacity: 0.6; }
    to { opacity: 1; }
}
@keyframes pulse {
    0%, 100% { opacity: 0.4; }
    50% { opacity: 1; }
}
.skeleton-pulse {
    animation: pulse 1.5s ease-in-out infinite;
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
    # Auto-refresh (data only, not tabs)
    dcc.Interval(id='refresh-interval', interval=REFRESH_INTERVAL, n_intervals=0),
    # Cache to skip redundant DOM rebuilds
    dcc.Store(id='data-hash', data=''),

    # Header
    html.Div([
        html.Div([
            html.Span('◆', style={'color': COLORS['accent'], 'fontSize': '22px', 'marginRight': '10px'}),
            html.Span('ALCADEIAS', style={
                'fontSize': '20px', 'fontWeight': '700', 'letterSpacing': '3px',
            }),
        ], style={'display': 'flex', 'alignItems': 'center'}),
        html.Div(id='account-info', style={
            'display': 'flex', 'gap': '20px', 'alignItems': 'center',
        }),
        html.Div(id='header-time', style={
            'fontSize': '12px', 'color': COLORS['text_dim'],
        }),
    ], style={
        'display': 'flex',
        'justifyContent': 'space-between',
        'alignItems': 'center',
        'padding': '16px 30px',
        'background': COLORS['header_bg'],
        'borderBottom': f'1px solid {COLORS["card_border"]}',
        'color': COLORS['text'],
    }),

    # Tabs (built once, never rebuilt)
    html.Div(
        dcc.Tabs(
            id='symbol-tabs',
            value=_startup_symbols[0] if _startup_symbols else '',
            children=[
                dcc.Tab(
                    label=s,
                    value=s,
                    style={
                        'background': COLORS['tab_bg'],
                        'color': COLORS['text_dim'],
                        'border': 'none',
                        'borderBottom': '2px solid transparent',
                        'padding': '12px 24px',
                        'fontSize': '13px',
                        'fontWeight': '600',
                        'letterSpacing': '1px',
                    },
                    selected_style={
                        'background': COLORS['bg'],
                        'color': COLORS['text'],
                        'border': 'none',
                        'borderBottom': f'2px solid {COLORS["tab_active"]}',
                        'padding': '12px 24px',
                        'fontSize': '13px',
                        'fontWeight': '700',
                        'letterSpacing': '1px',
                    },
                )
                for s in _startup_symbols
            ],
            style={'borderBottom': f'1px solid {COLORS["card_border"]}'},
        ),
        style={'padding': '0 30px'},
    ),

    # Content (refreshed by callback)
    html.Div(id='tab-content', style={
        'padding': '20px 30px 40px 30px',
        'maxWidth': '1200px',
    }),

], style={
    'background': COLORS['bg'],
    'minHeight': '100vh',
    'fontFamily': "'Inter', 'Segoe UI', -apple-system, sans-serif",
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
        return html.Div('No symbols configured.', style={
            'textAlign': 'center', 'color': COLORS['text_dim'],
            'marginTop': '80px', 'fontSize': '18px',
        }), html.Div(), '', ''

    # Load raw data to check if anything changed
    symbol_data = load_symbol_data(selected_symbol)
    account = load_account_data()
    daily = load_daily_trade_data()
    historical = load_historical_summary()
    
    # Build a quick hash of the data to detect changes
    raw = json.dumps({'s': symbol_data, 'a': account, 'd': daily, 'h': historical}, default=str, sort_keys=True)
    current_hash = hashlib.md5(raw.encode()).hexdigest()
    
    # Check if this is a tab switch or data actually changed
    triggered = callback_context.triggered[0]['prop_id'] if callback_context.triggered else ''
    is_tab_switch = 'symbol-tabs' in triggered
    
    # Skip DOM rebuild if data hasn't changed (interval-only trigger)
    if not is_tab_switch and current_hash == prev_hash:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    
    # Build account info display
    balance = account.get('balance', 0)
    equity = account.get('equity', 0)
    margin = account.get('margin', 0)
    drawdown = account.get('drawdown', 0)
    
    equity_color = COLORS['positive'] if equity >= balance else COLORS['negative']
    drawdown_color = COLORS['negative'] if drawdown > 5 else COLORS['text']
    
    account_display = html.Div([
        html.Div([
            html.Div('Balance', style={'fontSize': '9px', 'color': COLORS['text_dim'], 'textTransform': 'uppercase'}),
            html.Div(f'${balance:,.2f}', style={'fontSize': '14px', 'fontWeight': '700', 'color': COLORS['text']}),
        ], style={'textAlign': 'right'}),
        html.Div([
            html.Div('Equity', style={'fontSize': '9px', 'color': COLORS['text_dim'], 'textTransform': 'uppercase'}),
            html.Div(f'${equity:,.2f}', style={'fontSize': '14px', 'fontWeight': '700', 'color': equity_color}),
        ], style={'textAlign': 'right'}),
        html.Div([
            html.Div('Margin', style={'fontSize': '9px', 'color': COLORS['text_dim'], 'textTransform': 'uppercase'}),
            html.Div(f'${margin:,.2f}', style={'fontSize': '14px', 'fontWeight': '700', 'color': COLORS['text']}),
        ], style={'textAlign': 'right'}),
        html.Div([
            html.Div('Drawdown', style={'fontSize': '9px', 'color': COLORS['text_dim'], 'textTransform': 'uppercase'}),
            html.Div(f'{drawdown:.2f}%', style={'fontSize': '14px', 'fontWeight': '700', 'color': drawdown_color}),
        ], style={'textAlign': 'right'}),
    ], style={'display': 'flex', 'gap': '20px'})
    
    content = build_symbol_tab_content(selected_symbol)
    now = datetime.now().strftime('Last refresh: %H:%M:%S')
    return content, account_display, now, current_hash


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8050)
