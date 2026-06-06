import re
from urllib.parse import urlencode

import dash
import pandas as pd
from dash import ALL, Input, Output, State, callback, ctx, html

from src.data_loader import filter_ranking_data


dash.register_page(__name__, path="/ranking-regional", name="Regiões funcionais")


def _fmt_num(value, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"
    return (
        f"{float(value):,.{digits}f}".replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def _region_sort_value(region: str) -> tuple[int, str]:
    match = re.search(r"(\d+)", region or "")
    if match:
        return int(match.group(1)), region
    return 999, region or ""


def _icon(name: str, size: int = 34):
    classes = {
        "bars": "bi-bar-chart",
        "network": "bi-diagram-3",
        "users": "bi-people",
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
                                    "Escolha uma região funcional no filtro acima para abrir a página de municípios da região.",
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
                                            "Coredes",
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
                                    _icon("table", 22),
                                    className="summary-title-icon",
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
                                    _icon("info", 18),
                                    className="summary-note-icon",
                                ),
                                html.Div(
                                    "Selecione uma região para abrir a página de municípios correspondente."
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
    ],
    className="page regional-page",
)


@callback(
    Output("overview-regions", "children"),
    Output("overview-municipalities", "children"),
    Output("overview-coredes", "children"),
    Output("overview-year", "children"),
    Output("regions-summary-table-container", "children"),
    Input("filter-ano", "value"),
)
def update_region_overview(year):
    rows = _build_region_summary_data(year)
    municipalities = sum(row["municipios"] for row in rows)

    coredes = set()
    for row in rows:
        coredes.update(
            item.strip()
            for item in row["coredes"].split(",")
            if item.strip()
        )

    return (
        str(len(rows)),
        str(municipalities),
        str(len(coredes)),
        str(year) if year else "-",
        _build_region_summary_table(rows),
    )


@callback(
    Output("app-location", "pathname", allow_duplicate=True),
    Output("app-location", "search", allow_duplicate=True),
    Input("filter-regiao", "value"),
    State("filter-ano", "value"),
    State("app-location", "pathname"),
    prevent_initial_call=True,
)
def navigate_to_municipios_from_region_filter(region, year, pathname):
    if ctx.triggered_id != "filter-regiao":
        return dash.no_update, dash.no_update

    if pathname != "/ranking-regional" or not region:
        return dash.no_update, dash.no_update

    params = urlencode(
        {
            "ano": year or "",
            "regiao": region,
        }
    )
    return "/municipios", f"?{params}"


@callback(
    Output("filter-regiao", "value", allow_duplicate=True),
    Output("filter-corede", "value", allow_duplicate=True),
    Output("filter-municipio", "value", allow_duplicate=True),
    Output("app-location", "search", allow_duplicate=True),
    Input("app-location", "pathname"),
    prevent_initial_call=True,
)
def reset_region_filters_when_opening_regional_page(pathname):
    if pathname != "/ranking-regional":
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    return None, None, None, ""


@callback(
    Output("app-location", "pathname", allow_duplicate=True),
    Output("app-location", "search", allow_duplicate=True),
    Input({"type": "regional-overview-card", "region": ALL}, "n_clicks"),
    State("filter-ano", "value"),
    State("app-location", "pathname"),
    prevent_initial_call=True,
)
def navigate_to_municipios_from_region_card(_clicks, year, pathname):
    if pathname != "/ranking-regional":
        return dash.no_update, dash.no_update

    if not _clicks or not any(clicks for clicks in _clicks if clicks):
        return dash.no_update, dash.no_update

    triggered = ctx.triggered_id
    if not isinstance(triggered, dict):
        return dash.no_update, dash.no_update

    region = triggered.get("region")
    if not region:
        return dash.no_update, dash.no_update

    params = urlencode(
        {
            "ano": year or "",
            "regiao": region,
        }
    )
    return "/municipios", f"?{params}"
