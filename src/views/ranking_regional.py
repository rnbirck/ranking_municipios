import re
from urllib.parse import urlencode

import unicodedata

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, callback, clientside_callback, ctx, dash_table, dcc, html

from src.data_loader import filter_ranking_data, get_sector_labels, load_ranking_data


dash.register_page(__name__, path="/ranking-regional", name="Regiões funcionais")

SECTOR_LABELS = get_sector_labels()
SECTOR_COLUMNS = list(SECTOR_LABELS)


def _fmt_num(value, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"
    return (
        f"{float(value):,.{digits}f}".replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def _fmt_delta(value, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"
    sign = "+" if float(value) >= 0 else ""
    return f"{sign}{float(value):.{digits}f}".replace(".", ",")


def _fmt_pos_delta(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    value = int(value)
    if value == 0:
        return "0"
    return f"+{value}" if value > 0 else str(value)


def _classification_status(value) -> str:
    text = "" if value is None or pd.isna(value) else str(value).strip()
    normalized = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    if "acima" in normalized:
        return "above"
    if "baixo" in normalized or "abaixo" in normalized:
        return "low"
    if "intervalo" in normalized or "dentro" in normalized or "esperado" in normalized:
        return "range"
    return "neutral" if text else "missing"


def _classification_label(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    text = str(value).strip()
    return text if text else "-"


def _classification_datatable_styles() -> list[dict]:
    return [
        {
            "if": {"column_id": "classificacao"},
            "fontWeight": "800",
            "borderRadius": "6px",
        },
        {
            "if": {
                "filter_query": '{classificacao_status} = "above"',
                "column_id": "classificacao",
            },
            "backgroundColor": "#e7f6ef",
            "color": "#06724f",
        },
        {
            "if": {
                "filter_query": '{classificacao_status} = "range"',
                "column_id": "classificacao",
            },
            "backgroundColor": "#fff3cf",
            "color": "#8a5a12",
        },
        {
            "if": {
                "filter_query": '{classificacao_status} = "low"',
                "column_id": "classificacao",
            },
            "backgroundColor": "#fde8e8",
            "color": "#b4232d",
        },
    ]


def _hover_layout(height=None, margin=None, **kwargs):
    layout = dict(
        hoverlabel=dict(
            bgcolor="#ffffff",
            bordercolor="#dfe6ec",
            font=dict(
                family="Inter, Segoe UI, Arial, sans-serif", size=12, color="#102542"
            ),
            align="left",
        ),
        **kwargs,
    )
    if height is not None:
        layout["height"] = height
    if margin is not None:
        layout["margin"] = margin
    return layout


def _region_code(region: str | None) -> str:
    if not region:
        return "região"
    match = re.search(r"RF\s*\d+|RF\d+", region, re.IGNORECASE)
    if match:
        return match.group(0).replace(" ", "").upper()
    return region.split("—")[0].split("-")[0].strip()


def _region_sort_value(region: str) -> tuple[int, str]:
    match = re.search(r"(\d+)", region or "")
    if match:
        return int(match.group(1)), region
    return 999, region or ""


def _icon(name: str, size: int = 34):
    classes = {
        "bars": "bi-bar-chart",
        "building": "bi-buildings",
        "star": "bi-star",
        "network": "bi-diagram-3",
        "trophy": "bi-trophy",
        "book": "bi-book",
        "coin": "bi-coin",
        "leaf": "bi-tree",
        "heart": "bi-heart-pulse",
        "shield": "bi-shield-check",
        "users": "bi-people",
        "bulb": "bi-lightbulb",
        "scale": "bi-sliders",
        "method": "bi-journal-text",
        "map": "bi-map",
        "calendar": "bi-calendar3",
        "table": "bi-table",
        "info": "bi-info-circle",
    }
    return html.I(
        className=f"bi {classes.get(name, classes['bars'])}",
        style={"fontSize": f"{size}px"},
    )


def _empty_figure(message: str) -> go.Figure:
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
    figure.update_layout(margin=dict(l=10, r=10, t=10, b=10))
    return figure


def _rank_series(frame: pd.DataFrame, column: str):
    return frame[column].rank(method="min", ascending=False).astype("Int64")


def _previous_frame(year: int | None, region: str | None, corede: str | None = None):
    if year is None:
        return pd.DataFrame()
    history = load_ranking_data()
    prev_years = sorted(
        history.loc[history["ano"] < int(year), "ano"].dropna().astype(int).unique()
    )
    if not prev_years:
        return pd.DataFrame()
    previous = history[history["ano"] == prev_years[-1]].copy()
    if region:
        previous = previous[previous["regiao_funcional"] == region]
    if corede:
        previous = previous[previous["corede"] == corede]
    return previous


def _prepare_scope(year, region, corede):
    frame = filter_ranking_data(ano=year, regiao_funcional=region)
    if corede:
        frame = frame[frame["corede"] == corede]
    return frame.sort_values(
        ["ranking_regiao_funcional", "nota_final", "municipio"],
        ascending=[True, False, True],
    ).copy()


def _build_region_summary_data(year):
    frame = filter_ranking_data(ano=year)
    if frame.empty:
        return []

    rows = []
    for region, group in frame.groupby("regiao_funcional", dropna=True):
        coredes = sorted(
            group["corede"].replace("", pd.NA).dropna().astype(str).unique()
        )
        rows.append(
            {
                "regiao": region,
                "municipios": int(group["municipio"].nunique()),
                "coredes_count": len(coredes),
                "coredes": ", ".join(coredes),
                "nota_final": _fmt_num(group["nota_final"].mean()),
            }
        )
    return sorted(rows, key=lambda item: _region_sort_value(item["regiao"]))


def _build_region_summary_table(rows):
    if not rows:
        return html.Div(
            "Não há dados regionais para o ano selecionado.", className="empty-state"
        )
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        html.Span(row["regiao"], className="region-explore-badge"),
                        className="region-explore-col region-explore-col--badge",
                    ),
                    html.Div(
                        [
                            html.Div(
                                str(row["municipios"]),
                                className="region-explore-metric-value",
                            ),
                            html.Div(
                                "municípios",
                                className="region-explore-metric-label",
                            ),
                        ],
                        className="region-explore-col region-explore-col--metric",
                    ),
                    html.Div(
                        [
                            html.Div(
                                str(row["coredes_count"]),
                                className="region-explore-metric-value",
                            ),
                            html.Div(
                                "Coredes",
                                className="region-explore-metric-label",
                            ),
                        ],
                        className="region-explore-col region-explore-col--metric",
                    ),
                    html.Div(
                        [
                            html.Div(
                                "Coredes",
                                className="region-explore-coredes-label",
                            ),
                            html.Div(
                                row["coredes"],
                                className="region-explore-coredes-text",
                            ),
                        ],
                        className="region-explore-col region-explore-col--coredes",
                    ),
                    html.Div(
                        html.Span("Explorar região", className="region-explore-cta"),
                        className="region-explore-col region-explore-col--cta",
                    ),
                ],
                className="region-explore-card",
                id={"type": "regional-overview-card", "region": row["regiao"]},
                n_clicks=0,
                title=f"Selecionar {row['regiao']}",
            )
            for row in rows
        ],
        className="region-explore-list",
    )


