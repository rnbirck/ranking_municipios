import unicodedata
import os

import dash
import dash_bootstrap_components as dbc
import plotly.io as pio
from dash import Dash, Input, Output, State, callback, ctx, dcc, html, no_update

from src.data_loader import (
    filter_ranking_data,
    get_default_year,
    load_anos,
    load_regioes,
)


custom_template = pio.templates["plotly_white"]
custom_template.layout.separators = ",."
custom_template.layout.font = dict(
    family="Inter, Segoe UI, Arial, sans-serif", color="#102542", size=12
)
custom_template.layout.paper_bgcolor = "rgba(0,0,0,0)"
custom_template.layout.plot_bgcolor = "rgba(0,0,0,0)"
custom_template.layout.margin = dict(l=32, r=20, t=34, b=28)
custom_template.layout.hoverlabel = dict(
    bgcolor="#ffffff",
    bordercolor="#dfe6ec",
    font_family="Inter, Segoe UI, Arial, sans-serif",
    font_color="#102542",
)
pio.templates.default = custom_template


def _normalize_search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(
        character for character in normalized if not unicodedata.combining(character)
    ).casefold()


def _safe_load_anos() -> list[int]:
    try:
        return load_anos()
    except Exception as exc:
        print(f"Erro ao carregar anos: {exc}")
        return []


def _safe_load_regioes(year: int | None) -> list[str]:
    try:
        return load_regioes(year)
    except Exception as exc:
        print(f"Erro ao carregar regioes: {exc}")
        return []


def _safe_filter_frame(
    year: int | None, region: str | None = None, corede: str | None = None
):
    try:
        frame = filter_ranking_data(ano=year, regiao_funcional=region)
        if corede:
            frame = frame[frame["corede"] == corede]
        return frame
    except Exception as exc:
        print(f"Erro ao filtrar dados: {exc}")
        return None


def _safe_load_coredes(year: int | None, region: str | None) -> list[str]:
    if not region:
        return []
    frame = _safe_filter_frame(year, region)
    if frame is None or frame.empty or "corede" not in frame.columns:
        return []
    return sorted(frame["corede"].replace("", None).dropna().astype(str).unique())


def _safe_load_municipios(
    year: int | None, region: str | None, corede: str | None
) -> list[str]:
    frame = _safe_filter_frame(year, region, corede)
    if frame is None or frame.empty or "municipio" not in frame.columns:
        return []
    return sorted(frame["municipio"].dropna().astype(str).unique())


def _icon(name: str, size: int = 18):
    classes = {
        "home": "bi-house-door",
        "map": "bi-map",
        "building": "bi-buildings",
        "gauge": "bi-speedometer2",
        "compare": "bi-shuffle",
        "method": "bi-grid-3x3-gap",
        "help": "bi-question-circle",
        "users": "bi-people",
    }
    return html.Span(
        html.I(
            className=f"bi {classes.get(name, classes['home'])}",
            style={"fontSize": f"{size}px"},
        ),
        className="nav-icon",
    )


def _logo():
    return html.Span("u", className="brand-symbol")


def _nav_item(label: str, href: str, icon_name: str, active="partial"):
    return dbc.NavLink(
        [_icon(icon_name), html.Span(label)],
        href=href,
        active=active,
        className="nav-link",
    )


def _dropdown_options(values):
    return [{"label": str(value), "value": value} for value in values]


def _municipio_options(values):
    return [
        {
            "label": municipio,
            "value": municipio,
            "search": f"{municipio} {_normalize_search_text(municipio)}",
        }
        for municipio in values
    ]


