import re
import threading
import time
import unicodedata
from urllib.parse import parse_qs

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, callback, ctx, dcc, html

from src.data_loader import (
    filter_ranking_data,
    get_category_labels,
    load_category_data,
    load_category_positions,
    load_indicator_names,
    load_municipio_category_history_data,
    load_municipio_indicator_data,
    load_municipio_summary_data,
    load_ranking_data,
)


dash.register_page(__name__, path="/municipios", name="Munic\u00edpios")

CATEGORY_LABELS = get_category_labels()
CATEGORY_ORDER = list(CATEGORY_LABELS)
CATEGORY_DEFAULT = CATEGORY_ORDER[0] if CATEGORY_ORDER else "saude"
CATEGORY_ICONS = {
    "educacao": "book",
    "financas": "coin",
    "meio_ambiente": "tree",
    "saude": "heart-pulse",
    "seguranca": "shield-check",
    "socioeconomico": "people",
}
MUNICIPIO_PRIMARY = "#b7791f"
MUNICIPIO_PRIMARY_FILL = "rgba(183, 121, 31, 0.12)"
MUNICIPIO_ACCENT = "#8a5a12"
MUNICIPIO_AVERAGE = "#64748b"
_PREFETCH_LOCK = threading.Lock()
_PREFETCH_KEYS: set[tuple[int, str, str, int]] = set()