def _focus_row(scope: pd.DataFrame, municipio: str | None):
    if scope.empty or not municipio:
        return None
    selected = scope[scope["municipio"] == municipio]
    if not selected.empty:
        return selected.iloc[0]
    return None


def _build_ranking_data(scope: pd.DataFrame, previous: pd.DataFrame):
    previous_lookup = (
        previous.set_index("municipio") if not previous.empty else pd.DataFrame()
    )
    rows = []
    for _, row in scope.iterrows():
        prev_score = (
            previous_lookup.loc[row["municipio"], "nota_final"]
            if row["municipio"] in previous_lookup.index
            else None
        )
        prev_rank = (
            previous_lookup.loc[row["municipio"], "ranking_regiao_funcional"]
            if row["municipio"] in previous_lookup.index
            else None
        )
        delta_score = (
            float(row["nota_final"] - prev_score)
            if prev_score is not None and not pd.isna(prev_score)
            else None
        )
        delta_rank = (
            int(prev_rank - row["ranking_regiao_funcional"])
            if prev_rank is not None and not pd.isna(prev_rank)
            else None
        )
        rows.append(
            {
                "star": "*" if int(row["ranking_regiao_funcional"]) == 1 else "",
                "posicao": int(row["ranking_regiao_funcional"]),
                "municipio": row["municipio"],
                "corede": row["corede"],
                "classificacao": _classification_label(row.get("classificacao")),
                "classificacao_status": _classification_status(
                    row.get("classificacao")
                ),
                "nota_final": _fmt_num(row["nota_final"]),
                "delta_nota": _fmt_delta(delta_score),
                "delta_posicao": _fmt_pos_delta(delta_rank),
            }
        )
    return rows


def _selected_name_with_corede(name: str, corede: str | None):
    clean_corede = (
        str(corede).strip() if corede is not None and not pd.isna(corede) else ""
    )
    if not clean_corede:
        return name
    return [
        html.Span(name, className="selected-name-text"),
        html.Span(clean_corede, className="selected-corede"),
    ]


def _indicator_rows(scope: pd.DataFrame, row, previous: pd.DataFrame):
    if row is None or scope.empty:
        return []

    prev_row = None
    if not previous.empty:
        match = previous[previous["municipio"] == row["municipio"]]
        if not match.empty:
            prev_row = match.iloc[0]

    rows = []
    icons = {
        "nota_educacao": "book",
        "nota_financas": "coin",
        "nota_meio_ambiente": "leaf",
        "nota_saude": "heart",
        "nota_seguranca": "shield",
        "nota_socioeconomico": "users",
        "nota_final": "bars",
    }
    sector_scope = scope.copy()
    for column, label in {**SECTOR_LABELS, "nota_final": "Ranking geral"}.items():
        ranks = _rank_series(sector_scope, column)
        position = (
            int(ranks.loc[row.name])
            if row.name in ranks.index and not pd.isna(ranks.loc[row.name])
            else "-"
        )
        delta_note = None
        delta_pos = None
        if prev_row is not None:
            delta_note = float(row[column] - prev_row[column])
            prev_ranks = _rank_series(previous, column)
            prev_match = previous[previous["municipio"] == row["municipio"]]
            if not prev_match.empty:
                prev_index = prev_match.index[0]
                if (
                    prev_index in prev_ranks.index
                    and not pd.isna(prev_ranks.loc[prev_index])
                    and position != "-"
                ):
                    delta_pos = int(prev_ranks.loc[prev_index] - position)
        rows.append(
            html.Tr(
                [
                    html.Td(
                        [
                            _icon(icons[column], 17),
                            html.Span(label, style={"marginLeft": "9px"}),
                        ]
                    ),
                    html.Td(_fmt_num(row[column])),
                    html.Td(f"{position}º" if position != "-" else "-"),
                    html.Td(
                        f"↑ {_fmt_delta(delta_note)}"
                        if delta_note is not None and delta_note >= 0
                        else f"↓ {_fmt_delta(delta_note)}"
                        if delta_note is not None
                        else "-",
                        className="positive"
                        if delta_note is not None and delta_note >= 0
                        else "negative"
                        if delta_note is not None
                        else "",
                    ),
                    html.Td(
                        f"↑ {_fmt_pos_delta(delta_pos)}"
                        if delta_pos is not None and delta_pos >= 0
                        else f"↓ {_fmt_pos_delta(delta_pos)}"
                        if delta_pos is not None
                        else "-",
                        className="positive"
                        if delta_pos is not None and delta_pos >= 0
                        else "negative"
                        if delta_pos is not None
                        else "",
                    ),
                ],
                className="is-total" if column == "nota_final" else "",
            )
        )
    return rows


def _detail_table(
    scope: pd.DataFrame, row, previous: pd.DataFrame, region_code: str, year
):
    if row is None:
        return html.Div(
            "Selecione um município para ver os indicadores.", className="empty-state"
        )
    return html.Table(
        [
            html.Thead(
                html.Tr(
                    [
                        html.Th("Indicador"),
                        html.Th(f"Nota {year}"),
                        html.Th(f"Posição na {region_code}"),
                        html.Th("Δ nota"),
                        html.Th("Δ posição"),
                    ]
                )
            ),
            html.Tbody(_indicator_rows(scope, row, previous)),
        ],
        className="detail-table",
    )


