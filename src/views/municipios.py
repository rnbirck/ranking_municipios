import dash
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dcc, html
from plotly.subplots import make_subplots

from src.data_loader import get_sector_labels, load_ranking_data


# Página temporariamente fora da navegação/roteamento.
# Mantemos o código aqui para reativação futura sem reconstruir a view.

SECTOR_LABELS = get_sector_labels()
SECTOR_COLUMNS = list(SECTOR_LABELS)
COMPARE_COLORS = ["#007873", "#3f74e0", "#8f52db", "#7b8797"]
TREND_OPTIONS = [{"label": "Total", "value": "nota_final"}] + [
    {"label": label, "value": column} for column, label in SECTOR_LABELS.items()
]


def _fmt_num(value, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"
    return (
        f"{float(value):,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )


def _fmt_delta(value, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"
    sign = "+" if float(value) >= 0 else ""
    return f"{sign}{float(value):.{digits}f}".replace(".", ",")


def _fmt_pos(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{int(value)}º"


def _trend_label(column: str) -> str:
    return "Nota final" if column == "nota_final" else SECTOR_LABELS.get(column, "Indicador")


def _hover_layout(height: int, margin: dict, **kwargs):
    layout = dict(
        height=height,
        margin=margin,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(
            bgcolor="#ffffff",
            bordercolor="#dfe6ec",
            font=dict(
                family="Inter, Segoe UI, Arial, sans-serif",
                size=12,
                color="#102542",
            ),
            align="left",
        ),
        **kwargs,
    )
    return layout


def _icon(name: str, size: int = 24):
    classes = {
        "building": "bi-buildings",
        "radar": "bi-bullseye",
        "line": "bi-graph-up-arrow",
        "rank": "bi-award",
        "trophy": "bi-trophy",
        "trend": "bi-arrow-up-right",
        "star": "bi-star",
        "shield": "bi-shield",
        "table": "bi-table",
        "info": "bi-info-circle",
        "map": "bi-map",
        "network": "bi-diagram-3",
        "book": "bi-book",
        "coin": "bi-coin",
        "tree": "bi-tree",
        "heart": "bi-heart-pulse",
        "security": "bi-shield-check",
        "users": "bi-people",
    }
    return html.I(
        className=f"bi {classes.get(name, classes['building'])}",
        style={"fontSize": f"{size}px"},
    )


def _year_frame(year) -> pd.DataFrame:
    frame = load_ranking_data()
    if year is not None:
        frame = frame[frame["ano"] == year]
    return frame.copy()


def _municipio_options(values):
    return [
        {"label": municipio, "value": municipio, "search": municipio}
        for municipio in values
    ]


def _history_for(names):
    frame = load_ranking_data()
    return frame[frame["municipio"].isin([name for name in names if name])].copy()


def _row_for(frame: pd.DataFrame, municipio: str | None):
    if frame.empty or not municipio:
        return None
    match = frame[frame["municipio"] == municipio]
    if match.empty:
        return None
    return match.iloc[0]


def _previous_row(municipio: str | None, year) -> pd.Series | None:
    if not municipio or year is None:
        return None
    history = load_ranking_data()
    previous = history[(history["ano"] == year - 1) & (history["municipio"] == municipio)]
    if previous.empty:
        return None
    return previous.iloc[0]


def _overall_rank(frame: pd.DataFrame, row) -> int | None:
    if frame.empty or row is None:
        return None
    ranks = frame["nota_final"].rank(method="min", ascending=False).astype("Int64")
    value = ranks.loc[row.name] if row.name in ranks.index else pd.NA
    return int(value) if not pd.isna(value) else None


def _indicator_rank(frame: pd.DataFrame, row, column: str) -> int | None:
    if frame.empty or row is None:
        return None
    ranks = frame[column].rank(method="min", ascending=False).astype("Int64")
    value = ranks.loc[row.name] if row.name in ranks.index else pd.NA
    return int(value) if not pd.isna(value) else None


def _state_average(frame: pd.DataFrame, column: str) -> str:
    if frame.empty:
        return "-"
    return _fmt_num(frame[column].mean())


def _best_and_worst(row):
    if row is None:
        return None, None
    scored = [(column, float(row[column])) for column in SECTOR_COLUMNS]
    best = max(scored, key=lambda item: item[1])
    worst = min(scored, key=lambda item: item[1])
    return best, worst


def _selected_names(selected, comparisons):
    names = [selected, *(comparisons or [])]
    return [name for index, name in enumerate(names) if name and name not in names[:index]]


def _selection_card(row, color: str, selected: bool = False):
    if row is None:
        return html.Div()
    classes = "municipios-selection-card is-selected" if selected else "municipios-selection-card"
    return html.Div(
        [
            html.Div(
                [
                    html.Span(className="municipios-selection-dot", style={"background": color}),
                    html.Div(str(row["municipio"]), className="municipios-selection-name"),
                ],
                className="municipios-selection-top",
            ),
            html.Div(
                [
                    html.Span(str(row["regiao_funcional"]), className="municipios-selection-badge"),
                    html.Span(str(row["corede"]), className="municipios-selection-badge"),
                ],
                className="municipios-selection-meta",
            ),
        ],
        className=classes,
    )


def _selection_placeholder_card():
    return html.Div(
        [
            html.Div(
                [
                    _icon("users", 18),
                    html.Span("Adicionar comparacao", className="municipios-selection-placeholder-title"),
                ],
                className="municipios-selection-placeholder-top",
            ),
            html.P(
                "Use o filtro 'Comparar com' para incluir outros municipios.",
                className="municipios-selection-placeholder-text",
            ),
        ],
        className="municipios-selection-card municipios-selection-card-placeholder",
    )


def _empty_figure(message: str):
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font=dict(size=13, color="#5d6b7e"),
    )
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False)
    figure.update_layout(height=290, margin=dict(l=12, r=12, t=12, b=12))
    return figure


def _trend_history_title(trend_mode: str, trend_column: str) -> str:
    metric_label = _trend_label(trend_column)
    if trend_mode == "rank":
        return "Evolução da posição geral" if trend_column == "nota_final" else f"Evolução da posição em {metric_label}"
    return "Evolução da nota final" if trend_column == "nota_final" else f"Evolução da nota em {metric_label}"


def _trend_history_figure(selected, comparisons, trend_column, trend_mode):
    names = _selected_names(selected, comparisons)
    history = _history_for(names)
    if history.empty or not selected:
        return _empty_figure("Selecione um município para visualizar a evolução.")

    metric_label = _trend_label(trend_column)
    figure = go.Figure()

    if trend_mode == "rank":
        statewide = load_ranking_data()
        max_rank = statewide.groupby("ano")["municipio"].nunique().max()
        for index, name in enumerate(names):
            data = history[history["municipio"] == name].sort_values("ano").copy()
            if data.empty:
                continue
            ranks = []
            for _, row in data.iterrows():
                year_frame = statewide[statewide["ano"] == row["ano"]]
                if trend_column == "nota_final":
                    year_ranks = year_frame["nota_final"].rank(method="min", ascending=False).astype("Int64")
                    value = year_ranks.loc[row.name] if row.name in year_ranks.index else pd.NA
                    ranks.append(int(value) if not pd.isna(value) else None)
                else:
                    ranks.append(_indicator_rank(year_frame, row, trend_column))
            data["trend_value"] = ranks
            figure.add_trace(
                go.Scatter(
                    x=data["ano"],
                    y=data["trend_value"],
                    customdata=[_fmt_pos(value) for value in data["trend_value"]],
                    mode="lines+markers+text",
                    text=[_fmt_pos(value) for value in data["trend_value"]],
                    textposition="top center",
                    name=name,
                    line=dict(color=COMPARE_COLORS[index % len(COMPARE_COLORS)], width=3 if index == 0 else 2),
                    marker=dict(size=7),
                    hovertemplate=f"<b>%{{fullData.name}}</b><br>Ano %{{x}}<br>Posição em {metric_label}: %{{customdata}}<extra></extra>",
                )
            )
        figure.update_layout(
            **_hover_layout(
                height=332,
                margin=dict(l=18, r=20, t=36, b=28),
                yaxis=dict(
                    autorange="reversed",
                    range=[max_rank + 8, 1],
                    showticklabels=False,
                    ticks="",
                    showline=False,
                    zeroline=False,
                    gridcolor="#e5ebef",
                    fixedrange=True,
                ),
                xaxis=dict(tickmode="linear", showgrid=False, color="#102542"),
                legend=dict(orientation="h", y=1.14, x=0.5, xanchor="center"),
                showlegend=True,
            )
        )
        return figure

    y_values = history[trend_column].dropna()
    y_min = float(y_values.min()) if not y_values.empty else 0
    y_max = float(y_values.max()) if not y_values.empty else 10
    span = max(y_max - y_min, 0.9)
    y_range = [max(0, y_min - span * 0.2), min(10, y_max + span * 0.2)]
    for index, name in enumerate(names):
        data = history[history["municipio"] == name].sort_values("ano")
        if data.empty:
            continue
        figure.add_trace(
            go.Scatter(
                x=data["ano"],
                y=data[trend_column],
                customdata=[_fmt_num(value) for value in data[trend_column]],
                mode="lines+markers+text",
                text=[_fmt_num(value) for value in data[trend_column]],
                textposition="top center",
                name=name,
                line=dict(color=COMPARE_COLORS[index % len(COMPARE_COLORS)], width=3 if index == 0 else 2),
                marker=dict(size=7),
                hovertemplate=f"<b>%{{fullData.name}}</b><br>Ano %{{x}}<br>{metric_label}: %{{customdata}}<extra></extra>",
            )
        )
    figure.update_layout(
        **_hover_layout(
            height=332,
            margin=dict(l=18, r=20, t=36, b=28),
            yaxis=dict(
                range=y_range,
                showticklabels=False,
                ticks="",
                showline=False,
                zeroline=False,
                gridcolor="#e5ebef",
                fixedrange=True,
            ),
            xaxis=dict(tickmode="linear", showgrid=False, color="#102542"),
            legend=dict(orientation="h", y=1.14, x=0.5, xanchor="center"),
            showlegend=True,
        )
    )
    return figure


def _radar_figure(year_frame, selected, comparisons, radar_mode):
    if year_frame.empty or not selected:
        return _empty_figure("Selecione um município para comparar perfis.")

    names = _selected_names(selected, comparisons)[:3]
    labels = [SECTOR_LABELS[column] for column in SECTOR_COLUMNS]
    labels_closed = labels + [labels[0]]
    state_values = [float(year_frame[column].mean()) for column in SECTOR_COLUMNS]

    if radar_mode == "side_by_side" and len(names) > 1:
        figure = make_subplots(
            rows=1,
            cols=len(names),
            specs=[[{"type": "polar"} for _ in names]],
            subplot_titles=names,
            horizontal_spacing=0.08,
        )
        polar_layout = dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(
                range=[0, 10],
                tickvals=[0, 2.5, 5, 7.5, 10],
                tickfont=dict(size=10, color="#708095"),
                gridcolor="#dfe7ed",
            ),
            angularaxis=dict(
                tickfont=dict(size=10, color="#102542"),
                gridcolor="#dfe7ed",
            ),
        )

        for index, name in enumerate(names, start=1):
            row = _row_for(year_frame, name)
            if row is None:
                continue
            values = [float(row[column]) for column in SECTOR_COLUMNS]
            color = COMPARE_COLORS[(index - 1) % len(COMPARE_COLORS)]
            fill_color = f"rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, 0.10)"
            figure.add_trace(
                go.Scatterpolar(
                    r=values + [values[0]],
                    theta=labels_closed,
                    customdata=[_fmt_num(value) for value in values + [values[0]]],
                    mode="lines+markers",
                    name=name,
                    legendgroup=name,
                    line=dict(color=color, width=3),
                    marker=dict(size=6),
                    fill="toself",
                    fillcolor=fill_color,
                    hovertemplate="<b>%{fullData.name}</b><br>%{theta}: %{customdata}<extra></extra>",
                ),
                row=1,
                col=index,
            )
            figure.add_trace(
                go.Scatterpolar(
                    r=state_values + [state_values[0]],
                    theta=labels_closed,
                    customdata=[_fmt_num(value) for value in state_values + [state_values[0]]],
                    mode="lines+markers",
                    name="Média do RS",
                    legendgroup="media-rs",
                    showlegend=index == 1,
                    line=dict(color="#8a97a8", width=2, dash="dash"),
                    marker=dict(size=5),
                    hovertemplate="<b>%{fullData.name}</b><br>%{theta}: %{customdata}<extra></extra>",
                ),
                row=1,
                col=index,
            )

        layout_updates = {
            "polar": polar_layout,
            "legend": dict(orientation="h", y=1.14, x=0.5, xanchor="center"),
            "showlegend": True,
        }
        if len(names) > 1:
            layout_updates["polar2"] = polar_layout
        if len(names) > 2:
            layout_updates["polar3"] = polar_layout

        figure.update_layout(
            **_hover_layout(
                height=430,
                margin=dict(l=10, r=10, t=52, b=10),
                **layout_updates,
            )
        )
        return figure

    figure = go.Figure()
    for index, name in enumerate(names):
        row = _row_for(year_frame, name)
        if row is None:
            continue
        values = [float(row[column]) for column in SECTOR_COLUMNS]
        figure.add_trace(
            go.Scatterpolar(
                r=values + [values[0]],
                theta=labels_closed,
                customdata=[_fmt_num(value) for value in values + [values[0]]],
                mode="lines+markers",
                name=name,
                line=dict(color=COMPARE_COLORS[index % len(COMPARE_COLORS)], width=3 if index == 0 else 2),
                marker=dict(size=6),
                fill="toself" if index == 0 else None,
                fillcolor="rgba(0, 120, 115, 0.08)" if index == 0 else None,
                hovertemplate="<b>%{fullData.name}</b><br>%{theta}: %{customdata}<extra></extra>",
            )
        )

    figure.add_trace(
        go.Scatterpolar(
            r=state_values + [state_values[0]],
            theta=labels_closed,
            customdata=[_fmt_num(value) for value in state_values + [state_values[0]]],
            mode="lines+markers",
            name="Média do RS",
            line=dict(color="#8a97a8", width=2, dash="dash"),
            marker=dict(size=5),
            hovertemplate="<b>%{fullData.name}</b><br>%{theta}: %{customdata}<extra></extra>",
        )
    )

    figure.update_layout(
        **_hover_layout(
            height=470,
            margin=dict(l=16, r=16, t=26, b=16),
            polar=dict(
                bgcolor="rgba(0,0,0,0)",
                radialaxis=dict(
                    range=[0, 10],
                    tickvals=[0, 2.5, 5, 7.5, 10],
                    tickfont=dict(size=10, color="#708095"),
                    gridcolor="#dfe7ed",
                ),
                angularaxis=dict(
                    tickfont=dict(size=11, color="#102542"),
                    gridcolor="#dfe7ed",
                ),
            ),
            legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"),
            showlegend=True,
        )
    )
    return figure


def _variation_cell(value):
    if value is None or pd.isna(value):
        return html.Td("-")
    class_name = "positive" if value > 0 else "negative" if value < 0 else ""
    arrow = "↑ " if value > 0 else "↓ " if value < 0 else ""
    return html.Td(f"{arrow}{_fmt_delta(value)}", className=class_name)


def _comparison_table(year_frame, selected, comparisons, year):
    names = _selected_names(selected, comparisons)[:3]
    if year_frame.empty or not names:
        return html.Div("Selecione um município para comparar indicadores.", className="empty-state")

    previous_frame = _year_frame(year - 1) if year else pd.DataFrame()
    header_top = [html.Th("Indicador", rowSpan=2)]
    for name in names:
        header_top.append(html.Th(name, colSpan=3))
    header_top.append(html.Th("Média do RS", rowSpan=2))

    header_bottom = []
    for _ in names:
        header_bottom.extend([html.Th("Nota (0-10)"), html.Th("Posição"), html.Th("Variação")])

    rows = []
    icon_map = {
        "nota_educacao": "book",
        "nota_financas": "coin",
        "nota_meio_ambiente": "tree",
        "nota_saude": "heart",
        "nota_seguranca": "security",
        "nota_socioeconomico": "users",
        "nota_final": "trophy",
    }
    row_labels = {**SECTOR_LABELS, "nota_final": "Nota final"}

    for column, label in row_labels.items():
        cells = [
            html.Td(
                [_icon(icon_map[column], 16), html.Span(label)],
                className="municipios-compare-indicator",
            )
        ]
        for name in names:
            row = _row_for(year_frame, name)
            prev = _row_for(previous_frame, name)
            if row is None:
                cells.extend([html.Td("-"), html.Td("-"), html.Td("-")])
                continue
            if column == "nota_final":
                position = _overall_rank(year_frame, row)
            else:
                position = _indicator_rank(year_frame, row, column)
            delta = None
            if prev is not None and column in prev:
                delta = float(row[column] - prev[column])
            cells.extend(
                [
                    html.Td(_fmt_num(row[column])),
                    html.Td(_fmt_pos(position)),
                    _variation_cell(delta),
                ]
            )
        cells.append(html.Td(_state_average(year_frame, column)))
        rows.append(html.Tr(cells, className="is-total" if column == "nota_final" else ""))

    return html.Table(
        [
            html.Thead([html.Tr(header_top), html.Tr(header_bottom)]),
            html.Tbody(rows),
        ],
        className="municipios-compare-table",
    )


def _insights(year_frame, selected, comparisons, year):
    names = _selected_names(selected, comparisons)
    row = _row_for(year_frame, selected)
    previous = _previous_row(selected, year)
    if row is None:
        return html.Div("Selecione um município para abrir os destaques.", className="empty-state")

    best, worst = _best_and_worst(row)
    better_count = 0
    if len(names) > 1:
        for column in SECTOR_COLUMNS:
            current_value = float(row[column])
            peer_values = []
            for peer in names[1:]:
                peer_row = _row_for(year_frame, peer)
                if peer_row is not None:
                    peer_values.append(float(peer_row[column]))
            if peer_values and current_value >= max(peer_values):
                better_count += 1

    delta = None
    if previous is not None:
        delta = float(row["nota_final"] - previous["nota_final"])

    items = [
        ("trend", f"{selected} lidera em {better_count} indicadores dentro do conjunto comparado." if len(names) > 1 else f"{selected} é o município principal da comparação."),
        ("star", f"Melhor indicador atual: {SECTOR_LABELS[best[0]]} com {_fmt_num(best[1])}." if best else "Sem destaque calculado."),
        ("shield", f"Indicador mais frágil: {SECTOR_LABELS[worst[0]]} com {_fmt_num(worst[1])}." if worst else "Sem fragilidade calculada."),
        ("line", f"Variação anual da nota final: {_fmt_delta(delta)}." if delta is not None else "Sem variação anual disponível."),
    ]
    return html.Div(
        [
            html.Div(
                [_icon(icon_name, 18), html.Div(text, className="municipios-insight-text")],
                className="municipios-insight-item",
            )
            for icon_name, text in items
        ],
        className="municipios-insight-list",
    )


layout = html.Div(
    [
        html.Section(
            [
                html.Div(
                    [
                        html.Div(_icon("building", 46), className="municipios-hero-icon"),
                        html.Div(
                            [
                                html.H1("Municípios", className="municipios-title"),
                                html.P(
                                    "Compare trajetórias, notas e perfis de indicadores entre municípios selecionados.",
                                    className="municipios-subtitle",
                                ),
                            ],
                            className="municipios-hero-copy",
                        ),
                    ],
                    className="municipios-hero-head",
                ),
                html.Div(
                    [
                        html.Div("Comparar com", className="filter-label"),
                        dcc.Dropdown(
                            id="municipios-compare",
                            placeholder="Adicionar municípios",
                            multi=True,
                            className="filter-control",
                        ),
                    ],
                    className="municipios-hero-compare",
                ),
            ],
            className="municipios-hero municipios-redesign-hero",
        ),
        html.Section(id="municipios-selection-strip", className="municipios-selection-strip"),
        html.Section(
            [
                html.Article(
                    [
                        html.Div(_icon("trophy", 28), className="municipios-metric-icon"),
                        html.Div(
                            [
                                html.Div("Nota final (2025)", id="municipio-score-title", className="municipios-metric-heading"),
                                html.Div(id="municipio-score", className="municipios-metric-value"),
                                html.Div(id="municipio-score-footnote", className="municipios-metric-footnote"),
                            ]
                        ),
                    ],
                    className="municipios-metric-card emphasis",
                ),
                html.Article(
                    [
                        html.Div(_icon("rank", 28), className="municipios-metric-icon"),
                        html.Div(
                            [
                                html.Div("Posição geral (2025)", className="municipios-metric-heading"),
                                html.Div(id="municipio-rank", className="municipios-metric-value"),
                                html.Div(id="municipio-rank-footnote", className="municipios-metric-footnote"),
                            ]
                        ),
                    ],
                    className="municipios-metric-card",
                ),
                html.Article(
                    [
                        html.Div(_icon("trend", 28), className="municipios-metric-icon"),
                        html.Div(
                            [
                                html.Div("Variação anual", className="municipios-metric-heading"),
                                html.Div(id="municipio-delta", className="municipios-metric-value"),
                                html.Div(id="municipio-delta-footnote", className="municipios-metric-footnote"),
                            ]
                        ),
                    ],
                    className="municipios-metric-card",
                ),
                html.Article(
                    [
                        html.Div(_icon("star", 28), className="municipios-metric-icon"),
                        html.Div(
                            [
                                html.Div("Melhor indicador", className="municipios-metric-heading"),
                                html.Div(id="municipio-best-label", className="municipios-metric-value small"),
                                html.Div(id="municipio-best-value", className="municipios-metric-footnote"),
                            ]
                        ),
                    ],
                    className="municipios-metric-card",
                ),
                html.Article(
                    [
                        html.Div(_icon("shield", 28), className="municipios-metric-icon"),
                        html.Div(
                            [
                                html.Div("Indicador mais frágil", className="municipios-metric-heading"),
                                html.Div(id="municipio-weak-label", className="municipios-metric-value small"),
                                html.Div(id="municipio-weak-value", className="municipios-metric-footnote"),
                            ]
                        ),
                    ],
                    className="municipios-metric-card",
                ),
            ],
            className="municipios-metrics municipios-metrics-wide",
        ),
        html.Section(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div([_icon("radar", 18), html.Span("Perfil de indicadores (2025)")], className="chart-title"),
                                dcc.RadioItems(
                                    id="municipio-radar-mode",
                                    options=[
                                        {"label": "Sobreposto", "value": "overlay"},
                                        {"label": "Lado a lado", "value": "side_by_side"},
                                    ],
                                    value="overlay",
                                    inline=True,
                                    className="municipios-radar-mode",
                                    inputClassName="municipios-radar-mode-input",
                                    labelClassName="municipios-radar-mode-option",
                                ),
                            ],
                            className="municipios-radar-header",
                        ),
                        dcc.Graph(id="municipio-radar", config={"displayModeBar": False}),
                    ],
                    className="chart-card municipios-radar-card",
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(id="municipio-trend-history-title", className="chart-title"),
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                html.Div("Visualização", className="municipios-trend-label"),
                                                dcc.RadioItems(
                                                    id="municipio-trend-mode",
                                                    options=[
                                                        {"label": "Nota", "value": "score"},
                                                        {"label": "Posição", "value": "rank"},
                                                    ],
                                                    value="score",
                                                    inline=True,
                                                    className="municipios-radar-mode",
                                                    inputClassName="municipios-radar-mode-input",
                                                    labelClassName="municipios-radar-mode-option",
                                                ),
                                            ],
                                            className="municipios-trend-filter municipios-trend-filter-radio",
                                        ),
                                        html.Div(
                                            [
                                                html.Div("Categoria", className="municipios-trend-label"),
                                                dcc.Dropdown(
                                                    id="municipio-trend-category",
                                                    options=TREND_OPTIONS,
                                                    value="nota_final",
                                                    clearable=False,
                                                    searchable=False,
                                                    className="filter-control municipios-trend-select",
                                                ),
                                            ],
                                            className="municipios-trend-filter",
                                        ),
                                    ],
                                    className="municipios-trends-controls",
                                ),
                            ],
                            className="municipios-trends-header",
                        ),
                        dcc.Graph(id="municipio-trend-history", config={"displayModeBar": False}),
                    ],
                    className="chart-card municipios-trends-card",
                ),
            ],
            className="municipios-top-analytics",
        ),
        html.Section(
            [
                html.Div(
                    [
                        html.Div([_icon("table", 18), html.Span("Comparativo de indicadores (2025)")], className="chart-title"),
                        html.Div(id="municipios-comparison-table", className="municipios-table-shell"),
                    ],
                    className="chart-card municipios-compare-card",
                ),
            ],
            className="municipios-bottom-grid",
        ),
    ],
    className="page municipios-page municipios-redesign",
)