def _fmt_num(value, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"
    return (
        f"{float(value):,.{digits}f}".replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def _fmt_pos(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{int(value)}\u00ba"


def _pos_num(value) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fmt_text(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    text = str(value).strip()
    return text if text else "-"


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


def _classification_badge(value, class_name: str = ""):
    status = _classification_status(value)
    label = _fmt_text(value)
    classes = f"classification-badge status-{status}"
    if class_name:
        classes = f"{classes} {class_name}"
    return html.Span(label, className=classes)


def _position_variation_chip(current_value, previous_value):
    current_position = _pos_num(current_value)
    previous_position = _pos_num(previous_value)

    if current_position is None or previous_position is None:
        label = "• Sem hist\u00f3rico"
        tone = "is-neutral"
    else:
        difference = previous_position - current_position
        if difference > 0:
            label = f"▲ Subiu {difference}"
            tone = "is-up"
        elif difference < 0:
            label = f"▼ Caiu {abs(difference)}"
            tone = "is-down"
        else:
            label = "• Sem varia\u00e7\u00e3o"
            tone = "is-neutral"

    return html.Span(label, className=f"municipio-info-variation-chip {tone}")


INDICATOR_FALLBACK_LABELS = {
    "qt_acesso_infor": "Acesso \u00e0 informa\u00e7\u00e3o",
}

PERCENT_INDICATOR_MULTIPLIERS = {
    "qt_acesso_infor": 100,
    "formalidade_mercado_trabalho": 100,
    "geracao_emprego_per_capita": 100,
    "vinculos_per_capita": 100,
    "proporcao_pessoas_baixa_renda": 1,
    "vulnerabilidade_social": 1,
}


def _indicator_label(value: str) -> str:
    identifier = str(value or "").strip()
    try:
        friendly_name = load_indicator_names().get(identifier)
    except Exception as exc:
        print(f"Erro ao carregar nomes dos indicadores: {exc}")
        friendly_name = None
    if friendly_name:
        return friendly_name
    return INDICATOR_FALLBACK_LABELS.get(
        identifier, identifier.replace("_", " ").capitalize()
    )


def _indicator_display_label(value: str, row=None) -> str:
    if row is not None:
        try:
            name = row.get("indicador_nome")
        except AttributeError:
            name = None
        if name is not None and not pd.isna(name):
            text = str(name).strip()
            if text and text != str(value or "").strip():
                return text
    return _indicator_label(str(value or ""))


def _is_percent_indicator(indicator: str | None) -> bool:
    return str(indicator or "").strip() in PERCENT_INDICATOR_MULTIPLIERS


def _indicator_observed_display_value(value, indicator: str | None):
    if value is None or pd.isna(value):
        return None
    numeric_value = float(value)
    multiplier = PERCENT_INDICATOR_MULTIPLIERS.get(str(indicator or "").strip())
    if multiplier is None:
        return numeric_value
    return numeric_value * multiplier


def _fmt_indicator_observed_value(value, indicator: str | None) -> str:
    display_value = _indicator_observed_display_value(value, indicator)
    if display_value is None or pd.isna(display_value):
        return "-"
    suffix = "%" if _is_percent_indicator(indicator) else ""
    return f"{_fmt_num(display_value)}{suffix}"


RADAR_LABELS = {
    "adequacao formacao docente": "Forma\u00e7\u00e3o<br>docente",
    "cobertura acs": "Cobertura<br>ACS",
    "cobertura aps": "Cobertura<br>APS",
    "cobertura vacinal penta polio media": "Vacinal<br>penta/polio",
    "medicos por mil habitantes": "M\u00e9dicos<br>por mil hab.",
    "obitos causas evitaveis mil habitantes": "\u00d3bitos evit\u00e1veis<br>por mil hab.",
    "proporcao consultas pre natal": "Pr\u00e9-natal",
    "proporcao gravidez adolescencia": "Gravidez<br>adolesc\u00eancia",
    "qt acesso infor": "Acesso \u00e0<br>informa\u00e7\u00e3o",
    "saeb ensino fundamental": "SAEB<br>fundamental",
    "taxa cobertura creche": "Cobertura<br>creche",
    "taxa distorcao fundamental": "Distor\u00e7\u00e3o<br>fundamental",
}


def _radar_label(value: str, max_words_per_line: int = 2) -> str:
    normalized = str(value or "").replace("_", " ").strip().lower()
    if normalized in RADAR_LABELS:
        return RADAR_LABELS[normalized]

    words = _indicator_label(value).split()
    if len(words) <= max_words_per_line:
        return " ".join(words)
    lines = [
        " ".join(words[index : index + max_words_per_line])
        for index in range(0, len(words), max_words_per_line)
    ]
    return "<br>".join(lines)


def _icon(name: str, size: int = 22):
    return html.I(className=f"bi bi-{name}", style={"fontSize": f"{size}px"})


def _selector_option_label(icon_name: str, text: str):
    return html.Span(
        [_icon(icon_name, 16), html.Span(text)],
        className="municipio-info-option-content",
    )


def _indicator_option_label(text: str):
    return html.Span(text, className="municipio-info-indicator-label")


def _empty_state(text: str):
    return html.Div(text, className="empty-state")


def _empty_figure(message: str, height: int = 260) -> go.Figure:
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
    figure.update_layout(
        height=height,
        margin=dict(l=12, r=12, t=12, b=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return figure


def _safe_ranking_data() -> pd.DataFrame:
    try:
        return load_ranking_data()
    except Exception as exc:
        print(f"Erro ao carregar ranking_municipios: {exc}")
        return pd.DataFrame()


def _safe_category_data(category: str) -> pd.DataFrame:
    try:
        return load_category_data(category)
    except Exception as exc:
        print(f"Erro ao carregar categoria {category}: {exc}")
        return pd.DataFrame()


def _safe_category_positions(
    year, region: str | None, corede: str | None
) -> pd.DataFrame:
    try:
        return load_category_positions(year, region, corede)
    except Exception as exc:
        print(f"Erro ao carregar posicoes das categorias: {exc}")
        return pd.DataFrame()


def _safe_municipio_summary(
    year=None,
    region: str | None = None,
    corede: str | None = None,
    municipio: str | None = None,
) -> pd.DataFrame:
    try:
        return load_municipio_summary_data(year, region, corede, municipio)
    except Exception as exc:
        print(f"Erro ao carregar resumo otimizado de municipios: {exc}")
        return pd.DataFrame()


def _safe_municipio_category_history(
    category: str, region: str | None, municipio: str | None
) -> pd.DataFrame:
    try:
        return load_municipio_category_history_data(category, region, municipio)
    except Exception as exc:
        print(f"Erro ao carregar historico otimizado da categoria: {exc}")
        return pd.DataFrame()


def _safe_municipio_indicator_data(
    category: str,
    region: str | None,
    municipio: str | None,
    indicator: str | None = None,
) -> pd.DataFrame:
    try:
        return load_municipio_indicator_data(category, region, municipio, indicator)
    except Exception as exc:
        print(f"Erro ao carregar indicadores otimizados do municipio: {exc}")
        return pd.DataFrame()


def _prefetch_municipio_detail_data(
    year, region: str | None, category: str | None = None
) -> None:
    if year is None or not region:
        return

    target_category = category if category in CATEGORY_LABELS else CATEGORY_DEFAULT
    key = (int(year), str(region), target_category, int(time.time() // 900))
    with _PREFETCH_LOCK:
        if key in _PREFETCH_KEYS:
            return
        _PREFETCH_KEYS.add(key)

    def worker() -> None:
        try:
            ranking = _safe_ranking_data()
            previous_year = _previous_year(year, ranking)
            if previous_year is not None:
                _safe_category_positions(previous_year, region, None)
        except Exception as exc:
            print(f"Erro no pre-carregamento de municipio: {exc}")

    threading.Thread(target=worker, daemon=True).start()


def _selected_context(year, region, municipio):
    if year is None or not municipio:
        return None, region

    ranking = _safe_ranking_data()
    if ranking.empty:
        return None, region

    frame = ranking[ranking["ano"] == int(year)].copy()
    if region:
        frame = frame[frame["regiao_funcional"] == region]

    match = frame[frame["municipio"] == municipio]
    if match.empty and not region:
        match = ranking[
            (ranking["ano"] == int(year)) & (ranking["municipio"] == municipio)
        ]
    if match.empty:
        return None, region

    row = match.iloc[0]
    return row, str(row["regiao_funcional"])


def _region_sort_value(region: str) -> tuple[int, str]:
    match = re.search(r"(\d+)", region or "")
    if match:
        return int(match.group(1)), region
    return 999, region or ""


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
            "N\u00e3o h\u00e1 dados regionais para o ano selecionado.",
            className="empty-state",
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
                id={"type": "municipio-overview-card", "region": row["regiao"]},
                n_clicks=0,
                title=f"Selecionar {row['regiao']}",
            )
            for row in rows
        ],
        className="region-explore-list",
    )


def _build_region_overview(year):
    rows = _build_region_summary_data(year)
    municipalities = sum(row["municipios"] for row in rows)
    coredes = set()
    for row in rows:
        coredes.update(
            item.strip() for item in row["coredes"].split(",") if item.strip()
        )

    return html.Section(
        [
            html.Section(
                [
                    html.Div(_icon("map", 52), className="region-hero-icon"),
                    html.Div(
                        [
                            html.H1(
                                "Selecione uma regi\u00e3o funcional",
                                className="regional-title",
                            ),
                            html.P(
                                "Escolha uma regi\u00e3o funcional no filtro acima para abrir o ranking dos munic\u00edpios, os indicadores regionais e os detalhes por munic\u00edpio.",
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
                                _icon("diagram-3", 30),
                                className="overview-metric-icon teal-dark",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        str(len(rows)),
                                        className="overview-metric-value",
                                    ),
                                    html.Div(
                                        "regi\u00f5es funcionais",
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
                                _icon("people", 30),
                                className="overview-metric-icon teal",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        str(municipalities),
                                        className="overview-metric-value",
                                    ),
                                    html.Div(
                                        "munic\u00edpios",
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
                                _icon("journal-text", 30),
                                className="overview-metric-icon gold",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        str(len(coredes)),
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
                                _icon("calendar3", 30),
                                className="overview-metric-icon calendar",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        "Ano mais recente:",
                                        className="overview-year-label",
                                    ),
                                    html.Div(
                                        str(year) if year else "-",
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
                    html.Div(_build_region_summary_table(rows)),
                    html.Div(
                        [
                            html.Div(
                                _icon("info-circle", 18), className="summary-note-icon"
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
        className="region-overview municipio-region-overview",
    )


def _with_classificacao_from_ranking(frame: pd.DataFrame, ranking: pd.DataFrame):
    if frame.empty or "classificacao" not in ranking.columns:
        return frame
    if "classificacao" in frame.columns:
        has_values = (
            frame["classificacao"].fillna("").astype(str).str.strip().ne("").any()
        )
        if has_values:
            return frame
        frame = frame.drop(columns=["classificacao"])

    key_candidates = [
        ["id_municipio", "ano", "regiao_funcional"],
        ["municipio", "ano", "regiao_funcional"],
    ]
    for keys in key_candidates:
        if all(
            column in frame.columns and column in ranking.columns for column in keys
        ):
            lookup = (
                ranking[keys + ["classificacao"]]
                .dropna(subset=["classificacao"])
                .drop_duplicates(keys)
            )
            if lookup.empty:
                return frame
            return frame.merge(lookup, on=keys, how="left")

    return frame


def _region_municipalities_table(year, region: str | None, corede: str | None):
    summary = _safe_municipio_summary(year, region, corede)
    ranking = _safe_ranking_data()
    if ranking.empty or year is None:
        return _empty_state("Sem dados de munic\u00edpios para listar.")
    if not region:
        return _build_region_overview(year)

    if summary.empty:
        frame = ranking[
            (ranking["ano"] == int(year)) & (ranking["regiao_funcional"] == region)
        ].copy()
        if corede:
            frame = frame[frame["corede"] == corede]
    else:
        frame = summary.copy()
    if frame.empty:
        return _empty_state("N\u00e3o h\u00e1 munic\u00edpios no recorte selecionado.")

    frame = _with_classificacao_from_ranking(frame, ranking)
    frame = frame.sort_values(["ranking_regiao_funcional", "municipio"])
    _prefetch_municipio_detail_data(year, region, CATEGORY_DEFAULT)
    positions = pd.DataFrame()
    if summary.empty:
        positions = _safe_category_positions(year, region, None)
    category_positions = {}
    for category in CATEGORY_ORDER:
        summary_column = f"ranking_{category}"
        if summary_column in frame.columns:
            category_positions[category] = frame.set_index("municipio")[
                summary_column
            ].to_dict()
        else:
            category_positions[category] = (
                positions[positions["category"] == category]
                .set_index("municipio")["ranking_dimensao"]
                .to_dict()
                if not positions.empty
                else {}
            )

    header_cells = [
        html.Th("Geral"),
        html.Th("Munic\u00edpio"),
        html.Th("Corede"),
        html.Th("Desempenho"),
        *[html.Th(CATEGORY_LABELS[category]) for category in CATEGORY_ORDER],
    ]
    rows = [
        html.Tr(
            [
                html.Td(
                    html.Span(
                        _fmt_pos(row["ranking_regiao_funcional"]),
                        className="score-pill compact",
                    )
                ),
                html.Td(str(row["municipio"])),
                html.Td(_fmt_text(row.get("corede"))),
                html.Td(_classification_badge(row.get("classificacao"), "compact")),
                *[
                    html.Td(
                        _fmt_pos(
                            category_positions.get(category, {}).get(row["municipio"])
                        )
                    )
                    for category in CATEGORY_ORDER
                ],
            ],
            id={
                "type": "municipio-info-row",
                "municipio": str(row["municipio"]),
                "corede": _fmt_text(row.get("corede")),
            },
            n_clicks=0,
            title=f"Selecionar {row['municipio']}",
        )
        for _, row in frame.iterrows()
    ]

    subtitle = (
        f"{len(frame)} munic\u00edpios em {region}"
        if not corede
        else f"{len(frame)} munic\u00edpios em {region} - {corede}"
    )
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            _icon("list-ol", 18),
                            html.Span("Munic\u00edpios da regi\u00e3o"),
                        ],
                        className="chart-title",
                    ),
                    html.Div(subtitle, className="municipio-info-region-subtitle"),
                ],
                className="municipio-info-region-heading",
            ),
            html.Div(
                html.Table(
                    [
                        html.Thead(html.Tr(header_cells)),
                        html.Tbody(rows),
                    ],
                    className="region-summary-table municipio-info-region-table",
                ),
                className="municipio-info-region-table-scroll",
            ),
        ],
        className="chart-card municipio-info-region-card",
    )


def _previous_year(year, ranking: pd.DataFrame | None = None) -> int | None:
    if year is None:
        return None
    frame = ranking if ranking is not None else _safe_ranking_data()
    if frame.empty or "ano" not in frame.columns:
        return None
    previous_years = sorted(
        frame.loc[frame["ano"] < int(year), "ano"].dropna().astype(int).unique()
    )
    return previous_years[-1] if previous_years else None


def _category_cards(
    year,
    region,
    municipio,
    selected_category=None,
    current_positions: pd.DataFrame | None = None,
    previous_positions: pd.DataFrame | None = None,
    previous_year: int | None = None,
):
    current_positions = (
        current_positions
        if current_positions is not None
        else _safe_category_positions(year, region, None)
    )

    cards = []
    for category in CATEGORY_ORDER:
        current_match = (
            current_positions[
                (current_positions["category"] == category)
                & (current_positions["municipio"] == municipio)
            ]
            if not current_positions.empty
            else pd.DataFrame()
        )

        if current_match.empty:
            current_rank = None
            previous_rank = None
            value = "-"
            previous_position = "Anterior: -"
        else:
            current_rank = current_match.iloc[0].get("ranking_dimensao")
            value = _fmt_pos(current_rank)
            previous_match = (
                previous_positions[
                    (previous_positions["category"] == category)
                    & (previous_positions["municipio"] == municipio)
                ]
                if previous_positions is not None and not previous_positions.empty
                else pd.DataFrame()
            )
            if previous_match.empty or previous_year is None:
                previous_rank = None
                previous_position = "Anterior: -"
            else:
                previous_rank = previous_match.iloc[0].get("ranking_dimensao")
                previous_position = (
                    f"Anterior ({previous_year}): {_fmt_pos(previous_rank)}"
                )

        variation_chip = _position_variation_chip(current_rank, previous_rank)

        cards.append(
            html.Article(
                [
                    html.Div(
                        _icon(CATEGORY_ICONS[category], 24),
                        className="municipio-info-category-icon",
                    ),
                    html.Div(
                        [
                            html.Div(
                                CATEGORY_LABELS[category],
                                className="municipio-info-card-label",
                            ),
                            html.Div(value, className="municipio-info-card-value"),
                            html.Div(
                                [
                                    html.Div(
                                        previous_position,
                                        className="municipio-info-card-score",
                                    ),
                                    variation_chip,
                                ],
                                className="municipio-info-card-meta",
                            ),
                        ]
                    ),
                ],
                className=(
                    "municipio-info-category-card is-selected"
                    if category == selected_category
                    else "municipio-info-category-card"
                ),
                id={"type": "category-card", "category": category},
                n_clicks=0,
                title=f"Selecionar categoria {CATEGORY_LABELS[category]}",
            )
        )
    return cards


def _category_history(
    category: str,
    region: str | None,
    municipio: str | None,
    category_data: pd.DataFrame | None = None,
):
    frame = (
        category_data if category_data is not None else _safe_category_data(category)
    )
    if frame.empty or not region or not municipio:
        return pd.DataFrame(), 0

    region_frame = frame[frame["regiao_funcional"] == region].copy()
    history = (
        region_frame[region_frame["municipio"] == municipio]
        .sort_values("ano")
        .drop_duplicates(["ano", "municipio"])
    )
    if "total_municipios_regiao" in history.columns:
        max_value = history["total_municipios_regiao"].max()
    else:
        max_value = region_frame.groupby("ano")["municipio"].nunique().max()
    max_rank = int(max_value) if pd.notna(max_value) else 0
    return history, max_rank


def _category_history_figure(
    category: str,
    region: str | None,
    municipio: str | None,
    category_data: pd.DataFrame | None = None,
):
    history, max_rank = _category_history(category, region, municipio, category_data)
    if history.empty:
        return _empty_figure(
            "Selecione um munic\u00edpio para ver o hist\u00f3rico.", height=260
        )

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=history["ano"],
            y=history["ranking_dimensao"],
            mode="lines+markers+text",
            text=[_fmt_pos(value) for value in history["ranking_dimensao"]],
            customdata=[_fmt_num(value) for value in history["nota_dimensao"]],
            textposition="top center",
            line=dict(color=MUNICIPIO_PRIMARY, width=3),
            marker=dict(size=7, color=MUNICIPIO_PRIMARY),
            cliponaxis=False,
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Posi\u00e7\u00e3o na categoria: %{text}<br>"
                "Nota da categoria: %{customdata}<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        height=254,
        margin=dict(l=46, r=30, t=42, b=36),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            tickmode="linear", showgrid=False, color="#102542", tickfont=dict(size=10)
        ),
        yaxis=dict(
            title=dict(text="Posi\u00e7\u00e3o", font=dict(size=11, color="#526277")),
            autorange="reversed",
            range=[max_rank + 6, 0] if max_rank else None,
            showticklabels=True,
            tickfont=dict(size=10, color="#526277"),
            ticks="",
            gridcolor="#e5ebef",
            zeroline=False,
            fixedrange=True,
        ),
        hoverlabel=dict(
            bgcolor="#ffffff",
            bordercolor="#dfe6ec",
            font=dict(color="#102542"),
        ),
        showlegend=False,
    )
    return figure


def _category_radar_figure(
    category: str,
    year,
    region: str | None,
    municipio: str | None,
    category_data: pd.DataFrame | None = None,
):
    if not region or not municipio or year is None:
        return _empty_figure("Selecione um munic\u00edpio.", height=260)

    frame = (
        category_data if category_data is not None else _safe_category_data(category)
    )
    if frame.empty:
        return _empty_figure("Sem dados para a categoria.", height=260)

    current_frame = frame[
        (frame["ano"] == int(year))
        & (frame["regiao_funcional"] == region)
        & (frame["municipio"] == municipio)
    ].copy()
    if current_frame.empty:
        return _empty_figure("Sem dados para o recorte.", height=260)

    indicadores = current_frame["indicador"].dropna().unique()
    if len(indicadores) == 0:
        return _empty_figure("Sem indicadores na categoria.", height=260)

    values = []
    medias = []
    labels = []
    for indicador in indicadores:
        indicador_rows = frame[
            (frame["ano"] == int(year))
            & (frame["regiao_funcional"] == region)
            & (frame["indicador"] == indicador)
        ]
        municipio_row = current_frame[current_frame["indicador"] == indicador]
        if municipio_row.empty or pd.isna(municipio_row.iloc[0]["nota_indicador"]):
            values.append(0)
        else:
            values.append(float(municipio_row.iloc[0]["nota_indicador"]))
        if (
            not municipio_row.empty
            and "media_nota_indicador_regiao" in municipio_row.columns
            and not pd.isna(municipio_row.iloc[0]["media_nota_indicador_regiao"])
        ):
            medias.append(float(municipio_row.iloc[0]["media_nota_indicador_regiao"]))
        else:
            medias.append(float(indicador_rows["nota_indicador"].mean()))
        labels.append(_radar_label(indicador))

    labels_closed = labels + [labels[0]]
    values_closed = values + [values[0]]
    medias_closed = medias + [medias[0]]

    figure = go.Figure()
    figure.add_trace(
        go.Scatterpolar(
            r=values_closed,
            theta=labels_closed,
            customdata=[_fmt_num(v) for v in values_closed],
            mode="lines+markers",
            name=str(municipio),
            line=dict(color=MUNICIPIO_PRIMARY, width=3),
            marker=dict(size=8, color=MUNICIPIO_PRIMARY),
            fill="toself",
            fillcolor=MUNICIPIO_PRIMARY_FILL,
            hovertemplate="<b>%{fullData.name}</b><br>%{theta}: %{customdata}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatterpolar(
            r=medias_closed,
            theta=labels_closed,
            customdata=[_fmt_num(v) for v in medias_closed],
            mode="lines+markers",
            name=f"M\u00e9dia da {region}",
            line=dict(color=MUNICIPIO_AVERAGE, width=2, dash="dash"),
            marker=dict(size=6, color=MUNICIPIO_AVERAGE),
            hovertemplate="<b>%{fullData.name}</b><br>%{theta}: %{customdata}<extra></extra>",
        )
    )
    figure.update_layout(
        height=292,
        margin=dict(l=30, r=18, t=12, b=18),
        paper_bgcolor="rgba(0,0,0,0)",
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            domain=dict(x=[0.06, 0.68], y=[0.02, 0.96]),
            radialaxis=dict(
                range=[0, 10],
                tickvals=[0, 2.5, 5, 7.5, 10],
                showticklabels=False,
                gridcolor="#dfe7ed",
            ),
            angularaxis=dict(
                tickfont=dict(size=10, color="#102542"),
                gridcolor="#dfe7ed",
            ),
        ),
        legend=dict(
            x=0.78,
            y=0.92,
            xanchor="left",
            yanchor="top",
            orientation="v",
            bgcolor="rgba(255,255,255,0.92)",
            bordercolor="#d8e1e8",
            borderwidth=1,
            font=dict(size=11, color="#102542"),
            itemwidth=30,
        ),
        showlegend=True,
    )
    return figure


def _current_indicator_rows(
    category: str,
    year,
    region: str | None,
    municipio: str | None,
    category_data: pd.DataFrame | None = None,
):
    frame = (
        category_data if category_data is not None else _safe_category_data(category)
    )
    if frame.empty or year is None or not region or not municipio:
        return pd.DataFrame()

    current = frame[
        (frame["ano"] == int(year))
        & (frame["regiao_funcional"] == region)
        & (frame["municipio"] == municipio)
    ].copy()
    if current.empty:
        return current
    ranking_column = _indicator_rank_column(current)
    return current.sort_values([ranking_column, "indicador"])


def _indicator_rank_column(frame: pd.DataFrame) -> str:
    return (
        "ranking_indicador_desempatado"
        if "ranking_indicador_desempatado" in frame.columns
        else "ranking_indicador"
    )


def _indicator_options(current_rows: pd.DataFrame):
    if current_rows.empty:
        return []
    return [
        {
            "label": _indicator_option_label(
                _indicator_display_label(row["indicador"], row)
            ),
            "value": row["indicador"],
        }
        for _, row in current_rows.iterrows()
    ]


def _indicator_history(
    category: str,
    region,
    municipio,
    indicator,
    category_data: pd.DataFrame | None = None,
):
    frame = (
        category_data if category_data is not None else _safe_category_data(category)
    )
    if frame.empty or not region or not municipio or not indicator:
        return pd.DataFrame(), 0

    region_indicator = frame[
        (frame["regiao_funcional"] == region) & (frame["indicador"] == indicator)
    ].copy()
    history = region_indicator[region_indicator["municipio"] == municipio].sort_values(
        "ano"
    )
    if "total_municipios_regiao" in history.columns:
        max_value = history["total_municipios_regiao"].max()
    else:
        max_value = region_indicator.groupby("ano")["municipio"].nunique().max()
    max_rank = int(max_value) if pd.notna(max_value) else 0
    return history, max_rank


def _indicator_history_figure(
    category: str,
    region,
    municipio,
    indicator,
    category_data: pd.DataFrame | None = None,
):
    history, max_rank = _indicator_history(
        category, region, municipio, indicator, category_data
    )
    if history.empty:
        return _empty_figure(
            "Selecione um indicador para ver o hist\u00f3rico.", height=260
        )

    figure = go.Figure()
    ranking_column = _indicator_rank_column(history)
    figure.add_trace(
        go.Scatter(
            x=history["ano"],
            y=history[ranking_column],
            mode="lines+markers+text",
            text=[_fmt_pos(value) for value in history[ranking_column]],
            customdata=[
                [
                    _fmt_indicator_observed_value(row["valor_original"], indicator),
                    _fmt_num(row["nota_indicador"]),
                    _fmt_pos(row.get("ranking_indicador")),
                ]
                for _, row in history.iterrows()
            ],
            textposition="top center",
            line=dict(color=MUNICIPIO_ACCENT, width=3),
            marker=dict(size=7, color=MUNICIPIO_ACCENT),
            cliponaxis=False,
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Posi\u00e7\u00e3o no indicador: %{text}<br>"
                "Posi\u00e7\u00e3o original: %{customdata[2]}<br>"
                "Valor Observado: %{customdata[0]}<br>"
                "Nota: %{customdata[1]}<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        height=254,
        margin=dict(l=46, r=30, t=42, b=36),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            tickmode="linear", showgrid=False, color="#102542", tickfont=dict(size=10)
        ),
        yaxis=dict(
            title=dict(text="Posi\u00e7\u00e3o", font=dict(size=11, color="#526277")),
            autorange="reversed",
            range=[max_rank + 6, 0] if max_rank else None,
            showticklabels=True,
            tickfont=dict(size=10, color="#526277"),
            ticks="",
            gridcolor="#e5ebef",
            zeroline=False,
            fixedrange=True,
        ),
        hoverlabel=dict(bgcolor="#ffffff", bordercolor="#dfe6ec"),
        showlegend=False,
    )
    return figure


def _indicator_value_history_figure(
    category: str,
    region,
    municipio,
    indicator,
    category_data: pd.DataFrame | None = None,
):
    history, _ = _indicator_history(
        category, region, municipio, indicator, category_data
    )
    if history.empty:
        return _empty_figure("Selecione um indicador.", height=260)

    display_values = [
        _indicator_observed_display_value(value, indicator)
        for value in history["valor_original"]
    ]
    formatted_values = [
        _fmt_indicator_observed_value(value, indicator)
        for value in history["valor_original"]
    ]
    is_percent = _is_percent_indicator(indicator)
    y_axis_title = "Valor Observado (%)" if is_percent else "Valor Observado"
    has_regional_average = bool(
        "media_valor_original_regiao" in history.columns
        and history["media_valor_original_regiao"].notna().any()
    )
    regional_average_values = []
    formatted_regional_average_values = []
    if has_regional_average:
        regional_average_values = [
            _indicator_observed_display_value(value, indicator)
            for value in history["media_valor_original_regiao"]
        ]
        formatted_regional_average_values = [
            _fmt_indicator_observed_value(value, indicator)
            for value in history["media_valor_original_regiao"]
        ]

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=history["ano"],
            y=display_values,
            mode="lines+markers+text",
            name=str(municipio),
            text=formatted_values,
            customdata=formatted_values,
            textposition="top center",
            line=dict(color=MUNICIPIO_PRIMARY, width=3),
            marker=dict(size=7, color=MUNICIPIO_PRIMARY),
            cliponaxis=False,
            showlegend=has_regional_average,
            hovertemplate=(
                "<b>%{x}</b><br>Valor Observado: %{customdata}<extra></extra>"
            ),
        )
    )
    if has_regional_average:
        figure.add_trace(
            go.Scatter(
                x=history["ano"],
                y=regional_average_values,
                mode="lines+markers",
                name=f"Média da {region}",
                customdata=formatted_regional_average_values,
                line=dict(color=MUNICIPIO_AVERAGE, width=2, dash="dot"),
                marker=dict(size=6, color=MUNICIPIO_AVERAGE),
                connectgaps=True,
                showlegend=True,
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    "Média regional: %{customdata}<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        height=254,
        margin=dict(l=54, r=32, t=42, b=36),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            tickmode="linear", showgrid=False, color="#102542", tickfont=dict(size=10)
        ),
        yaxis=dict(
            title=dict(text=y_axis_title, font=dict(size=10, color="#526277")),
            gridcolor="#e5ebef",
            zeroline=False,
            fixedrange=True,
            tickfont=dict(size=10),
            ticksuffix="%" if is_percent else "",
            automargin=True,
        ),
        hoverlabel=dict(bgcolor="#ffffff", bordercolor="#dfe6ec"),
        legend=dict(
            orientation="h",
            y=1.16,
            x=1,
            xanchor="right",
            font=dict(size=10, color="#526277"),
        ),
        showlegend=has_regional_average,
    )
    return figure


layout = html.Div(
    [
        html.Section(
            [
                html.Div(
                    [
                        html.Div(
                            _icon("buildings", 42), className="municipio-info-hero-icon"
                        ),
                        html.Div(
                            [
                                html.H1(
                                    "Informa\u00e7\u00f5es dos munic\u00edpios",
                                    id="municipio-info-title",
                                    className="municipio-info-title",
                                ),
                                html.P(
                                    "Acompanhe a posi\u00e7\u00e3o do munic\u00edpio dentro da sua regi\u00e3o funcional por categoria e por indicador.",
                                    id="municipio-info-subtitle",
                                    className="municipio-info-subtitle",
                                ),
                            ],
                            className="municipio-info-identity-copy",
                        ),
                    ],
                    className="municipio-info-identity-block",
                ),
                html.Div(
                    id="municipio-info-context", className="municipio-info-context"
                ),
            ],
            id="municipio-info-hero",
            className="municipio-info-hero",
        ),
        html.Section(
            id="municipio-info-category-cards",
            className="municipio-info-category-grid",
            style={"display": "none"},
        ),
        html.Section(id="municipio-info-region-list"),
        html.Div(
            html.Button(
                [_icon("arrow-left", 16), html.Span("Voltar para sele\u00e7\u00e3o")],
                id="municipio-info-back-button",
                className="municipio-info-back-button",
                n_clicks=0,
            ),
            id="municipio-info-back-actions",
            className="municipio-info-back-actions",
            style={"display": "none"},
        ),
        html.Section(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                _icon("grid", 18),
                                html.Span("Selecione a dimens\u00e3o"),
                            ],
                            className="selector-label",
                        ),
                        dcc.RadioItems(
                            id="municipio-info-category",
                            options=[
                                {
                                    "label": _selector_option_label(
                                        CATEGORY_ICONS.get(key, "circle"),
                                        label,
                                    ),
                                    "value": key,
                                }
                                for key, label in CATEGORY_LABELS.items()
                            ],
                            value=CATEGORY_DEFAULT,
                            inline=True,
                            className="municipio-info-segmented",
                            inputClassName="municipio-info-segmented-input",
                            labelClassName="municipio-info-segmented-option",
                        ),
                    ],
                    className="category-selector-container",
                ),
            ],
            id="municipio-info-category-selector",
            className="municipio-info-selector-section",
            style={"display": "none"},
        ),
        html.Section(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        _icon("columns-gap", 18),
                                        html.Span(
                                            "Hist\u00f3rico de posi\u00e7\u00e3o",
                                            id="municipio-info-category-history-title",
                                        ),
                                    ],
                                    className="chart-title",
                                ),
                            ],
                            className="municipio-info-panel-header",
                        ),
                        dcc.Loading(
                            id="municipio-chart-history-loading",
                            type="circle",
                            color=MUNICIPIO_PRIMARY,
                            children=[
                                dcc.Graph(
                                    id="municipio-info-category-history",
                                    config={"displayModeBar": False},
                                ),
                            ],
                        ),
                    ],
                    className="chart-card municipio-info-panel",
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        _icon("activity", 18),
                                        html.Span(
                                            "Notas da dimens\u00e3o",
                                            id="municipio-info-category-radar-title",
                                        ),
                                    ],
                                    className="chart-title",
                                ),
                            ],
                            className="municipio-info-panel-header",
                        ),
                        dcc.Loading(
                            id="municipio-chart-radar-loading",
                            type="circle",
                            color=MUNICIPIO_PRIMARY,
                            children=[
                                dcc.Graph(
                                    id="municipio-info-category-radar",
                                    config={"displayModeBar": False},
                                ),
                            ],
                        ),
                    ],
                    className="chart-card municipio-info-panel",
                ),
            ],
            id="municipio-info-main-grid",
            className="municipio-info-main-grid",
            style={"display": "none"},
        ),
        html.Section(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                _icon("activity", 18),
                                html.Span("Selecione o indicador"),
                            ],
                            className="selector-label",
                        ),
                        html.Div(
                            [
                                dcc.RadioItems(
                                    id="municipio-info-indicator",
                                    options=[],
                                    value=None,
                                    inline=True,
                                    className="municipio-info-segmented indicator-pills municipio-info-indicator-pills",
                                    inputClassName="municipio-info-segmented-input",
                                    labelClassName="municipio-info-segmented-option municipio-info-indicator-chip",
                                ),
                                dcc.Dropdown(
                                    id="municipio-info-indicator-more",
                                    options=[],
                                    value=None,
                                    clearable=False,
                                    searchable=False,
                                    placeholder="Mais indicadores",
                                    className="municipio-info-more-dropdown",
                                    style={"display": "none"},
                                ),
                            ],
                            className="indicator-selector-row",
                        ),
                    ],
                    className="indicator-selector-container",
                ),
            ],
            id="municipio-info-indicator-selector",
            className="municipio-info-selector-section",
            style={"display": "none"},
        ),
        html.Section(
            [
                html.Div(
                    [
                        html.Div(
                            "Hist\u00f3rico de posi\u00e7\u00e3o no indicador",
                            id="municipio-info-indicator-history-title",
                            className="chart-title",
                        ),
                        dcc.Loading(
                            id="municipio-indicator-history-loading",
                            type="circle",
                            color=MUNICIPIO_PRIMARY,
                            children=[
                                dcc.Graph(
                                    id="municipio-info-indicator-history",
                                    config={"displayModeBar": False},
                                ),
                            ],
                        ),
                    ],
                    className="chart-card municipio-info-panel",
                ),
                html.Div(
                    [
                        html.Div(
                            "Valor Observado do indicador no tempo",
                            id="municipio-info-indicator-value-title",
                            className="chart-title",
                        ),
                        dcc.Loading(
                            id="municipio-indicator-value-loading",
                            type="circle",
                            color=MUNICIPIO_PRIMARY,
                            children=[
                                dcc.Graph(
                                    id="municipio-info-indicator-value-history",
                                    config={"displayModeBar": False},
                                ),
                            ],
                        ),
                    ],
                    className="chart-card municipio-info-panel",
                ),
            ],
            id="municipio-info-lower-grid",
            className="municipio-info-main-grid lower",
            style={"display": "none"},
        ),
    ],
    className="page municipio-info-page",
)