def _radar_figure(scope: pd.DataFrame, row) -> go.Figure:
    if row is None or scope.empty:
        return _empty_figure("Selecione um município.")

    labels = [SECTOR_LABELS[column] for column in SECTOR_COLUMNS]
    municipio_values = [float(row[column]) for column in SECTOR_COLUMNS]
    media_values = [float(scope[column].mean()) for column in SECTOR_COLUMNS]
    labels_closed = labels + [labels[0]]

    figure = go.Figure()
    figure.add_trace(
        go.Scatterpolar(
            r=municipio_values + [municipio_values[0]],
            theta=labels_closed,
            customdata=[
                _fmt_num(value) for value in municipio_values + [municipio_values[0]]
            ],
            mode="lines+markers",
            name=str(row["municipio"]),
            line=dict(color="#007873", width=3),
            marker=dict(size=8, color="#007873"),
            fill="toself",
            fillcolor="rgba(0, 120, 115, 0.08)",
            hovertemplate="<b>%{fullData.name}</b><br>%{theta}: %{customdata}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatterpolar(
            r=media_values + [media_values[0]],
            theta=labels_closed,
            customdata=[_fmt_num(value) for value in media_values + [media_values[0]]],
            mode="lines+markers",
            name=f"Média da {_region_code(row['regiao_funcional'])}",
            line=dict(color="#7b8797", width=2, dash="dash"),
            marker=dict(size=6, color="#7b8797"),
            hovertemplate="<b>%{fullData.name}</b><br>%{theta}: %{customdata}<extra></extra>",
        )
    )
    figure.update_layout(
        **_hover_layout(
            height=344,
            margin=dict(l=10, r=10, t=2, b=2),
            paper_bgcolor="rgba(0,0,0,0)",
            polar=dict(
                bgcolor="rgba(0,0,0,0)",
                domain=dict(x=[0.02, 0.98], y=[0.02, 0.92]),
                radialaxis=dict(
                    range=[0, 10],
                    tickvals=[0, 2.5, 5, 7.5, 10],
                    tickfont=dict(size=10, color="#708095"),
                    gridcolor="#dfe7ed",
                ),
                angularaxis=dict(
                    tickfont=dict(size=11, color="#102542"), gridcolor="#dfe7ed"
                ),
            ),
            legend=dict(
                orientation="h",
                y=1.02,
                x=0.5,
                xanchor="center",
                font=dict(size=12, color="#102542"),
            ),
            showlegend=True,
        )
    )
    return figure


def _selected_detail_content(
    scope: pd.DataFrame, row, previous: pd.DataFrame, region_code: str, year
):
    return html.Div(
        [
            dcc.Graph(
                id="municipality-radar",
                figure=_radar_figure(scope, row),
                className="radar-wrap",
                config={"displayModeBar": False},
            ),
        ],
        className="selected-detail-content radar-only",
    )


def _municipality_history_figure(
    region: str | None, corede: str | None, municipio: str | None, mode: str = "nota"
) -> go.Figure:
    history = load_ranking_data()
    if region:
        history = history[history["regiao_funcional"] == region]
    if corede:
        history = history[history["corede"] == corede]
    if history.empty or not municipio:
        return _empty_figure("Sem série histórica para o município.")

    selected = history[history["municipio"] == municipio].sort_values("ano")
    if selected.empty:
        return _empty_figure("Sem série histórica para o município.")

    if mode == "posicao":
        y_column = "ranking_regiao_funcional"
        y_values = selected[y_column].dropna()
        y_min = float(y_values.min())
        y_max = float(y_values.max())

        figure = go.Figure()
        figure.add_trace(
            go.Scatter(
                x=selected["ano"],
                y=selected[y_column],
                mode="lines+markers+text",
                name=municipio,
                text=[f"{int(value)}º" for value in selected[y_column]],
                customdata=[f"{int(value)}º" for value in selected[y_column]],
                textposition="top center",
                textfont=dict(size=12),
                cliponaxis=False,
                line=dict(color="#007873", width=3),
                marker=dict(size=7, color="#007873"),
                hovertemplate="<b>%{fullData.name}</b><br>Ano %{x}<br>Posição: %{customdata}<extra></extra>",
            )
        )
        figure.update_layout(
            **_hover_layout(
                height=280,
                margin=dict(l=24, r=24, t=34, b=34),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(
                    tickmode="linear",
                    showgrid=False,
                    color="#102542",
                    tickfont=dict(size=11),
                ),
                yaxis=dict(
                    autorange="reversed",
                    range=[y_max + 4, max(1, y_min - 4)],
                    title=None,
                    showticklabels=False,
                    ticks="",
                    showline=False,
                    zeroline=False,
                    showgrid=True,
                    gridcolor="#e5ebef",
                    fixedrange=True,
                ),
                showlegend=False,
            )
        )
        return figure

    y_column = "nota_final"
    y_label = "Nota"
    regional = history.groupby("ano", as_index=False).agg(media=("nota_final", "mean"))
    y_values = pd.concat([selected[y_column], regional["media"]]).dropna()
    if y_values.empty:
        y_range = [0, 10]
    else:
        y_min = float(y_values.min())
        y_max = float(y_values.max())
        center = (y_min + y_max) / 2
        span = max(y_max - y_min, 0.8)
        y_range = [max(0, center - span * 0.75), min(10, center + span * 0.75)]

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=selected["ano"],
            y=selected[y_column],
            mode="lines+markers+text",
            name=municipio,
            text=[_fmt_num(value) for value in selected[y_column]],
            customdata=[_fmt_num(value) for value in selected[y_column]],
            textposition="top center",
            line=dict(color="#007873", width=3),
            marker=dict(size=7, color="#007873"),
            hovertemplate=f"<b>%{{fullData.name}}</b><br>Ano %{{x}}<br>{y_label}: %{{customdata}}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=regional["ano"],
            y=regional["media"],
            mode="lines+markers+text",
            name=f"Média da {_region_code(region)}",
            text=[_fmt_num(value) for value in regional["media"]],
            customdata=[_fmt_num(value) for value in regional["media"]],
            textposition="bottom center",
            line=dict(color="#7b8797", width=2, dash="dash"),
            marker=dict(size=6, color="#7b8797"),
            hovertemplate=f"<b>%{{fullData.name}}</b><br>Ano %{{x}}<br>Média: %{{customdata}}<extra></extra>",
        )
    )
    figure.update_layout(
        **_hover_layout(
            height=280,
            margin=dict(l=18, r=24, t=34, b=34),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(tickmode="linear", showgrid=False, color="#102542"),
            yaxis=dict(
                range=y_range,
                title=None,
                showticklabels=False,
                ticks="",
                showline=False,
                zeroline=False,
                showgrid=True,
                gridcolor="#e5ebef",
                fixedrange=True,
            ),
            legend=dict(
                orientation="h",
                y=1.12,
                x=0.5,
                xanchor="center",
                font=dict(size=12, color="#102542"),
            ),
            showlegend=True,
        )
    )
    return figure


