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
        "gauge": "bi-speedometer2",
    }
    return html.I(className=f"bi {classes.get(name, classes['home'])}", style={"fontSize": f"{size}px"})


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


def _stat(icon_name, value, label, note, orange=False):
    return html.Article(
        [
            html.Div(_icon(icon_name), className=f"circle-icon{' orange' if orange else ''}"),
            html.Div(
                [
                    html.Div(value, className=f"stat-value{' orange-value' if orange else ''}"),
                    html.Div(label, className="stat-label"),
                    html.Div(note, className="stat-note"),
                ]
            ),
        ],
        className="soft-card stat-card",
    )


def _objective(icon_name, title, text):
    return html.Article(
        [
            html.Div(_icon(icon_name), className="circle-icon"),
            html.Div([html.Div(title, className="card-title"), html.Div(text, className="card-text")]),
        ],
        className="soft-card objective-card",
    )


def _step(number, icon_name, text):
    return html.Div(
        [
            html.Span(str(number), className="step-num"),
            html.Div(_icon(icon_name, 29), className="step-icon"),
            html.Div(text, className="card-text"),
        ],
        className="soft-card step-card",
    )


def _find(icon_name, title, text):
    return html.A(
        [
            html.Div(_icon(icon_name), className="circle-icon small"),
            html.Div([html.Div(title, className="card-title"), html.Div(text, className="card-text")]),
            html.Span("›", className="chevron"),
        ],
        href="/ranking-regional",
        className="soft-card find-card",
    )


def layout():
    summary = _summary()
    return html.Div(
        [
            html.Div([_icon("home", 16), html.Span("Página inicial")], className="home-badge"),
            html.H1(
                "Painel de Indicadores dos Municípios do Rio Grande do Sul",
                className="home-title",
            ),
            html.P(
                "Explore, compare e acompanhe o desempenho dos municípios gaúchos em saúde, educação, segurança, finanças, meio ambiente e desenvolvimento socioeconômico.",
                className="home-subtitle",
            ),
            html.Section(
                [
                    _stat("building", summary["municipios"], "municípios", "do Rio Grande do Sul"),
                    _stat("state", summary["regioes"], "regiões funcionais", "de planejamento"),
                    _stat("network", summary["coredes"], "Coredes", "Conselhos Regionais de Desenvolvimento"),
                    _stat("calendar", summary["serie"], "Série histórica", f"{summary['anos']} anos de dados disponíveis", orange=True),
                ],
                className="stat-grid",
            ),
            html.Div("Objetivo do dashboard", className="section-title"),
            html.Section(
                [
                    _objective("users", "Comparar municípios", "Permite comparar o desempenho entre municípios em diferentes indicadores e dimensões."),
                    _objective("bars", "Explorar diferenças regionais", "Evidencia desigualdades e potencialidades entre regiões funcionais e Coredes do estado."),
                    _objective("trend", "Monitorar a evolução", "Acompanhe a evolução dos indicadores ao longo do tempo para apoiar decisões baseadas em evidências."),
                ],
                className="objective-grid",
            ),
            html.Div("Como navegar", className="section-title"),
            html.Section(
                [
                    _step(1, "calendar", "Selecione o ano de análise."),
                    html.Div("→", className="step-arrow"),
                    _step(2, "pin", "Escolha a região funcional."),
                    html.Div("→", className="step-arrow"),
                    _step(3, "building", "Refine por Corede ou município."),
                    html.Div("→", className="step-arrow"),
                    _step(4, "trend", "Analise rankings, indicadores e evolução."),
                ],
                className="steps-grid",
            ),
            html.Div("O que você encontra aqui", className="section-title"),
            html.Section(
                [
                    _find("gauge", "Visão geral do estado", "Panorama dos principais indicadores do Rio Grande do Sul e suas comparações."),
                    _find("map", "Análise por região funcional", "Compare indicadores, rankings e tendências entre as regiões funcionais."),
                ],
                className="find-grid",
            ),
        ],
        className="page home-page",
    )