@callback(
    Output("filter-ano", "value", allow_duplicate=True),
    Output("filter-regiao", "value", allow_duplicate=True),
    Output("filter-corede", "value", allow_duplicate=True),
    Output("filter-municipio", "value", allow_duplicate=True),
    Input("app-location", "search"),
    State("app-location", "pathname"),
    prevent_initial_call=True,
)
def apply_municipio_query_params(search, pathname):
    if pathname != "/municipios" or not search:
        return (
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
        )

    params = parse_qs(search.lstrip("?"), keep_blank_values=True)

    ano_value = dash.no_update
    if "ano" in params:
        raw_year = params.get("ano", [None])[0]
        if raw_year:
            try:
                ano_value = int(raw_year)
            except ValueError:
                ano_value = dash.no_update

    regiao_value = dash.no_update
    if "regiao" in params:
        regiao = params.get("regiao", [None])[0]
        regiao_value = regiao or dash.no_update

    if "corede" in params:
        corede = params.get("corede", [None])[0]
        corede_value = corede or None
    else:
        corede_value = dash.no_update

    municipio_value = dash.no_update
    if "municipio" in params:
        municipio = params.get("municipio", [None])[0]
        municipio_value = municipio or dash.no_update

    return ano_value, regiao_value, corede_value, municipio_value