@callback(
    Output("municipios-compare", "options"),
    Output("municipios-compare", "value"),
    Input("filter-ano", "value"),
    Input("filter-municipio", "value"),
    State("municipios-compare", "value"),
)
def update_compare_options(year, selected_municipio, current_compare):
    frame = _year_frame(year)
    municipalities = sorted(frame["municipio"].dropna().astype(str).unique()) if not frame.empty else []
    compare_options = [municipio for municipio in municipalities if municipio != selected_municipio]
    compare_values = [value for value in (current_compare or []) if value in compare_options][:3]
    return _municipio_options(compare_options), compare_values


@callback(
    Output("municipios-selection-strip", "children"),
    Output("municipio-score", "children"),
    Output("municipio-score-footnote", "children"),
    Output("municipio-rank", "children"),
    Output("municipio-rank-footnote", "children"),
    Output("municipio-delta", "children"),
    Output("municipio-delta-footnote", "children"),
    Output("municipio-best-label", "children"),
    Output("municipio-best-value", "children"),
    Output("municipio-weak-label", "children"),
    Output("municipio-weak-value", "children"),
    Output("municipio-radar", "figure"),
    Output("municipio-trend-history-title", "children"),
    Output("municipio-trend-history", "figure"),
    Output("municipios-comparison-table", "children"),
    Input("filter-ano", "value"),
    Input("filter-municipio", "value"),
    Input("municipios-compare", "value"),
    Input("municipio-radar-mode", "value"),
    Input("municipio-trend-mode", "value"),
    Input("municipio-trend-category", "value"),
)
def update_municipios_page(year, selected_municipio, comparisons, radar_mode, trend_mode, trend_category):
    frame = _year_frame(year)
    comparisons = comparisons or []
    selected_row = _row_for(frame, selected_municipio)
    previous_row = _previous_row(selected_municipio, year)

    strip_names = _selected_names(selected_municipio, comparisons)
    strip_rows = [_row_for(frame, name) for name in strip_names]
    strip_children = [
        _selection_card(row, COMPARE_COLORS[index % len(COMPARE_COLORS)], selected=index == 0)
        for index, row in enumerate(strip_rows)
        if row is not None
    ]
    if not strip_children:
        strip_children = [
            html.Div(
                "Selecione um município principal no filtro superior para começar a comparação.",
                className="empty-state",
            )
        ]
    else:
        while len(strip_children) < 4:
            strip_children.append(_selection_placeholder_card())

    if selected_row is None:
        empty = _empty_figure("Selecione um município principal.")
        return (
            strip_children,
            "-",
            "Selecione um município",
            "-",
            "Sem posição calculada",
            "-",
            "Sem histórico anterior",
            "-",
            "-",
            "-",
            "-",
            empty,
            empty,
            "Evolução da nota final",
            html.Div("Selecione um município para abrir o comparativo.", className="empty-state"),
        )

    statewide_total = frame["municipio"].nunique()
    score = _fmt_num(selected_row["nota_final"])
    overall_rank = _overall_rank(frame, selected_row)
    rank_text = _fmt_pos(overall_rank)
    delta = None
    if previous_row is not None and previous_row["nota_final"] is not None and not pd.isna(previous_row["nota_final"]):
        delta = float(selected_row["nota_final"] - previous_row["nota_final"])
    best, worst = _best_and_worst(selected_row)
    trend_mode = trend_mode or "score"
    trend_category = trend_category or "nota_final"
    trend_title = _trend_history_title(trend_mode, trend_category)

    return (
        strip_children,
        score,
        str(selected_row["municipio"]),
        rank_text,
        f"entre {statewide_total} municípios",
        _fmt_delta(delta),
        f"{year - 1} → {year}" if year else "Variação anual",
        SECTOR_LABELS[best[0]] if best else "-",
        f"{_fmt_num(best[1])} / 10" if best else "-",
        SECTOR_LABELS[worst[0]] if worst else "-",
        f"{_fmt_num(worst[1])} / 10" if worst else "-",
        _radar_figure(frame, selected_municipio, comparisons, radar_mode),
        trend_title,
        _trend_history_figure(selected_municipio, comparisons, trend_category, trend_mode),
        _comparison_table(frame, selected_municipio, comparisons, year),
    )