def _municipality_selection_prompt(region_code: str, total: int):
    return html.Div(
        [
            html.Div(
                _icon("building", 58), className="municipality-prompt-illustration"
            ),
            html.Div(
                [
                    html.Div(
                        "Selecione um município para ver os detalhes",
                        className="municipality-prompt-title",
                    ),
                    html.Div(
                        "Escolha um município no filtro acima ou clique em uma linha do ranking ao lado para visualizar informações detalhadas por indicador.",
                        className="municipality-prompt-text",
                    ),
                ],
                className="municipality-prompt-copy",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("1"),
                            html.Div("Escolha um município no filtro acima."),
                        ]
                    ),
                    html.Div(
                        [html.Span("2"), html.Div("Ou clique em uma linha do ranking.")]
                    ),
                    html.Div(
                        [
                            html.Span("3"),
                            html.Div("Veja notas, posições e evolução por indicador."),
                        ]
                    ),
                ],
                className="municipality-prompt-steps",
            ),
            html.Div(
                [
                    _icon("bars", 24),
                    html.Div(
                        "Os indicadores do município selecionado serão exibidos aqui."
                    ),
                ],
                className="municipality-prompt-empty",
            ),
        ],
        className="municipality-prompt",
    )


def _history_figure(region: str | None, corede: str | None):
    history = load_ranking_data()
    if region:
        history = history[history["regiao_funcional"] == region]
    if corede:
        history = history[history["corede"] == corede]
    if history.empty:
        return _empty_figure("Sem série histórica para o recorte.")
    summary = history.groupby("ano", as_index=False).agg(media=("nota_final", "mean"))
    figure = go.Figure(
        go.Scatter(
            x=summary["ano"],
            y=summary["media"],
            mode="lines+markers+text",
            text=[_fmt_num(value) for value in summary["media"]],
            customdata=[_fmt_num(value) for value in summary["media"]],
            textposition="top center",
            line=dict(color="#007873", width=2),
            marker=dict(size=7, color="#007873"),
            hovertemplate="<b>Média regional</b><br>Ano %{x}<br>Média: %{customdata}<extra></extra>",
        )
    )
    figure.update_layout(
        **_hover_layout(
            height=220,
            margin=dict(l=30, r=12, t=18, b=26),
            yaxis=dict(
                range=[
                    max(0, summary["media"].min() - 1),
                    min(10, summary["media"].max() + 1),
                ],
                gridcolor="#e5ebef",
            ),
            xaxis=dict(tickmode="linear"),
            showlegend=False,
        )
    )
    return figure


def _indicator_bar(scope: pd.DataFrame):
    if scope.empty:
        return _empty_figure("Sem indicadores para o recorte.")
    means = scope[SECTOR_COLUMNS].mean()
    labels = [SECTOR_LABELS[column] for column in SECTOR_COLUMNS]
    figure = go.Figure(
        go.Bar(
            x=means.tolist(),
            y=labels,
            orientation="h",
            text=[_fmt_num(value) for value in means],
            customdata=[_fmt_num(value) for value in means],
            textposition="outside",
            marker=dict(color="#007873", line=dict(width=0)),
            width=0.62,
            hovertemplate="<b>%{y}</b><br>Média: %{customdata}<extra></extra>",
        )
    )
    figure.update_layout(
        **_hover_layout(
            height=220,
            margin=dict(l=172, r=58, t=2, b=4),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            bargap=0.36,
            xaxis=dict(
                range=[0, 10],
                title=None,
                showgrid=False,
                zeroline=False,
                showline=False,
                ticks="",
                showticklabels=False,
                tickfont=dict(size=10, color="#526277"),
            ),
            yaxis=dict(
                title=None,
                autorange="reversed",
                tickfont=dict(size=11, color="#102542"),
                ticks="",
                ticklabelstandoff=10,
                automargin=True,
            ),
            uniformtext=dict(minsize=10, mode="show"),
            showlegend=False,
        )
    )
    return figure


def _metric(icon_name, value_id, label, label_id=None):
    label_props = {"id": label_id} if label_id else {}
    return html.Div(
        [
            html.Div(_icon(icon_name, 35), className="circle-icon small"),
            html.Div(
                [
                    html.Div(id=value_id, className="metric-value"),
                    html.Div(label, className="metric-label", **label_props),
                ]
            ),
        ],
        className="hero-metric",
    )