@callback(
    Output("filter-regiao", "value", allow_duplicate=True),
    Input({"type": "municipio-overview-card", "region": ALL}, "n_clicks"),
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
    Output("municipio-info-indicator", "options"),
    Output("municipio-info-indicator", "value"),
    Output("municipio-info-indicator-more", "options"),
    Output("municipio-info-indicator-more", "value"),
    Output("municipio-info-indicator-more", "style"),
    Input("filter-ano", "value"),
    Input("filter-regiao", "value"),
    Input("filter-municipio", "value"),
    Input("municipio-info-category", "value"),
    State("municipio-info-indicator", "value"),
)
def update_indicator_options(year, region, municipio, category, current_indicator):
    category = category if category in CATEGORY_LABELS else CATEGORY_DEFAULT
    selected_row, resolved_region = _selected_context(year, region, municipio)
    if selected_row is None:
        return [], None, [], None, {"display": "none"}

    indicator_data = _safe_municipio_indicator_data(
        category, resolved_region, selected_row["municipio"]
    )
    current_rows = _current_indicator_rows(
        category, year, resolved_region, selected_row["municipio"], indicator_data
    )

    all_options = _indicator_options(current_rows)

    values = [option["value"] for option in all_options]
    value = (
        current_indicator
        if current_indicator in values
        else (values[0] if values else None)
    )
    return all_options, value, [], None, {"display": "none"}