def serve_layout():
    years = _safe_load_anos()
    default_year = get_default_year()
    selected_year = (
        default_year if default_year in years else (years[0] if years else None)
    )
    regions = _safe_load_regioes(selected_year)
    selected_region = None
    coredes = _safe_load_coredes(selected_year, selected_region)
    municipalities = _safe_load_municipios(selected_year, selected_region, None)

    return html.Div(
        [
            dcc.Location(id="app-location", refresh=False),
            html.Header(
                [
                    html.A(
                        [_logo(), html.Span("Unisinos", className="brand-name")],
                        href="/",
                        className="brand",
                    ),
                    html.Nav(
                        [
                            _nav_item("Inicio", "/", "home", active="exact"),
                            _nav_item("Regiões funcionais", "/ranking-regional", "map"),
                        ],
                        className="nav",
                    ),
                    html.Div(
                        [
                            html.Span(
                                [_icon("help"), html.Span("Ajuda")],
                                className="help-link",
                            ),
                            html.Span(
                                [_icon("users"), html.Span("Núcleo CEI")],
                                className="cei-button",
                            ),
                        ],
                        className="nav-actions",
                    ),
                ],
                className="topbar",
            ),
            html.Main(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Div("Ano", className="filter-label"),
                                    dcc.Dropdown(
                                        id="filter-ano",
                                        options=_dropdown_options(years),
                                        value=selected_year,
                                        clearable=False,
                                        searchable=False,
                                        className="filter-control",
                                    ),
                                ],
                                className="filter-field filter-year",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        "Região funcional", className="filter-label"
                                    ),
                                    dcc.Dropdown(
                                        id="filter-regiao",
                                        options=_dropdown_options(regions),
                                        value=selected_region,
                                        placeholder="Selecione",
                                        clearable=True,
                                        className="filter-control",
                                    ),
                                ],
                                className="filter-field filter-region",
                            ),
                            html.Div(
                                [
                                    html.Div("Corede", className="filter-label"),
                                    dcc.Dropdown(
                                        id="filter-corede",
                                        options=_dropdown_options(coredes),
                                        value=None,
                                        placeholder="Todos",
                                        clearable=True,
                                        className="filter-control",
                                    ),
                                ],
                                className="filter-field filter-corede",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        "Município",
                                        id="municipio-filter-label",
                                        className="filter-label",
                                    ),
                                    dcc.Dropdown(
                                        id="filter-municipio",
                                        options=_municipio_options(municipalities),
                                        value=None,
                                        placeholder="Selecione um munic\u00edpio",
                                        clearable=True,
                                        maxHeight=320,
                                        optionHeight=42,
                                        className="filter-control",
                                    ),
                                ],
                                className="filter-field filter-municipio",
                            ),
                            html.Button(
                                "↻  Limpar filtros",
                                id="clear-filters",
                                className="clear-button",
                                n_clicks=0,
                            ),
                        ],
                        id="filters-panel",
                        className="filters",
                    ),
                    html.Div(
                        dash.page_container,
                        id="content-shell",
                        className="content-shell",
                    ),
                ],
                className="app-main",
            ),
        ],
        className="app-shell",
    )


app = Dash(
    __name__,
    use_pages=True,
    pages_folder="src/views",
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
    ],
    suppress_callback_exceptions=True,
    title="Dashboard Ranking Municípios",
)
server = app.server
app.layout = serve_layout


@callback(
    Output("filter-regiao", "options"),
    Output("filter-regiao", "value"),
    Output("filter-corede", "options"),
    Output("filter-corede", "value"),
    Output("filter-municipio", "options"),
    Output("filter-municipio", "value"),
    Input("filter-ano", "value"),
    Input("filter-regiao", "value"),
    Input("filter-corede", "value"),
    Input("app-location", "pathname"),
    Input("clear-filters", "n_clicks"),
    State("filter-municipio", "value"),
)
def update_filter_options(
    selected_year,
    selected_region,
    selected_corede,
    pathname,
    clear_clicks,
    current_municipio,
):
    triggered = ctx.triggered_id
    regions = _safe_load_regioes(selected_year)
    is_municipios_page = False

    if triggered == "clear-filters":
        region = None
        corede = None
        municipio = None
    else:
        region = selected_region if selected_region in regions else None
        coredes_for_region = _safe_load_coredes(selected_year, region)
        corede = selected_corede if selected_corede in coredes_for_region else None
        municipios_for_scope = (
            _safe_load_municipios(selected_year, None, None)
            if is_municipios_page
            else _safe_load_municipios(selected_year, region, corede)
        )
        municipio = (
            current_municipio if current_municipio in municipios_for_scope else None
        )

    coredes = _safe_load_coredes(selected_year, region)
    municipalities = (
        _safe_load_municipios(selected_year, None, None)
        if is_municipios_page
        else _safe_load_municipios(selected_year, region, corede)
    )
    if municipio not in municipalities:
        municipio = None

    return (
        _dropdown_options(regions),
        region,
        _dropdown_options(coredes),
        corede,
        _municipio_options(municipalities),
        municipio,
    )


@callback(
    Output("filters-panel", "style"),
    Output("filters-panel", "className"),
    Output("content-shell", "className"),
    Output("municipio-filter-label", "children"),
    Input("app-location", "pathname"),
    Input("filter-regiao", "value"),
)
def update_shell_for_route(pathname, selected_region):
    if pathname == "/":
        return {"display": "none"}, "filters", "content-shell", "Município"
    if pathname == "/ranking-regional" and not selected_region:
        return {}, "filters filters-overview", "content-shell has-filters", "Município"
    return {}, "filters", "content-shell has-filters", "Município"


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.getenv("PORT", "8070")))