layout = html.Div(
    [
        html.Section(
            [
                html.Section(
                    [
                        html.Div(_icon("map", 52), className="region-hero-icon"),
                        html.Div(
                            [
                                html.H1(
                                    "Selecione uma região funcional",
                                    className="regional-title",
                                ),
                                html.P(
                                    "Escolha uma região funcional no filtro acima para abrir o ranking dos municípios, os indicadores regionais e os detalhes por município.",
                                    className="regional-subtitle",
                                ),
                            ],
                            className="region-hero-copy",
                        ),
                    ],
                    className="region-overview-hero",
                ),
                html.Section(
                    [
                        html.Article(
                            [
                                html.Div(
                                    _icon("network", 30),
                                    className="overview-metric-icon teal-dark",
                                ),
                                html.Div(
                                    [
                                        html.Div(
                                            id="overview-regions",
                                            className="overview-metric-value",
                                        ),
                                        html.Div(
                                            "regiões funcionais",
                                            className="overview-metric-label",
                                        ),
                                    ]
                                ),
                            ],
                            className="overview-metric-card",
                        ),
                        html.Article(
                            [
                                html.Div(
                                    _icon("users", 30),
                                    className="overview-metric-icon teal",
                                ),
                                html.Div(
                                    [
                                        html.Div(
                                            id="overview-municipalities",
                                            className="overview-metric-value",
                                        ),
                                        html.Div(
                                            "municípios",
                                            className="overview-metric-label",
                                        ),
                                    ]
                                ),
                            ],
                            className="overview-metric-card",
                        ),
                        html.Article(
                            [
                                html.Div(
                                    _icon("method", 30),
                                    className="overview-metric-icon gold",
                                ),
                                html.Div(
                                    [
                                        html.Div(
                                            id="overview-coredes",
                                            className="overview-metric-value",
                                        ),
                                        html.Div(
                                            "Coredes", className="overview-metric-label"
                                        ),
                                    ]
                                ),
                            ],
                            className="overview-metric-card",
                        ),
                        html.Article(
                            [
                                html.Div(
                                    _icon("calendar", 30),
                                    className="overview-metric-icon calendar",
                                ),
                                html.Div(
                                    [
                                        html.Div(
                                            "Ano mais recente:",
                                            className="overview-year-label",
                                        ),
                                        html.Div(
                                            id="overview-year",
                                            className="overview-metric-value",
                                        ),
                                    ]
                                ),
                            ],
                            className="overview-metric-card",
                        ),
                    ],
                    className="overview-metrics-grid",
                ),
                html.Section(
                    [
                        html.Div(
                            [
                                html.Div(
                                    _icon("table", 22), className="summary-title-icon"
                                ),
                                html.Div(
                                    "Explore as regiões funcionais",
                                    className="summary-title",
                                ),
                            ],
                            className="summary-heading",
                        ),
                        html.Div(id="regions-summary-table-container"),
                        html.Div(
                            [
                                html.Div(
                                    _icon("info", 18), className="summary-note-icon"
                                ),
                                html.Div(
                                    "Selecione uma região para explorar o ranking dos municípios e os detalhes regionais."
                                ),
                            ],
                            className="summary-note region-explore-note",
                        ),
                    ],
                    className="region-summary-card",
                ),
            ],
            id="region-overview",
            className="region-overview",
        ),
        html.Section(
            [
                html.Div(
                    [
                        html.Div(_icon("building", 44), className="circle-icon"),
                        html.Div(
                            [
                                html.H1(
                                    id="regional-title", className="regional-title"
                                ),
                                html.P(
                                    "Compare o desempenho dos municípios dentro da região selecionada. Ao escolher um município, você verá informações detalhadas por indicador.",
                                    className="regional-subtitle",
                                ),
                            ]
                        ),
                    ],
                    className="hero-title-block",
                ),
                _metric(
                    "building",
                    "metric-municipios",
                    "Municípios na região",
                    "metric-municipios-label",
                ),
                _metric("star", "metric-media", "Média da nota final"),
                _metric("network", "metric-coredes", "Coredes", "metric-coredes-label"),
                html.Div(
                    [
                        html.Div(
                            _icon("trophy", 36), className="circle-icon small orange"
                        ),
                        html.Div(
                            [
                                html.Div(
                                    "Município selecionado", className="selected-label"
                                ),
                                html.Div(id="selected-name", className="selected-name"),
                                html.Div(id="selected-meta", className="selected-meta"),
                                html.Div(
                                    id="selected-municipio-actions",
                                    className="selected-municipio-actions",
                                ),
                            ]
                        ),
                    ],
                    id="selected-municipio-card",
                    className="selected-municipio",
                    style={"display": "none"},
                ),
            ],
            id="regional-hero",
            className="regional-hero no-selected",
            style={"display": "none"},
        ),
        html.Section(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                _icon("table", 18),
                                html.Div(id="ranking-title", className="panel-title"),
                            ],
                            className="panel-heading ranking-heading",
                        ),
                        dcc.Loading(
                            id="ranking-table-loading",
                            type="circle",
                            color="#007873",
                            children=[
                                dash_table.DataTable(
                                    id="ranking-table",
                                    columns=[
                                        {"name": "Posição", "id": "posicao"},
                                        {"name": "Município", "id": "municipio"},
                                        {"name": "Corede", "id": "corede"},
                                        {"name": "Desempenho", "id": "classificacao"},
                                        {"name": "Nota", "id": "nota_final"},
                                        {"name": "Var. ant.", "id": "delta_nota"},
                                        {"name": "Δ pos.", "id": "delta_posicao"},
                                    ],
                                    tooltip_header={
                                        "classificacao": (
                                            "A coluna Desempenho classifica o "
                                            "município considerando seu tamanho "
                                            "populacional."
                                        ),
                                    },
                                    tooltip_delay=300,
                                    tooltip_duration=None,
                                    data=[],
                                    active_cell=None,
                                    selected_cells=[],
                                    page_action="none",
                                    sort_action="none",
                                    style_table={
                                        "overflowX": "auto",
                                        "overflowY": "auto",
                                        "maxHeight": "310px",
                                        "width": "100%",
                                        "minWidth": "100%",
                                    },
                                    style_cell={
                                        "textAlign": "center",
                                        "padding": "7px 8px",
                                        "fontSize": "0.84rem",
                                        "whiteSpace": "normal",
                                        "height": "auto",
                                    },
                                    style_cell_conditional=[
                                        {
                                            "if": {"column_id": "posicao"},
                                            "width": "64px",
                                            "minWidth": "58px",
                                            "maxWidth": "70px",
                                        },
                                        {
                                            "if": {"column_id": "municipio"},
                                            "width": "190px",
                                            "minWidth": "170px",
                                            "maxWidth": "220px",
                                        },
                                        {
                                            "if": {"column_id": "corede"},
                                            "width": "210px",
                                            "minWidth": "180px",
                                            "maxWidth": "240px",
                                        },
                                        {
                                            "if": {"column_id": "classificacao"},
                                            "width": "130px",
                                            "minWidth": "120px",
                                            "maxWidth": "150px",
                                        },
                                        {
                                            "if": {"column_id": "nota_final"},
                                            "width": "74px",
                                            "minWidth": "68px",
                                            "maxWidth": "82px",
                                        },
                                        {
                                            "if": {"column_id": "delta_nota"},
                                            "width": "82px",
                                            "minWidth": "76px",
                                            "maxWidth": "90px",
                                        },
                                        {
                                            "if": {"column_id": "delta_posicao"},
                                            "width": "88px",
                                            "minWidth": "82px",
                                            "maxWidth": "96px",
                                        },
                                    ],
                                ),
                            ],
                        ),
                        html.Div(id="ranking-scroll-reset-dummy", style={"display": "none"}),
                    ],
                    className="ranking-card",
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        _icon("bars", 18),
                                        html.Div(
                                            id="detail-title", className="panel-title"
                                        ),
                                    ],
                                    className="panel-heading-main",
                                ),
                                html.Div(
                                    [_icon("info", 16), html.Span("Filtro necessário")],
                                    className="detail-required-badge",
                                ),
                            ],
                            className="panel-heading detail-heading",
                        ),
                        dcc.Loading(
                            id="detail-loading",
                            type="circle",
                            color="#007873",
                            children=[html.Div(id="indicator-detail-table")],
                        ),
                    ],
                    id="municipality-detail-card",
                    className="detail-card",
                    style={"display": "none"},
                ),
            ],
            id="dashboard-grid",
            className="dashboard-grid only-ranking",
            style={"display": "none"},
        ),
        html.Section(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [_icon("bars", 18), html.Span(id="history-title")],
                                    className="chart-title",
                                ),
                                html.Div(
                                    [
                                        html.Span(
                                            "Visualização",
                                            className="history-mode-label",
                                        ),
                                        dcc.RadioItems(
                                            id="history-mode-selector",
                                            options=[
                                                {
                                                    "label": "Posição",
                                                    "value": "posicao",
                                                },
                                                {
                                                    "label": "Nota final",
                                                    "value": "nota",
                                                },
                                            ],
                                            value="posicao",
                                            inline=True,
                                            className="history-mode-selector",
                                            inputClassName="history-mode-input",
                                            labelClassName="history-mode-option",
                                        ),
                                    ],
                                    className="history-mode-control",
                                ),
                            ],
                            className="chart-title-row",
                        ),
                        dcc.Loading(
                            id="history-loading",
                            type="circle",
                            color="#007873",
                            children=[
                                dcc.Graph(
                                    id="regional-history",
                                    className="plot-wrap",
                                    config={"displayModeBar": False},
                                ),
                            ],
                        ),
                        html.Div(
                            "Ver série histórica completa  ›", className="card-title"
                        ),
                    ],
                    className="chart-card",
                ),
                html.Div(
                    [
                        html.Div(
                            [_icon("bars", 18), html.Span(id="bars-title")],
                            className="chart-title",
                        ),
                        dcc.Loading(
                            id="bars-loading",
                            type="circle",
                            color="#007873",
                            children=[
                                dcc.Graph(
                                    id="indicator-bars",
                                    className="plot-wrap",
                                    config={"displayModeBar": False},
                                ),
                            ],
                        ),
                        html.Div(id="quick-read-card", className="quick-read-card"),
                        html.Div(
                            "Ver indicadores em detalhes  ›", className="card-title"
                        ),
                    ],
                    className="chart-card",
                ),
                html.Div(
                    [
                        html.Div(_icon("bulb", 34), className="circle-icon small"),
                        html.Div(
                            [
                                html.Div(
                                    "Como interpretar esta página",
                                    className="guide-title",
                                ),
                                html.Ul(
                                    [
                                        html.Li(
                                            "Todas as comparações e posições são sempre dentro da região funcional selecionada."
                                        ),
                                        html.Li(
                                            "Ao selecionar um município, o painel de detalhes será atualizado com notas, posições e evolução por indicador."
                                        ),
                                        html.Li(
                                            "As posições e evoluções refletem mudanças apenas entre os municípios desta região."
                                        ),
                                    ],
                                    className="guide-list",
                                ),
                            ]
                        ),
                    ],
                    className="guide-card",
                ),
            ],
            id="lower-grid",
            className="lower-grid",
            style={"display": "none"},
        ),
        html.Div(
            html.Button(
                [_icon("arrow-left", 16), html.Span("Voltar")],
                id="regional-back-button",
                className="regional-back-button",
                n_clicks=0,
            ),
            id="regional-back-actions",
            className="regional-back-actions",
            style={"display": "none"},
        ),
        html.Section(
            [
                html.A(
                    [
                        html.Div(_icon("scale", 30), className="circle-icon small"),
                        html.Div(
                            [
                                html.Div("Comparar municípios", className="card-title"),
                                html.Div(
                                    "Compare até 5 municípios da região.",
                                    className="card-text",
                                ),
                            ]
                        ),
                        html.Span("›", className="chevron"),
                    ],
                    href="/municipios",
                    className="action-card",
                ),
                html.A(
                    [
                        html.Div(_icon("bars", 30), className="circle-icon small"),
                        html.Div(
                            [
                                html.Div(
                                    "Explorar indicadores", className="card-title"
                                ),
                                html.Div(
                                    "Acesse dados e séries históricas.",
                                    className="card-text",
                                ),
                            ]
                        ),
                        html.Span("›", className="chevron"),
                    ],
                    href="/municipios",
                    className="action-card",
                ),
                html.A(
                    [
                        html.Div(_icon("method", 30), className="circle-icon small"),
                        html.Div(
                            [
                                html.Div("Metodologia", className="card-title"),
                                html.Div(
                                    "Entenda os indicadores e cálculos.",
                                    className="card-text",
                                ),
                            ]
                        ),
                        html.Span("›", className="chevron"),
                    ],
                    href="#",
                    className="action-card",
                ),
            ],
            id="action-row",
            className="action-row",
        ),
    ],
    className="page regional-page",
)