@callback(
    Output("municipio-info-context", "children"),
    Output("municipio-info-title", "children"),
    Output("municipio-info-subtitle", "children"),
    Output("municipio-info-hero", "style"),
    Output("municipio-info-category-cards", "children"),
    Output("municipio-info-category-cards", "style"),
    Output("municipio-info-region-list", "children"),
    Output("municipio-info-region-list", "style"),
    Output("municipio-info-back-actions", "style"),
    Output("municipio-info-category-selector", "style"),
    Output("municipio-info-main-grid", "style"),
    Output("municipio-info-indicator-selector", "style"),
    Output("municipio-info-lower-grid", "style"),
    Output("municipio-info-category-history-title", "children"),
    Output("municipio-info-category-radar-title", "children"),
    Output("municipio-info-indicator-history-title", "children"),
    Output("municipio-info-indicator-value-title", "children"),
    Output("municipio-info-category-history", "figure"),
    Output("municipio-info-category-radar", "figure"),
    Output("municipio-info-indicator-history", "figure"),
    Output("municipio-info-indicator-value-history", "figure"),
    Input("filter-ano", "value"),
    Input("filter-regiao", "value"),
    Input("filter-corede", "value"),
    Input("filter-municipio", "value"),
    Input("municipio-info-category", "value"),
    Input("municipio-info-indicator", "value"),
)
def update_municipio_info(year, region, corede, municipio, category, indicator):
    selected_row, resolved_region = _selected_context(year, region, municipio)
    if selected_row is None:
        empty_figure = _empty_figure(
            "Selecione um munic\u00edpio no filtro superior.", height=260
        )
        hero_style = {"display": "none"} if not region else {}
        return (
            html.Div(
                "Selecione um ano e um munic\u00edpio para abrir a an\u00e1lise.",
                className="municipio-info-context-empty",
            ),
            "Informa\u00e7\u00f5es dos munic\u00edpios",
            "Acompanhe a posi\u00e7\u00e3o do munic\u00edpio dentro da sua regi\u00e3o funcional por categoria e por indicador.",
            hero_style,
            [],
            {"display": "none"},
            _region_municipalities_table(year, region, corede),
            {},
            {"display": "none"},
            {"display": "none"},
            {"display": "none"},
            {"display": "none"},
            {"display": "none"},
            "Hist\u00f3rico de posi\u00e7\u00e3o",
            "Notas da dimens\u00e3o",
            "Hist\u00f3rico de posi\u00e7\u00e3o no indicador",
            "Valor Observado do indicador no tempo",
            empty_figure,
            empty_figure,
            empty_figure,
            empty_figure,
        )

    municipio_name = str(selected_row["municipio"])
    category = category if category in CATEGORY_LABELS else CATEGORY_DEFAULT

    ranking = _safe_ranking_data()
    previous_year = _previous_year(year, ranking)
    current_positions = _safe_category_positions(year, resolved_region, None)
    total_municipios = (
        int(current_positions["municipio"].nunique())
        if not current_positions.empty and "municipio" in current_positions.columns
        else 0
    )
    previous_positions = (
        _safe_category_positions(previous_year, resolved_region, None)
        if previous_year is not None
        else pd.DataFrame()
    )
    category_history_data = _safe_municipio_category_history(
        category, resolved_region, municipio_name
    )
    indicator_data = _safe_municipio_indicator_data(
        category, resolved_region, municipio_name
    )

    current_rows = (
        _current_indicator_rows(
            category, year, resolved_region, municipio_name, indicator_data
        )
        if not indicator_data.empty
        else pd.DataFrame()
    )
    selected_indicator_rows = (
        current_rows[current_rows["indicador"] == indicator]
        if indicator and not current_rows.empty
        else pd.DataFrame()
    )
    indicator_label = (
        _indicator_display_label(indicator, selected_indicator_rows.iloc[0])
        if indicator and not selected_indicator_rows.empty
        else _indicator_label(indicator or "indicador")
    )
    category_label = CATEGORY_LABELS.get(category, _fmt_text(category))

    context = html.Div(
        [
            html.Article(
                [
                    html.Div(
                        "Desempenho no porte populacional",
                        className="municipio-info-rank-label",
                    ),
                    html.Div(
                        _classification_badge(
                            selected_row.get("classificacao"),
                            "municipio-info-classification municipio-info-classification--hero",
                        ),
                        className="municipio-info-performance-panel",
                    ),
                ],
                className="municipio-info-context-card municipio-info-performance-card",
            ),
            html.Article(
                [
                    html.Div(
                        f"Posi\u00e7\u00e3o geral na {resolved_region}",
                        className="municipio-info-rank-label",
                    ),
                    html.Div(
                        [
                            html.Strong(
                                _fmt_pos(selected_row.get("ranking_regiao_funcional"))
                            ),
                            html.Span(
                                _icon("trophy", 26),
                                className="municipio-info-rank-icon",
                            ),
                        ],
                        className="municipio-info-rank-value",
                    ),
                ],
                className="municipio-info-context-card municipio-info-position-card",
            ),
        ],
        className="municipio-info-rank-panel",
    )
    title = [
        municipio_name,
        html.Div(
            "Munic\u00edpio",
            className="municipio-info-title-badge",
        ),
    ]
    subtitle = [
        html.Span(
            f"{resolved_region} • {_fmt_text(selected_row.get('corede'))}",
            className="municipio-info-subtitle-context",
        ),
    ]
    if total_municipios > 0:
        subtitle.append(
            html.Span(
                f"Posi\u00e7\u00f5es calculadas entre os {total_municipios} munic\u00edpios da {resolved_region}.",
                className="municipio-info-subtitle-summary",
            )
        )

    return (
        context,
        title,
        subtitle,
        {},
        _category_cards(
            year,
            resolved_region,
            municipio_name,
            category,
            current_positions,
            previous_positions,
            previous_year,
        ),
        {},
        html.Div(),
        {"display": "none"},
        {},
        {},
        {},
        {},
        {},
        f"Hist\u00f3rico de posi\u00e7\u00e3o - {category_label}",
        f"Notas da dimens\u00e3o - {category_label}",
        f"Hist\u00f3rico de posi\u00e7\u00e3o - {indicator_label}",
        f"Valor Observado - {indicator_label}",
        _category_history_figure(
            category, resolved_region, municipio_name, category_history_data
        ),
        _category_radar_figure(
            category, year, resolved_region, municipio_name, indicator_data
        ),
        _indicator_history_figure(
            category, resolved_region, municipio_name, indicator, indicator_data
        ),
        _indicator_value_history_figure(
            category, resolved_region, municipio_name, indicator, indicator_data
        ),
    )


@callback(
    Output("filter-municipio", "value", allow_duplicate=True),
    Output("filter-corede", "value", allow_duplicate=True),
    Input({"type": "municipio-info-row", "municipio": ALL, "corede": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def select_municipio_from_region_table(_clicks):
    if not _clicks or not any(clicks for clicks in _clicks if clicks):
        return dash.no_update, dash.no_update

    triggered = ctx.triggered_id
    if isinstance(triggered, dict):
        return triggered.get("municipio"), triggered.get("corede")
    return dash.no_update, dash.no_update


@callback(
    Output("filter-municipio", "value", allow_duplicate=True),
    Input("municipio-info-back-button", "n_clicks"),
    prevent_initial_call=True,
)
def back_to_municipio_selection(n_clicks):
    if not n_clicks:
        return dash.no_update
    return None


@callback(
    Output("municipio-info-category", "value"),
    Input({"type": "category-card", "category": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def select_category_from_card(_clicks):
    if not _clicks or not any(clicks for clicks in _clicks if clicks):
        return dash.no_update

    triggered = ctx.triggered_id
    if isinstance(triggered, dict):
        return triggered.get("category")
    return dash.no_update
