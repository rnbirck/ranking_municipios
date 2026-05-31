import dash
import pandas as pd
from dash import html

from src.data_loader import filter_ranking_data, get_default_year, load_ranking_data


dash.register_page(__name__, path="/", name="Início")


def _fmt_int(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{int(value):,}".replace(",", ".")


def _year_range(frame) -> str:
    if frame.empty or "ano" not in frame.columns:
        return "-"
    years = sorted(frame["ano"].dropna().astype(int).unique())
    if not years:
        return "-"
    return str(years[0]) if len(years) == 1 else f"{years[0]}–{years[-1]}"


def _icon(name: str, size: int = 31):
    classes = {
        "home": "bi-house-door",
        "building": "bi-buildings",
        "state": "bi-map",
        "network": "bi-diagram-3",
        "calendar": "bi-calendar3",
        "users": "bi-people",
        "bars": "bi-bar-chart",
        "trend": "bi-graph-up-arrow",
        "map": "bi-map",
        "pin": "bi-geo-alt",
        "check": "bi-check-circle",
        "list": "bi-list-check",
    }
    return html.I(
        className=f"bi {classes.get(name, classes['home'])}",
        style={"fontSize": f"{size}px"},
    )


def _summary():
    full = load_ranking_data()
    year = get_default_year()
    current = filter_ranking_data(ano=year)
    if current.empty:
        return {
            "municipios": "-",
            "regioes": "-",
            "coredes": "-",
            "serie": _year_range(full),
            "anos": "0",
        }

    years = sorted(full["ano"].dropna().astype(int).unique())
    return {
        "municipios": _fmt_int(current["municipio"].nunique()),
        "regioes": _fmt_int(current["regiao_funcional"].nunique()),
        "coredes": _fmt_int(current["corede"].replace("", pd.NA).dropna().nunique()),
        "serie": _year_range(full),
        "anos": _fmt_int(len(years)),
    }


def _metric(icon_name, value, label, note, orange=False):
    return html.Article(
        [
            html.Div(
                _icon(icon_name),
                className=f"home-metric-icon{' is-orange' if orange else ''}",
            ),
            html.Div(
                [
                    html.Div(
                        value,
                        className=f"home-metric-value{' is-orange' if orange else ''}",
                    ),
                    html.Div(label, className="home-metric-label"),
                    html.Div(note, className="home-metric-note"),
                ],
                className="home-metric-copy",
            ),
        ],
        className="home-metric-card",
    )


def _objective(icon_name, title, text):
    return html.Article(
        [
            html.Div(_icon(icon_name), className="home-objective-icon"),
            html.Div(
                [
                    html.H3(title, className="home-card-title"),
                    html.P(text, className="home-card-text"),
                ]
            ),
        ],
        className="home-objective-card",
    )


def _step(number, icon_name, text):
    return html.Article(
        [
            html.Span(str(number), className="home-step-number"),
            html.Div(_icon(icon_name, 28), className="home-step-icon"),
            html.P(text, className="home-step-text"),
        ],
        className="home-step-card",
    )


def _feature_card(icon_name, title, text, bullets, href, orange=False):
    return html.A(
        [
            html.Div(
                _icon(icon_name),
                className=f"home-feature-icon{' is-orange' if orange else ''}",
            ),
            html.Div(
                [
                    html.H3(
                        title,
                        className=f"home-feature-title{' is-orange' if orange else ''}",
                    ),
                    html.P(text, className="home-card-text"),
                ],
                className="home-feature-copy",
            ),
            html.Ul(
                [html.Li(item) for item in bullets],
                className=f"home-feature-list{' is-orange' if orange else ''}",
            ),
        ],
        href=href,
        className=f"home-feature-card{' is-orange' if orange else ''}",
    )


def _hero_orbits():
    return html.Div(
        [
            html.Span(className="home-orbit orbit-1"),
            html.Span(className="home-orbit orbit-2"),
            html.Span(className="home-orbit orbit-3"),
            html.Span(className="home-orbit orbit-4"),
            html.Span(className="home-orbit-dot dot-1"),
            html.Span(className="home-orbit-dot dot-2"),
            html.Span(className="home-orbit-dot dot-3"),
        ],
        className="home-radar-orbits",
        **{"aria-hidden": "true"},
    )


def layout():
    summary = _summary()
    return html.Div(
        [
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [_icon("home", 16), html.Span("Página inicial")],
                                className="home-radar-badge",
                            ),
                            html.H1(
                                "Radar dos Municípios do Rio Grande do Sul",
                                className="home-radar-title",
                            ),
                            html.P(
                                "Explore, compare e acompanhe o desempenho dos municípios gaúchos em saúde, educação, segurança, finanças, meio ambiente e desenvolvimento socioeconômico.",
                                className="home-radar-subtitle",
                            ),
                        ],
                        className="home-radar-copy",
                    ),
                    _hero_orbits(),
                ],
                className="home-radar-hero",
            ),
            html.Section(
                [
                    _metric(
                        "building",
                        summary["municipios"],
                        "municípios",
                        "do Rio Grande do Sul",
                    ),
                    _metric(
                        "state",
                        summary["regioes"],
                        "regiões funcionais",
                        "de planejamento",
                    ),
                    _metric(
                        "network",
                        summary["coredes"],
                        "Coredes",
                        "Conselhos Regionais de Desenvolvimento",
                    ),
                    _metric(
                        "calendar",
                        summary["serie"],
                        "Série histórica",
                        f"{summary['anos']} anos de dados disponíveis",
                        orange=True,
                    ),
                ],
                className="home-radar-metrics",
            ),
            html.H2("Objetivo do painel", className="home-radar-section-title"),
            html.Section(
                [
                    _objective(
                        "bars",
                        "Explorar recortes regionais",
                        "Evidencia desigualdades e potencialidades entre regiões funcionais e Coredes do estado.",
                    ),
                    _objective(
                        "trend",
                        "Acompanhar a evolução",
                        "Monitora os indicadores ao longo do tempo para apoiar decisões baseadas em evidências.",
                    ),
                ],
                className="home-objective-grid",
            ),
            html.H2("Como navegar", className="home-radar-section-title"),
            html.Section(
                [
                    _step(1, "calendar", "Selecione o ano de análise."),
                    html.Div("→", className="home-step-arrow"),
                    _step(2, "pin", "Escolha a região funcional ou o município."),
                    html.Div("→", className="home-step-arrow"),
                    _step(3, "building", "Explore os indicadores, notas e rankings."),
                    html.Div("→", className="home-step-arrow"),
                    _step(4, "trend", "Acompanhe a evolução e compare resultados."),
                ],
                className="home-navigation-flow",
            ),
            html.H2(
                "O que você encontra nas páginas", className="home-radar-section-title"
            ),
            html.Section(
                [
                    _feature_card(
                        "state",
                        "Regiões funcionais",
                        "Visão regional para comparar e entender o desempenho dos municípios.",
                        [
                            "Ranking dos municípios",
                            "Média da região e por indicador",
                            "Comparação entre municípios da região",
                            "Detalhes do município selecionado",
                        ],
                        "/ranking-regional",
                    ),
                    _feature_card(
                        "building",
                        "Municípios",
                        "Análise detalhada do desempenho de cada município ao longo do tempo.",
                        [
                            "Radar dos municípios",
                            "Evolução por dimensão",
                            "Histórico de posição",
                            "Comparação com a região funcional",
                        ],
                        "/municipios",
                        orange=True,
                    ),
                ],
                className="home-feature-grid",
            ),
        ],
        className="page home-page home-radar-page",
    )