@callback(
    Output("regional-title", "children"),
    Output("metric-municipios", "children"),
    Output("metric-municipios-label", "children"),
    Output("metric-media", "children"),
    Output("metric-coredes", "children"),
    Output("metric-coredes-label", "children"),
    Output("selected-name", "children"),
    Output("selected-meta", "children"),
    Output("selected-municipio-actions", "children"),
    Output("ranking-title", "children"),
    Output("detail-title", "children"),
    Output("indicator-detail-table", "children"),
    Output("ranking-table", "data"),
    Output("ranking-table", "style_table"),
    Output("ranking-table", "style_data_conditional"),
    Output("regional-history", "figure"),
    Output("indicator-bars", "figure"),
    Output("quick-read-card", "children"),
    Output("quick-read-card", "style"),
    Output("history-title", "children"),
    Output("bars-title", "children"),
    Input("filter-ano", "value"),
    Input("filter-regiao", "value"),
    Input("filter-corede", "value"),
    Input("filter-municipio", "value"),
    Input("history-mode-selector", "value"),
)
def update_region_page(year, region, corede, municipio, history_mode):
    ranking_table_style = {
        "overflowX": "auto",
        "overflowY": "auto",
        "maxHeight": "310px",
        "width": "100%",
        "minWidth": "100%",
    }
    ranking_style = [
        {"if": {"column_id": "delta_nota"}, "fontWeight": "700"},
        {"if": {"column_id": "delta_posicao"}, "fontWeight": "700"},
        {
            "if": {
                "filter_query": "{delta_nota} contains '+'",
                "column_id": "delta_nota",
            },
            "color": "#07845f",
        },
        {
            "if": {
                "filter_query": "{delta_nota} contains '-'",
                "column_id": "delta_nota",
            },
            "color": "#d92f3a",
        },
        {
            "if": {
                "filter_query": "{delta_posicao} contains '+'",
                "column_id": "delta_posicao",
            },
            "color": "#07845f",
        },
        {
            "if": {
                "filter_query": "{delta_posicao} contains '-'",
                "column_id": "delta_posicao",
            },
            "color": "#d92f3a",
        },
    ] + _classification_datatable_styles()

    if year is None or not region:
        empty = _empty_figure("Selecione uma região funcional.")
        return (
            "Região funcional",
            "-",
            "Municípios na região",
            "-",
            "-",
            "Coredes",
            "-",
            "-",
            html.Div(),
            "Ranking dos municípios",
            "Município selecionado",
            html.Div(
                "Selecione uma região funcional para visualizar os dados.",
                className="empty-state",
            ),
            [],
            ranking_table_style,
            [],
            empty,
            empty,
            html.Div(),
            {"display": "none"},
            "Evolução média regional",
            "Média por indicador",
        )

    scope = _prepare_scope(year, region, corede)
    previous = _previous_frame(year, region, corede)
    focus = _focus_row(scope, municipio)
    code = _region_code(region)

    if scope.empty:
        empty = _empty_figure("Sem dados para os filtros selecionados.")
        return (
            f"Região funcional {code}",
            "-",
            "Municípios no recorte",
            "-",
            "-",
            "Coredes",
            "-",
            "-",
            html.Div(),
            f"Ranking dos municípios na {code}",
            "Município selecionado",
            html.Div(
                "Não há municípios no recorte selecionado.", className="empty-state"
            ),
            [],
            ranking_table_style,
            [],
            empty,
            empty,
            html.Div(),
            {"display": "none"},
            f"Evolução média regional ({year})",
            f"Média por indicador na {code}",
        )

    total = scope["municipio"].nunique()
    media = scope["nota_final"].mean()
    coredes = scope["corede"].replace("", pd.NA).dropna().nunique()
    has_corede_filter = bool(corede)
    municipio_metric_label = (
        "Municípios no corede filtrado" if has_corede_filter else "Municípios na região"
    )
    coredes_metric_label = "Corede filtrado" if has_corede_filter else "Coredes"
    regional_scope_title = (
        f"Região funcional {code} - {corede}"
        if has_corede_filter
        else f"Região funcional {code}"
    )
    ranking_scope_title = (
        f"Ranking dos municípios na {code} - {corede}"
        if has_corede_filter
        else f"Ranking dos municípios na {code}"
    )

    if focus is None:
        return (
            regional_scope_title,
            str(total),
            municipio_metric_label,
            _fmt_num(media),
            str(coredes),
            coredes_metric_label,
            "",
            "",
            html.Div(),
            ranking_scope_title,
            "Detalhes do município",
            _municipality_selection_prompt(code, total),
            _build_ranking_data(scope, previous),
            ranking_table_style,
            ranking_style,
            _history_figure(region, corede),
            _indicator_bar(scope),
            html.Div(),
            {"display": "none"},
            f"Evolu\u00e7\u00e3o m\u00e9dia regional ({scope['ano'].min()}-{year})",
            f"M\u00e9dia por indicador na {code} ({year})",
        )

    selected_rank = int(focus["ranking_regiao_funcional"])
    selected_score = _fmt_num(focus["nota_final"])
    selected_name = str(focus["municipio"])
    selected_corede = focus.get("corede")
    params = urlencode(
        {
            "ano": year,
            "regiao": region or "",
            "corede": corede or "",
            "municipio": selected_name,
        }
    )
    municipio_link = dcc.Link(
        [_icon("map", 15), html.Span("Ver página completa")],
        href=f"/municipios?{params}",
        className="selected-municipio-link",
    )
    selected_previous = (
        previous[previous["municipio"] == selected_name]
        if not previous.empty
        else pd.DataFrame()
    )
    selected_delta = None
    if not selected_previous.empty:
        previous_score = selected_previous.iloc[0]["nota_final"]
        if previous_score is not None and not pd.isna(previous_score):
            selected_delta = float(focus["nota_final"] - previous_score)
    row_style = [
        {
            "if": {"filter_query": f'{{municipio}} = "{selected_name}"'},
            "backgroundColor": "#eaf4f2",
            "fontWeight": "800",
            "color": "#006c67",
        },
        {"if": {"column_id": "delta_nota"}, "fontWeight": "700"},
        {"if": {"column_id": "delta_posicao"}, "fontWeight": "700"},
        {
            "if": {
                "filter_query": "{delta_nota} contains '+'",
                "column_id": "delta_nota",
            },
            "color": "#07845f",
        },
        {
            "if": {
                "filter_query": "{delta_posicao} contains '+'",
                "column_id": "delta_posicao",
            },
            "color": "#07845f",
        },
        {
            "if": {
                "filter_query": "{delta_nota} contains '-'",
                "column_id": "delta_nota",
            },
            "color": "#d92f3a",
        },
        {
            "if": {
                "filter_query": "{delta_posicao} contains '-'",
                "column_id": "delta_posicao",
            },
            "color": "#d92f3a",
        },
    ] + _classification_datatable_styles()

    history_title = (
        "Evolução da posição no ranking"
        if history_mode == "posicao"
        else "Evolução da nota final"
    )

    return (
        regional_scope_title,
        str(total),
        municipio_metric_label,
        _fmt_num(media),
        str(coredes),
        coredes_metric_label,
        _selected_name_with_corede(selected_name, selected_corede),
        html.Div(
            [
                html.Div(
                    [
                        html.Div(f"{selected_rank}º", className="selected-stat-value"),
                        html.Div(f"lugar na {code}", className="selected-stat-label"),
                    ]
                ),
                html.Div(
                    [
                        html.Div(selected_score, className="selected-stat-value"),
                        html.Div("Nota final", className="selected-stat-label"),
                    ]
                ),
                html.Div(
                    [
                        html.Div(
                            _fmt_delta(selected_delta), className="selected-stat-value"
                        ),
                        html.Div("Variação anual", className="selected-stat-label"),
                    ]
                ),
                html.Div(
                    [
                        html.Div(
                            _classification_label(focus.get("classificacao")),
                            className=f"selected-stat-value classification-text status-{_classification_status(focus.get('classificacao'))}",
                        ),
                        html.Div("Desempenho pop.", className="selected-stat-label"),
                    ]
                ),
            ],
            className="selected-stats",
        ),
        municipio_link,
        ranking_scope_title,
        "Perfil do município por indicador",
        _selected_detail_content(scope, focus, previous, code, year),
        _build_ranking_data(scope, previous),
        ranking_table_style,
        row_style,
        _municipality_history_figure(region, corede, selected_name, history_mode),
        _indicator_bar(scope),
        html.Div(
            _detail_table(scope, focus, previous, code, year),
            className="indicator-summary-panel",
        ),
        {},
        history_title,
        "Desempenho por indicador",
    )


@callback(
    Output("regions-summary-table-container", "children"),
    Output("overview-regions", "children"),
    Output("overview-municipalities", "children"),
    Output("overview-coredes", "children"),
    Output("overview-year", "children"),
    Input("filter-ano", "value"),
)
def update_regions_summary(year):
    rows = _build_region_summary_data(year)
    municipalities = sum(row["municipios"] for row in rows)
    coredes = set()
    for row in rows:
        coredes.update(
            item.strip() for item in row["coredes"].split(",") if item.strip()
        )
    return (
        _build_region_summary_table(rows),
        str(len(rows)),
        str(municipalities),
        str(len(coredes)),
        str(year) if year else "-",
    )


@callback(
    Output("filter-regiao", "value", allow_duplicate=True),
    Input({"type": "regional-overview-card", "region": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def select_region_from_summary(_clicks):
    if not _clicks or not any(clicks for clicks in _clicks if clicks):
        return dash.no_update

    triggered = ctx.triggered_id
    if isinstance(triggered, dict):
        return triggered.get("region")
    return dash.no_update


@callback(
    Output("filter-municipio", "value", allow_duplicate=True),
    Input("regional-back-button", "n_clicks"),
    prevent_initial_call=True,
)
def back_to_regional_selection(n_clicks):
    if not n_clicks:
        return dash.no_update
    return None


@callback(
    Output("filter-municipio", "value", allow_duplicate=True),
    Input("ranking-table", "active_cell"),
    State("ranking-table", "data"),
    State("filter-municipio", "value"),
    prevent_initial_call=True,
)
def select_municipality_from_ranking(active_cell, rows, current_municipio):
    if not active_cell or not rows:
        return dash.no_update
    row_index = active_cell.get("row")
    if row_index is None or row_index >= len(rows):
        return dash.no_update
    municipio = rows[row_index].get("municipio")
    if not municipio or municipio == current_municipio:
        return dash.no_update
    return municipio


@callback(
    Output("ranking-table", "active_cell"),
    Output("ranking-table", "selected_cells"),
    Input("filter-municipio", "value"),
)
def clear_ranking_selection_when_municipality_clears(municipio):
    if municipio:
        return dash.no_update, dash.no_update
    return None, []


@callback(
    Output("region-overview", "style"),
    Output("regional-hero", "className"),
    Output("regional-hero", "style"),
    Output("selected-municipio-card", "style"),
    Output("dashboard-grid", "className"),
    Output("dashboard-grid", "style"),
    Output("municipality-detail-card", "style"),
    Output("lower-grid", "className"),
    Output("lower-grid", "style"),
    Output("action-row", "style"),
    Input("filter-regiao", "value"),
    Input("filter-municipio", "value"),
)
def toggle_regional_sections(region, municipio):
    hidden = {"display": "none"}
    visible = {}
    if not region:
        return (
            {},
            "regional-hero no-selected",
            hidden,
            hidden,
            "dashboard-grid only-ranking",
            hidden,
            hidden,
            "lower-grid",
            hidden,
            hidden,
        )
    if municipio:
        return (
            hidden,
            "regional-hero municipality-compact",
            visible,
            visible,
            "dashboard-grid municipality-selected",
            visible,
            visible,
            "lower-grid municipality-selected",
            visible,
            hidden,
        )
    return (
        hidden,
        "regional-hero no-selected region-compact",
        visible,
        hidden,
        "dashboard-grid awaiting-municipality",
        visible,
        visible,
        "lower-grid region-selected",
        visible,
        hidden,
    )


clientside_callback(
    """
    function(ano, regiao, corede, municipio, data) {
        setTimeout(function() {
            const container = document.querySelector('#ranking-table .dash-spreadsheet-container');
            if (container) {
                container.scrollTop = 0;
            }
            const inner = document.querySelector('#ranking-table .dash-spreadsheet-inner');
            if (inner) {
                inner.scrollTop = 0;
            }
        }, 80);
        return window.dash_clientside.no_update;
    }
    """,
    Output("ranking-scroll-reset-dummy", "children"),
    Input("filter-ano", "value"),
    Input("filter-regiao", "value"),
    Input("filter-corede", "value"),
    Input("filter-municipio", "value"),
    Input("ranking-table", "data"),
)
