import logging
import os
import re
import threading
import textwrap
import time
import unicodedata
from functools import lru_cache
from urllib.parse import parse_qs, urlencode

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, callback, ctx, dcc, html

from src.indicator_metadata import get_indicator_methodology
from src.data_loader import (
    filter_ranking_data,
    get_category_labels,
    load_category_data,
    load_category_positions,
    load_indicator_regional_medians,
    load_indicator_names,
    load_municipio_category_history_data,
    load_municipio_indicator_data,
    load_municipio_summary_data,
    load_ranking_data,
)


logger = logging.getLogger(__name__)
logger.propagate = False

PERF_LOGS = os.getenv("APP_PERF_LOGS", "0") == "1"

if not logger.hasHandlers():
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)

logger.setLevel(logging.DEBUG if PERF_LOGS else logging.WARNING)

_perf_labels: dict[str, int] = {}


def _perf(label: str) -> None:
    _perf_labels.setdefault(label, 0)
    _perf_labels[label] += 1
    count = _perf_labels[label]
    if count > 1 and PERF_LOGS:
        logger.debug("[PERF] %s (call #%d)", label, count)


def _perf_start(label: str) -> float:
    _perf(label)
    return time.perf_counter()


def _perf_elapsed(label: str, start: float) -> None:
    if PERF_LOGS:
        logger.debug("[PERF] %s: %.1f ms", label, (time.perf_counter() - start) * 1000)


dash.register_page(__name__, path="/municipios", name="Munic\u00edpios")

CATEGORY_LABELS = get_category_labels()
CATEGORY_ORDER = list(CATEGORY_LABELS)
CATEGORY_DEFAULT = CATEGORY_ORDER[0] if CATEGORY_ORDER else "saude"
GENERAL_CATEGORY = "geral"
CATEGORY_SELECTOR_LABELS = {
    GENERAL_CATEGORY: "Geral",
    **CATEGORY_LABELS,
}
CATEGORY_SELECTOR_ORDER = [
    GENERAL_CATEGORY,
    *CATEGORY_ORDER,
]
CATEGORY_ICONS = {
    "educacao": "book",
    "financas": "coin",
    "meio_ambiente": "tree",
    "saude": "heart-pulse",
    "seguranca": "shield-check",
    "socioeconomico": "people",
}
CATEGORY_SELECTOR_ICONS = {
    GENERAL_CATEGORY: "house-door",
    **CATEGORY_ICONS,
}
CLASSIFICACAO_TOOLTIP = "Classifica o município considerando seu desempenho em relação ao seu tamanho populacional."
MUNICIPIO_PRIMARY = "#b7791f"
MUNICIPIO_PRIMARY_FILL = "rgba(183, 121, 31, 0.12)"
MUNICIPIO_ACCENT = "#8a5a12"
MUNICIPIO_AVERAGE = "#64748b"
REGIONAL_REFERENCE_LABEL = "Mediana"
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


def _dimension_rank_class(position, total) -> str:
    pos = _pos_num(position)
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = None

    base = "dimension-rank-pill"

    if pos is None or not total or total < 1:
        return f"{base} is-neutral"
    if total == 1:
        return f"{base} is-top"

    percentile = pos / total

    if percentile <= 0.25:
        return f"{base} is-top"
    if percentile <= 0.5:
        return f"{base} is-good"
    if percentile <= 0.75:
        return f"{base} is-mid"
    return f"{base} is-low"


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
    if "abaixo" in normalized or "baixo" in normalized:
        return "low"
    if "intervalo" in normalized or "dentro" in normalized or "esperado" in normalized:
        return "range"
    return "neutral" if text else "missing"


def _classification_display_label(value) -> str:
    text = _fmt_text(value)
    normalized = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        .strip()
    )
    if normalized == "baixo":
        return "Abaixo"
    return text


def _classification_badge(value, class_name: str = ""):
    status = _classification_status(value)
    label = _classification_display_label(value)
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
    "adequacao_formacao_docente": "Adequa\u00e7\u00e3o da Forma\u00e7\u00e3o Docente",
    "saeb_ensino_fundamental": "Nota do SAEB - Ensino Fundamental",
    "saeb_ensino_fundamental_media": "Nota do SAEB - Ensino Fundamental",
    "taxa_cobertura_creche": "Taxa de Cobertura de Creche",
    "taxa_distorcao_fundamental": "Taxa de Distor\u00e7\u00e3o Idade-S\u00e9rie - Ensino Fundamental",
    "proporcao_consultas_pre_natal": "Propor\u00e7\u00e3o de nascidos vivos de m\u00e3es com 7 ou mais consultas de pr\u00e9-natal",
    "proporcao_de_gravidas_com_pelo_menos_7_consultas_pre_natal": "Propor\u00e7\u00e3o de nascidos vivos de m\u00e3es com 7 ou mais consultas de pr\u00e9-natal",
    "geracao_emprego_per_capita": "Gera\u00e7\u00e3o de empregos por 1.000 habitantes",
    "geracao_de_emprego_per_capita": "Gera\u00e7\u00e3o de empregos por 1.000 habitantes",
}

PERCENT_INDICATOR_MULTIPLIERS = {
    "qt_acesso_infor": 1,
    "formalidade_mercado_trabalho": 100,
    "proporcao_pessoas_baixa_renda": 1,
    "vulnerabilidade_social": 1,
    "proporcao_gravidez_adolescencia": 1,
    "proporcao_de_gravidez_na_adolescencia": 1,
    "proporcao_consultas_pre_natal": 1,
    "proporcao_de_gravidas_com_pelo_menos_7_consultas_pre_natal": 1,
    "proporcao_de_nascidos_vivos_de_maes_com_7_ou_mais_consultas_de_pre_natal": 1,
    "cobertura_acs": 1,
    "cobertura_aps": 1,
    "cobertura_vacinal_penta_polio_media": 1,
    "taxa_cobertura_creche": 1,
    "taxa_distorcao_fundamental": 1,
    "adequacao_formacao_docente": 1,
    "proporcao_atendimento_agua": 1,
    "prop_atendimento_agua": 1,
    "proporcao_coleta_residuos": 1,
    "prop_coleta_residuos": 1,
    "indice_perdas_distribuicao": 1,
    "desmatamento_area": 1,
    "desmatamento_por_area": 1,
}

SCALE_MULTIPLIERS = {
    "geracao_emprego_per_capita": 1000,
}

MONETARY_INDICATORS = frozenset({
    "pib_per_capita",
    "renda_media",
})

INDICATOR_AXIS_LABELS = {
    "proporcao_gravidez_adolescencia": "Nascidos vivos (%)",
    "proporcao_de_gravidez_na_adolescencia": "Nascidos vivos (%)",
    "proporcao_consultas_pre_natal": "Nascidos vivos (%)",
    "proporcao_de_gravidas_com_pelo_menos_7_consultas_pre_natal": "Nascidos vivos (%)",
    "proporcao_de_nascidos_vivos_de_maes_com_7_ou_mais_consultas_de_pre_natal": "Nascidos vivos (%)",
    "cobertura_acs": "Cobertura (%)",
    "cobertura_aps": "Cobertura (%)",
    "cobertura_vacinal_penta_polio_media": "Cobertura vacinal (%)",
    "obitos_causas_evitaveis_mil_habitantes": "\u00d3bitos por mil habitantes",
    "obitos_por_causas_evitaveis_por_mil_habitantes": "\u00d3bitos por mil habitantes",
    "medicos_por_mil_habitantes": "M\u00e9dicos por mil habitantes",
    "taxa_cobertura_creche": "Cobertura (%)",
    "taxa_distorcao_fundamental": "Taxa (%)",
    "adequacao_formacao_docente": "Docentes com forma\u00e7\u00e3o adequada (%)",
    "qt_acesso_infor": "Acesso \u00e0 informa\u00e7\u00e3o (%)",
    "proporcao_atendimento_agua": "Atendimento (%)",
    "prop_atendimento_agua": "Atendimento (%)",
    "proporcao_coleta_residuos": "Coleta de res\u00edduos (%)",
    "prop_coleta_residuos": "Coleta de res\u00edduos (%)",
    "indice_perdas_distribuicao": "Perdas na distribui\u00e7\u00e3o (%)",
    "desmatamento_area": "(%) \u00c1rea desmatada",
    "desmatamento_por_area": "(%) \u00c1rea desmatada",
    "emissao_gases_per_capita": "MtCO2",
    "emissao_de_gases_per_capita": "MtCO2",
    "proporcao_pessoas_baixa_renda": "Popula\u00e7\u00e3o (%)",
    "vulnerabilidade_social": "(%) da popula\u00e7\u00e3o",
    "mulheres_empregadas_com_no_minimo_ensino_medio_por_1000_mulheres": "Por mil mulheres",
    "mulheres_empregadas_com_no_minimo_ensino_medio_por_1_000_mulheres": "Por mil mulheres",
    "mulheres_empregadas_ensino_medio_ou_mais_por_1000_mulheres": "Por mil mulheres",
    "formalidade_mercado_trabalho": "Formalidade (%)",
    "vinculos_per_capita": "V\u00ednculos por habitante",
    "vinculos_ativos_per_capita": "V\u00ednculos por habitante",
    "geracao_emprego_per_capita": "Empregos gerados por 1.000 habitantes",
    "renda_media": "Renda m\u00e9dia",
    "pib_per_capita": "PIB per capita",
    "roubos_por_10_mil_habitantes": "Ocorr\u00eancias por 10 mil habitantes",
    "roubos_por_10mil_hab": "Ocorr\u00eancias por 10 mil habitantes",
    "furtos_por_10_mil_habitantes": "Ocorr\u00eancias por 10 mil habitantes",
    "furtos_por_10mil_hab": "Ocorr\u00eancias por 10 mil habitantes",
    "armas_por_10_mil_habitantes": "Ocorr\u00eancias por 10 mil habitantes",
    "delitos_com_armas_por_10_mil_habitantes": "Ocorr\u00eancias por 10 mil habitantes",
    "delitos_armas_10_mil_habitantes": "Ocorr\u00eancias por 10 mil habitantes",
    "delitos_com_armas_por_10mil_hab": "Ocorr\u00eancias por 10 mil habitantes",
    "homicidios_dolosos_por_10_mil_habitantes": "Ocorr\u00eancias por 10 mil habitantes",
    "homicidio_doloso_por_10mil_hab": "Ocorr\u00eancias por 10 mil habitantes",
    "ameacas_por_10_mil_mulheres": "Ocorr\u00eancias por 10 mil mulheres",
    "ameaca_por_10mil_mulheres": "Ocorr\u00eancias por 10 mil mulheres",
    "estupros_por_10_mil_mulheres": "Ocorr\u00eancias por 10 mil mulheres",
    "estupro_por_10mil_mulheres": "Ocorr\u00eancias por 10 mil mulheres",
    "roubos_e_furtos_de_veiculos_por_10_mil_veiculos": "Ocorr\u00eancias por 10 mil ve\u00edculos",
    "roubos_furtos_veiculos_10_mil_veiculos": "Ocorr\u00eancias por 10 mil ve\u00edculos",
    "roubos_furtos_veiculos_por_10mil_veiculos": "Ocorr\u00eancias por 10 mil ve\u00edculos",
}

INDICATOR_DIRECTION_MAP = {
    # Educacao
    "qt_acesso_infor": "higher_better",
    "saeb_ensino_fundamental": "higher_better",
    "saeb_ensino_fundamental_media": "higher_better",
    "taxa_cobertura_creche": "higher_better",
    "taxa_distorcao_fundamental": "lower_better",
    "adequacao_formacao_docente": "higher_better",
    # Financas
    "execucao_orcamentaria_corrente": "lower_better",
    "exec_orc_corrente": "lower_better",
    "despesas_pessoal": "lower_better",
    "endividamento": "lower_better",
    "geracao_caixa": "higher_better",
    "geracao_de_caixa": "higher_better",
    "disponibilidade_caixa": "higher_better",
    "investimentos": "higher_better",
    "investimento": "higher_better",
    "restos_pagar": "lower_better",
    "restos_a_pagar": "lower_better",
    "autonomia_fiscal": "higher_better",
    # Meio ambiente
    "emissao_gases_per_capita": "lower_better",
    "proporcao_atendimento_agua": "higher_better",
    "prop_atendimento_agua": "higher_better",
    "proporcao_coleta_residuos": "higher_better",
    "prop_coleta_residuos": "higher_better",
    "indice_perdas_distribuicao": "lower_better",
    "desmatamento_area": "lower_better",
    "desmatamento_por_area": "lower_better",
    "incidencia_coliformes": "lower_better",
    # Saude
    "obitos_causas_evitaveis_mil_habitantes": "lower_better",
    "proporcao_consultas_pre_natal": "higher_better",
    "cobertura_vacinal_penta_polio_media": "higher_better",
    "proporcao_gravidez_adolescencia": "lower_better",
    "cobertura_aps": "higher_better",
    "medicos_por_mil_habitantes": "higher_better",
    "cobertura_acs": "higher_better",
    # Seguranca
    "roubos_por_10_mil_habitantes": "lower_better",
    "roubos_por_10mil_hab": "lower_better",
    "armas_por_10_mil_habitantes": "lower_better",
    "delitos_com_armas_por_10_mil_habitantes": "lower_better",
    "delitos_armas_10_mil_habitantes": "lower_better",
    "delitos_com_armas_por_10mil_hab": "lower_better",
    "furtos_por_10_mil_habitantes": "lower_better",
    "furtos_por_10mil_hab": "lower_better",
    "homicidios_dolosos_por_10_mil_habitantes": "lower_better",
    "homicidio_doloso_por_10mil_hab": "lower_better",
    "ameacas_por_10_mil_mulheres": "lower_better",
    "ameaca_por_10mil_mulheres": "lower_better",
    "estupros_por_10_mil_mulheres": "lower_better",
    "estupro_por_10mil_mulheres": "lower_better",
    "roubos_e_furtos_de_veiculos_por_10_mil_veiculos": "lower_better",
    "roubos_furtos_veiculos_10_mil_veiculos": "lower_better",
    "roubos_furtos_veiculos_por_10mil_veiculos": "lower_better",
    # Socioeconomico
    "vulnerabilidade_social": "lower_better",
    "mulheres_empregadas_com_no_minimo_ensino_medio_por_1000_mulheres": "higher_better",
    "mulheres_empregadas_ensino_medio_ou_mais_por_1000_mulheres": "higher_better",
    "proporcao_pessoas_baixa_renda": "lower_better",
    "vinculos_ativos_per_capita": "higher_better",
    "vinculos_per_capita": "higher_better",
    "formalidade_mercado_trabalho": "higher_better",
    "renda_media": "higher_better",
    "pib_per_capita": "higher_better",
    "geracao_emprego_per_capita": "higher_better",
}

INDICATOR_DIRECTION_SUBTITLE_MAP = {
    "execucao_orcamentaria_corrente": "Quanto menor, melhor, indicando f\u00f4lego para assumir novos compromissos financeiros.",
    "exec_orc_corrente": "Quanto menor, melhor, indicando f\u00f4lego para assumir novos compromissos financeiros.",
    "autonomia_fiscal": "Quanto maior, melhor, indicando menor depend\u00eancia de transfer\u00eancias de outros entes e autossufici\u00eancia.",
    "endividamento": "Quanto menor, melhor, indicando menores compromissos financeiros e maior disponibilidade para a busca de recursos com opera\u00e7\u00f5es de cr\u00e9dito.",
    "despesas_pessoal": "Quanto menor, melhor, indicando menores compromissos com despesas continuadas.",
    "investimentos": "Quanto maior, melhor, indicando maior disponibiliza\u00e7\u00e3o de recursos para despesas de capital em rela\u00e7\u00e3o a despesas de custeio.",
    "investimento": "Quanto maior, melhor, indicando maior disponibiliza\u00e7\u00e3o de recursos para despesas de capital em rela\u00e7\u00e3o a despesas de custeio.",
    "disponibilidade_caixa": "Quanto maior, melhor, indicando a exist\u00eancia de reserva financeira para manuten\u00e7\u00e3o de servi\u00e7os.",
    "geracao_caixa": "Quanto maior, melhor, indicando a sobra de recursos financeiros ao final do per\u00edodo.",
    "geracao_de_caixa": "Quanto maior, melhor, indicando a sobra de recursos financeiros ao final do per\u00edodo.",
    "restos_pagar": "Quanto menor, melhor. \u00cdndices altos podem significar contas em atraso.",
    "restos_a_pagar": "Quanto menor, melhor. \u00cdndices altos podem significar contas em atraso.",
}


def _indicator_key(value: str | None) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", ascii_value.lower())).strip(
        "_"
    )


def _normalize_sort_text(value) -> str:
    text = "" if value is None or pd.isna(value) else str(value)
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode("ascii").casefold().strip()


def _indicator_label(value: str) -> str:
    identifier = str(value or "").strip()
    try:
        friendly_name = load_indicator_names().get(identifier)
    except Exception as exc:
        logger.error("Erro ao carregar nomes dos indicadores: %s", exc)
        friendly_name = None
    fallback_label = INDICATOR_FALLBACK_LABELS.get(
        identifier, INDICATOR_FALLBACK_LABELS.get(_indicator_key(identifier))
    )
    if friendly_name:
        friendly_key = _indicator_key(friendly_name)
        return INDICATOR_FALLBACK_LABELS.get(friendly_key, friendly_name)
    if fallback_label:
        return fallback_label
    return identifier.replace("_", " ").capitalize()


def _indicator_display_label(value: str, row=None) -> str:
    if row is not None:
        try:
            name = row.get("indicador_nome")
        except AttributeError:
            name = None
        if name is not None and not pd.isna(name):
            text = str(name).strip()
            fallback_label = INDICATOR_FALLBACK_LABELS.get(_indicator_key(text))
            if fallback_label:
                return fallback_label
            if text and text != str(value or "").strip():
                return text
    return _indicator_label(str(value or ""))


def _indicator_direction_from_row(row=None) -> str | None:
    if row is None:
        return None

    candidate_columns = [
        "direcao",
        "sentido",
        "sentido_indicador",
        "polaridade",
        "tipo_indicador",
        "maior_melhor",
        "quanto_maior_melhor",
        "melhor_quando",
        "indicador_direcao",
        "orientacao",
    ]
    higher_values = {
        "maior_melhor",
        "maior_e_melhor",
        "maior_melhor",
        "higher_better",
        "positive",
        "positivo",
        "1",
        "true",
        "sim",
    }
    lower_values = {
        "menor_melhor",
        "menor_e_melhor",
        "lower_better",
        "negative",
        "negativo",
        "-1",
        "false",
        "nao",
        "não",
    }

    for column in candidate_columns:
        try:
            value = row.get(column)
        except AttributeError:
            value = None
        if value is None or pd.isna(value):
            continue

        text = str(value).strip().lower()
        normalized = _indicator_key(text)
        if text in higher_values or normalized in higher_values:
            return "higher_better"
        if text in lower_values or normalized in lower_values:
            return "lower_better"
    return None


def _indicator_direction(indicator: str | None, row=None) -> str:
    direction = _indicator_direction_from_row(row)
    if direction:
        return direction
    return INDICATOR_DIRECTION_MAP.get(_indicator_key(indicator), "unknown")


def _indicator_specific_direction_subtitle(indicator: str | None) -> str | None:
    if indicator is None:
        return None
    key = _indicator_key(indicator)
    return INDICATOR_DIRECTION_SUBTITLE_MAP.get(key)


def _indicator_direction_text(
    direction: str, indicator: str | None = None, row=None
) -> str:
    specific_text = _indicator_specific_direction_subtitle(indicator)
    if specific_text:
        return specific_text
    if direction == "higher_better":
        return "Valores mais altos indicam melhor desempenho neste indicador."
    if direction == "lower_better":
        return "Valores mais altos indicam pior desempenho neste indicador."
    return "Dire\u00e7\u00e3o interpretativa do indicador n\u00e3o informada."


def _indicator_direction_class(direction: str) -> str:
    if direction == "higher_better":
        return "is-higher-better"
    if direction == "lower_better":
        return "is-lower-better"
    return "is-unknown"


def _indicator_multiplier(indicator: str | None):
    raw_key = str(indicator or "").strip()
    normalized_key = _indicator_key(indicator)
    if raw_key in PERCENT_INDICATOR_MULTIPLIERS:
        return PERCENT_INDICATOR_MULTIPLIERS[raw_key]
    return PERCENT_INDICATOR_MULTIPLIERS.get(normalized_key)


def _is_percent_indicator(indicator: str | None) -> bool:
    return _indicator_multiplier(indicator) is not None


def _indicator_axis_title(indicator: str | None) -> str:
    return INDICATOR_AXIS_LABELS.get(_indicator_key(indicator), "Valor do indicador")


def _indicator_observed_display_value(value, indicator: str | None):
    if value is None or pd.isna(value):
        return None
    numeric_value = float(value)
    multiplier = _indicator_multiplier(indicator)
    if multiplier is not None:
        return numeric_value * multiplier
    key = _indicator_key(indicator)
    if key in SCALE_MULTIPLIERS:
        return numeric_value * SCALE_MULTIPLIERS[key]
    return numeric_value


def _fmt_indicator_observed_value(value, indicator: str | None) -> str:
    display_value = _indicator_observed_display_value(value, indicator)
    if display_value is None or pd.isna(display_value):
        return "-"
    suffix = "%" if _is_percent_indicator(indicator) else ""
    return f"{_fmt_num(display_value)}{suffix}"


def _is_monetary_indicator(indicator: str | None) -> bool:
    return _indicator_key(indicator) in MONETARY_INDICATORS


def _fmt_indicator_display_value(value, indicator: str | None) -> str:
    base = _fmt_indicator_observed_value(value, indicator)
    if _is_monetary_indicator(indicator):
        return f"R$ {base}"
    return base


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
    "ameacas por 10 mil mulheres": "Amea\u00e7as<br>por 10 mil<br>mulheres",
    "armas por 10 mil habitantes": "Armas<br>por 10 mil<br>habitantes",
    "estupros por 10 mil mulheres": "Estupros<br>por 10 mil<br>mulheres",
    "furtos por 10 mil habitantes": "Furtos<br>por 10 mil<br>habitantes",
    "homicidios dolosos por 10 mil habitantes": "Homic\u00eddios<br>dolosos por<br>10 mil hab.",
    "roubos por 10 mil habitantes": "Roubos<br>por 10 mil<br>habitantes",
    "saeb ensino fundamental": "SAEB<br>fundamental",
    "taxa cobertura creche": "Cobertura<br>creche",
    "taxa distorcao fundamental": "Distor\u00e7\u00e3o<br>fundamental",
    "geracao emprego per capita": "Empregos<br>por 1.000 hab.",
}


def _radar_label(
    value: str,
    width: int = 10,
    use_indicator_label: bool = True,
) -> str:
    normalized = str(value or "").replace("_", " ").strip().lower()
    if normalized in RADAR_LABELS:
        return RADAR_LABELS[normalized]

    label = _indicator_label(value) if use_indicator_label else str(value or "")
    label = " ".join(str(label).replace("_", " ").split())
    if not label:
        return ""

    lines = textwrap.wrap(
        label,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return "<br>".join(lines) if lines else label


def _top_line_chart_layout(height: int = 265) -> dict:
    return dict(
        height=height,
        margin=dict(l=40, r=18, t=24, b=18),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )


def _lower_line_chart_layout(height: int = 210) -> dict:
    return dict(
        height=height,
        margin=dict(l=40, r=20, t=30, b=28),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )


def _compact_line_xaxis() -> dict:
    return dict(
        tickmode="linear",
        showgrid=False,
        color="#102542",
        tickfont=dict(size=9),
    )


def _compact_rank_axis_range(values, max_rank: int | None = None, padding: int = 2):
    series = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    if series.empty:
        return [max_rank + 2, 0] if max_rank else None

    min_pos = int(series.min())
    max_pos = int(series.max())

    upper = max(1, min_pos - padding)
    lower = max_pos + padding

    if max_rank:
        lower = min(lower, int(max_rank) + 1)

    if lower <= upper:
        lower = upper + 2

    return [lower, upper]


def _compact_position_yaxis(max_rank: int = 0, rank_values=None) -> dict:
    if rank_values is not None:
        axis_range = _compact_rank_axis_range(rank_values, max_rank=max_rank, padding=2)
        autorange_setting = False
    else:
        axis_range = [max_rank + 6, 0] if max_rank else None
        autorange_setting = "reversed"

    return dict(
        title=dict(text="Posi\u00e7\u00e3o", font=dict(size=9, color="#526277")),
        autorange=autorange_setting,
        range=axis_range,
        showticklabels=True,
        tickfont=dict(size=9, color="#526277"),
        ticks="",
        gridcolor="#e5ebef",
        zeroline=False,
        fixedrange=True,
    )


def _radar_compact_height(category: str | None, labels: list[str] | None = None) -> int:
    complex_categories = {"seguranca", "saude", "socioeconomico"}
    label_count = len(labels or [])
    max_breaks = max((str(label).count("<br>") for label in labels or []), default=0)

    if category in complex_categories or label_count >= 7 or max_breaks >= 3:
        return 300
    if label_count <= 5:
        return 270
    return 285


def _compact_radar_layout(category: str | None, labels: list[str]) -> dict:
    return dict(
        height=_radar_compact_height(category, labels),
        margin=dict(l=64, r=104, t=20, b=34),
        paper_bgcolor="rgba(0,0,0,0)",
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            domain=dict(x=[0.14, 0.68], y=[0.13, 0.88]),
            radialaxis=dict(
                range=[0, 10],
                tickvals=[0, 2.5, 5, 7.5, 10],
                showticklabels=False,
                gridcolor="#dfe7ed",
            ),
            angularaxis=dict(
                tickfont=dict(size=8, color="#102542"),
                gridcolor="#dfe7ed",
                rotation=90,
                direction="clockwise",
            ),
        ),
        legend=dict(
            x=0.79,
            y=0.86,
            xanchor="left",
            yanchor="top",
            orientation="v",
            bgcolor="rgba(255,255,255,0.92)",
            bordercolor="#d8e1e8",
            borderwidth=1,
            font=dict(size=9, color="#102542"),
            itemwidth=30,
        ),
        showlegend=True,
    )


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


@lru_cache(maxsize=1)
def _safe_ranking_data_cached() -> pd.DataFrame:
    # Cache por sessao/processo; reinicie o app para limpar apos atualizacao de dados.
    _perf("_safe_ranking_data")
    try:
        return load_ranking_data()
    except Exception as exc:
        logger.error("Erro ao carregar ranking_municipios: %s", exc)
        return pd.DataFrame()


def _safe_ranking_data() -> pd.DataFrame:
    return _safe_ranking_data_cached().copy()


@lru_cache(maxsize=16)
def _safe_category_data_cached(category: str) -> pd.DataFrame:
    return load_category_data(category)


def _safe_category_data(category: str) -> pd.DataFrame:
    _perf("_safe_category_data")
    try:
        return _safe_category_data_cached(category)
    except Exception as exc:
        logger.error("Erro ao carregar categoria %s: %s", category, exc)
        return pd.DataFrame()


def _safe_category_positions(
    year, region: str | None, corede: str | None
) -> pd.DataFrame:
    try:
        return load_category_positions(year, region, corede)
    except Exception as exc:
        logger.error("Erro ao carregar posicoes das categorias: %s", exc)
        return pd.DataFrame()


def _category_positions_for_year(year, region: str | None) -> pd.DataFrame:
    return _safe_category_positions(year, region, None)


def _safe_municipio_summary(
    year=None,
    region: str | None = None,
    corede: str | None = None,
    municipio: str | None = None,
) -> pd.DataFrame:
    _perf("_safe_municipio_summary")
    try:
        return load_municipio_summary_data(year, region, corede, municipio)
    except Exception as exc:
        logger.error("Erro ao carregar resumo otimizado de municipios: %s", exc)
        return pd.DataFrame()


def _safe_municipio_category_history(
    category: str, region: str | None, municipio: str | None
) -> pd.DataFrame:
    try:
        return load_municipio_category_history_data(category, region, municipio)
    except Exception as exc:
        logger.error("Erro ao carregar historico otimizado da categoria: %s", exc)
        return pd.DataFrame()


@lru_cache(maxsize=128)
def _safe_municipio_indicator_data_cached(
    category: str,
    region: str | None,
    municipio: str | None,
    indicator: str | None = None,
) -> pd.DataFrame:
    return load_municipio_indicator_data(category, region, municipio, indicator)


def _safe_municipio_indicator_data(
    category: str,
    region: str | None,
    municipio: str | None,
    indicator: str | None = None,
) -> pd.DataFrame:
    try:
        return _safe_municipio_indicator_data_cached(
            category, region, municipio, indicator
        ).copy()
    except Exception as exc:
        logger.error("Erro ao carregar indicadores otimizados do municipio: %s", exc)
        return pd.DataFrame()


def _safe_indicator_regional_medians(
    category: str,
    region: str | None = None,
    year=None,
    indicator: str | None = None,
) -> pd.DataFrame:
    try:
        return load_indicator_regional_medians(category, region, year, indicator)
    except Exception as exc:
        logger.error("Erro ao carregar medianas regionais dos indicadores: %s", exc)
        return pd.DataFrame()


def _regional_median_category_column(frame: pd.DataFrame) -> str | None:
    for column in ("categoria", "dimensao", "category"):
        if column in frame.columns:
            return column
    return None


def _filter_regional_medians(
    regional_medians: pd.DataFrame | None,
    category: str,
    region: str | None = None,
    year=None,
    indicator: str | None = None,
) -> pd.DataFrame:
    if regional_medians is None or regional_medians.empty:
        return pd.DataFrame()

    frame = regional_medians.copy()
    mask = pd.Series(True, index=frame.index)
    if year is not None and "ano" in frame.columns:
        mask &= pd.to_numeric(frame["ano"], errors="coerce") == int(year)
    if region and "regiao_funcional" in frame.columns:
        mask &= frame["regiao_funcional"].astype(str) == str(region)
    if indicator and "indicador" in frame.columns:
        mask &= frame["indicador"].astype(str) == str(indicator)

    category_column = _regional_median_category_column(frame)
    if category_column:
        mask &= frame[category_column].astype(str) == str(category)

    return frame[mask].copy()


def _regional_median_value(
    regional_medians: pd.DataFrame | None,
    category: str,
    region: str | None,
    year,
    indicator: str,
    value_column: str,
):
    filtered = _filter_regional_medians(
        regional_medians, category, region, year, indicator
    )
    if filtered.empty or value_column not in filtered.columns:
        return None
    values = pd.to_numeric(filtered[value_column], errors="coerce").dropna()
    if values.empty:
        return None
    return values.iloc[0]


def _prefetch_municipio_detail_data(
    year,
    region: str | None,
    category: str | None = None,
    previous_year: int | None = None,
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
            resolved_previous_year = previous_year
            if resolved_previous_year is None:
                ranking = _safe_ranking_data()
                resolved_previous_year = _previous_year(year, ranking)
            if resolved_previous_year is not None:
                _safe_category_positions(resolved_previous_year, region, None)
        except Exception as exc:
            logger.error("Erro no pre-carregamento de municipio: %s", exc)

    threading.Thread(target=worker, daemon=True).start()


def _selected_context(
    year,
    region,
    municipio,
    ranking_df: pd.DataFrame | None = None,
):
    if year is None or not municipio:
        return None, region

    ranking = ranking_df if ranking_df is not None else _safe_ranking_data()
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
                                "Selecione uma regi\u00e3o funcional ou um munic\u00edpio",
                                className="regional-title",
                            ),
                            html.P(
                                "Escolha uma regi\u00e3o funcional para explorar o ranking regional ou selecione diretamente um munic\u00edpio no filtro acima para abrir seus detalhes.",
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
                                "Selecione uma regi\u00e3o funcional ou um munic\u00edpio para explorar rankings, indicadores e detalhes."
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


def _region_total_for_rank_color(
    year, region: str | None, ranking: pd.DataFrame | None = None
) -> int:
    if year is None or not region:
        return 0

    ranking_frame = ranking if ranking is not None else _safe_ranking_data()
    if ranking_frame.empty:
        return 0

    region_frame = ranking_frame[
        (ranking_frame["ano"] == int(year))
        & (ranking_frame["regiao_funcional"] == region)
    ].copy()

    if region_frame.empty or "municipio" not in region_frame.columns:
        return 0

    return int(region_frame["municipio"].nunique())


def _cache_key_text(value) -> str:
    return "" if value is None else str(value)


@lru_cache(maxsize=64)
def _region_municipalities_table_data(
    year: int, region_key: str, corede_key: str
) -> tuple[list[dict], dict[str, dict], int, int | None]:
    region = region_key or None
    corede = corede_key or None
    summary = _safe_municipio_summary(year, region, corede)
    ranking = _safe_ranking_data()
    region_total_for_color = _region_total_for_rank_color(year, region, ranking)

    if ranking.empty:
        return [], {}, 0, None

    previous_year = _previous_year(year, ranking)

    if summary.empty:
        frame = ranking[ranking["ano"] == int(year)].copy()
        if region:
            frame = frame[frame["regiao_funcional"] == region]
        if corede:
            frame = frame[frame["corede"] == corede]
    else:
        frame = summary.copy()

    if frame.empty:
        return [], {}, region_total_for_color, previous_year

    frame = _with_classificacao_from_ranking(frame, ranking)
    frame = frame.sort_values(["ranking_regiao_funcional", "municipio"])

    if region_total_for_color < 1:
        region_total_for_color = int(frame["municipio"].nunique())

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

    return (
        frame.to_dict("records"),
        category_positions,
        region_total_for_color,
        previous_year,
    )


def _region_municipalities_table(year, region: str | None, corede: str | None):
    if year is None:
        return _empty_state("Sem dados de munic\u00edpios para listar.")

    if not region and not corede:
        ranking = _safe_ranking_data()
        if ranking.empty:
            return _empty_state("Sem dados de munic\u00edpios para listar.")
        return _build_region_overview(year)

    records, category_positions, region_total_for_color, previous_year = (
        _region_municipalities_table_data(
            int(year), _cache_key_text(region), _cache_key_text(corede)
        )
    )
    if not records:
        return _empty_state("N\u00e3o h\u00e1 munic\u00edpios no recorte selecionado.")

    if region:
        _prefetch_municipio_detail_data(year, region, CATEGORY_DEFAULT, previous_year)

    header_cells = [
        html.Th("Geral"),
        html.Th("Munic\u00edpio"),
        html.Th("Corede"),
        html.Th(
            [
                html.Span("Desempenho no porte populacional"),
                html.Span("i", className="header-info-icon"),
                html.Div(
                    [
                        html.Div(
                            "Desempenho no porte populacional",
                            className="classification-tooltip-title",
                        ),
                        html.Div(
                            CLASSIFICACAO_TOOLTIP,
                            className="classification-tooltip-description",
                        ),
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Span(
                                            className="classification-tooltip-dot is-above"
                                        ),
                                        html.Span(
                                            "ACIMA",
                                            className="classification-tooltip-term",
                                        ),
                                    ],
                                    className="classification-tooltip-term-row",
                                ),
                                html.Div(
                                    "Desempenho acima do esperado para o porte populacional.",
                                    className="classification-tooltip-text",
                                ),
                            ],
                            className="classification-tooltip-section",
                        ),
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Span(
                                            className="classification-tooltip-dot is-range"
                                        ),
                                        html.Span(
                                            "NO INTERVALO",
                                            className="classification-tooltip-term",
                                        ),
                                    ],
                                    className="classification-tooltip-term-row",
                                ),
                                html.Div(
                                    "Desempenho dentro do esperado para o porte populacional.",
                                    className="classification-tooltip-text",
                                ),
                            ],
                            className="classification-tooltip-section",
                        ),
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Span(
                                            className="classification-tooltip-dot is-low"
                                        ),
                                        html.Span(
                                            "ABAIXO",
                                            className="classification-tooltip-term",
                                        ),
                                    ],
                                    className="classification-tooltip-term-row",
                                ),
                                html.Div(
                                    "Desempenho abaixo do esperado para o porte populacional.",
                                    className="classification-tooltip-text",
                                ),
                            ],
                            className="classification-tooltip-section",
                        ),
                    ],
                    className="classification-tooltip-box",
                ),
            ],
            className="has-header-tooltip classification-header-cell",
        ),
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
                        html.Span(
                            _fmt_pos(
                                category_positions.get(category, {}).get(
                                    row["municipio"]
                                )
                            ),
                            className=_dimension_rank_class(
                                category_positions.get(category, {}).get(
                                    row["municipio"]
                                ),
                                region_total_for_color,
                            ),
                        ),
                        className="dimension-rank-cell",
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
        for row in records
    ]

    record_regions = sorted(
        {
            str(row.get("regiao_funcional")).strip()
            for row in records
            if row.get("regiao_funcional") is not None
            and not pd.isna(row.get("regiao_funcional"))
            and str(row.get("regiao_funcional")).strip()
        },
        key=_region_sort_value,
    )
    region_label = ", ".join(record_regions)

    if region and corede:
        subtitle = f"{len(records)} munic\u00edpios em {region} - {corede}"
    elif region:
        subtitle = f"{len(records)} munic\u00edpios em {region}"
    elif corede and region_label:
        subtitle = f"{len(records)} munic\u00edpios no Corede {corede} - {region_label}"
    elif corede:
        subtitle = f"{len(records)} munic\u00edpios no Corede {corede}"
    else:
        subtitle = f"{len(records)} munic\u00edpios"

    table_title = (
        "Munic\u00edpios da regi\u00e3o"
        if region or region_label
        else "Munic\u00edpios do recorte"
    )
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            _icon("list-ol", 18),
                            html.Span(table_title),
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


def _previous_general_position(
    ranking: pd.DataFrame | None,
    previous_year: int | None,
    region: str | None,
    municipio: str | None,
):
    if (
        ranking is None
        or ranking.empty
        or previous_year is None
        or not region
        or not municipio
    ):
        return None

    required_columns = {
        "ano",
        "regiao_funcional",
        "municipio",
        "ranking_regiao_funcional",
    }
    if not required_columns.issubset(ranking.columns):
        return None

    frame = ranking[
        (ranking["ano"] == int(previous_year))
        & (ranking["regiao_funcional"] == region)
        & (ranking["municipio"] == municipio)
    ]
    if frame.empty:
        return None
    return frame.iloc[0].get("ranking_regiao_funcional")


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
            previous_position = (
                f"{previous_year}: -"
                if previous_year is not None
                else "Ano anterior: -"
            )
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
                previous_position = (
                    f"{previous_year}: -"
                    if previous_year is not None
                    else "Ano anterior: -"
                )
            else:
                previous_rank = previous_match.iloc[0].get("ranking_dimensao")
                previous_position = f"{previous_year}: {_fmt_pos(previous_rank)}"

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


def _general_position_history(
    year,
    region: str | None,
    municipio: str | None,
    ranking: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, int]:
    frame = ranking if ranking is not None else _safe_ranking_data()
    if frame.empty or not region or not municipio:
        return pd.DataFrame(), 0

    required_columns = {
        "ano",
        "regiao_funcional",
        "municipio",
        "ranking_regiao_funcional",
    }
    if not required_columns.issubset(frame.columns):
        return pd.DataFrame(), 0

    history = frame[
        (frame["regiao_funcional"] == region) & (frame["municipio"] == municipio)
    ].copy()
    if history.empty:
        return pd.DataFrame(), 0

    max_value = (
        frame[frame["regiao_funcional"] == region]
        .groupby("ano")["municipio"]
        .nunique()
        .max()
    )
    max_rank = int(max_value) if pd.notna(max_value) else 0
    return history.sort_values("ano"), max_rank


def _general_position_history_figure(
    year,
    region: str | None,
    municipio: str | None,
    ranking: pd.DataFrame | None = None,
):
    history, max_rank = _general_position_history(year, region, municipio, ranking)
    if history.empty:
        return _empty_figure(
            "Selecione um munic\u00edpio para ver o hist\u00f3rico geral.", height=260
        )

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=history["ano"],
            y=history["ranking_regiao_funcional"],
            mode="lines+markers+text",
            text=[_fmt_pos(value) for value in history["ranking_regiao_funcional"]],
            textposition="top center",
            line=dict(color=MUNICIPIO_PRIMARY, width=3),
            marker=dict(size=7, color=MUNICIPIO_PRIMARY),
            cliponaxis=False,
            hovertemplate=(
                "<b>%{x}</b><br>Posi\u00e7\u00e3o geral: %{text}<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        **_top_line_chart_layout(),
        xaxis=_compact_line_xaxis(),
        yaxis=_compact_position_yaxis(
            max_rank, rank_values=history["ranking_regiao_funcional"]
        ),
        hoverlabel=dict(
            bgcolor="#ffffff",
            bordercolor="#dfe6ec",
            font=dict(color="#102542"),
        ),
        showlegend=False,
    )
    return figure


def _general_dimension_radar_figure(
    year,
    region: str | None,
    municipio: str | None,
    ranking: pd.DataFrame | None = None,
    current_positions: pd.DataFrame | None = None,
):
    if not region or not municipio or year is None:
        return _empty_figure("Selecione um munic\u00edpio.", height=260)

    ranking_frame = ranking if ranking is not None else _safe_ranking_data()
    region_year = pd.DataFrame()
    if (
        not ranking_frame.empty
        and "ano" in ranking_frame.columns
        and "regiao_funcional" in ranking_frame.columns
    ):
        region_year = ranking_frame[
            (ranking_frame["ano"] == int(year))
            & (ranking_frame["regiao_funcional"] == region)
        ].copy()

    values = []
    medians = []
    labels = []

    for category in CATEGORY_ORDER:
        note_column = f"nota_{category}"
        value = None
        median_value = None

        if not region_year.empty and note_column in region_year.columns:
            municipio_row = region_year[region_year["municipio"] == municipio]
            if not municipio_row.empty:
                value = municipio_row.iloc[0].get(note_column)
            median_value = pd.to_numeric(
                region_year[note_column], errors="coerce"
            ).median()

        if (value is None or pd.isna(value)) and current_positions is not None:
            if (
                not current_positions.empty
                and "category" in current_positions.columns
                and "nota_dimensao" in current_positions.columns
            ):
                category_rows = current_positions[
                    current_positions["category"] == category
                ]
                municipio_row = category_rows[category_rows["municipio"] == municipio]
                if not municipio_row.empty:
                    value = municipio_row.iloc[0].get("nota_dimensao")
                if median_value is None or pd.isna(median_value):
                    median_value = pd.to_numeric(
                        category_rows["nota_dimensao"], errors="coerce"
                    ).median()

        values.append(float(value) if value is not None and not pd.isna(value) else 0)
        medians.append(
            float(median_value)
            if median_value is not None and not pd.isna(median_value)
            else 0
        )
        labels.append(
            _radar_label(
                CATEGORY_LABELS.get(category, _fmt_text(category)),
                width=12,
                use_indicator_label=False,
            )
        )

    if not labels:
        return _empty_figure("Sem dados para o radar geral.", height=260)

    labels_closed = labels + [labels[0]]
    values_closed = values + [values[0]]
    medians_closed = medians + [medians[0]]

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
            r=medians_closed,
            theta=labels_closed,
            customdata=[_fmt_num(v) for v in medians_closed],
            mode="lines+markers",
            name=f"{REGIONAL_REFERENCE_LABEL} da {region}",
            line=dict(color=MUNICIPIO_AVERAGE, width=2, dash="dash"),
            marker=dict(size=6, color=MUNICIPIO_AVERAGE),
            hovertemplate="<b>%{fullData.name}</b><br>%{theta}: %{customdata}<extra></extra>",
        )
    )
    figure.update_layout(**_compact_radar_layout(GENERAL_CATEGORY, labels))
    return figure


def _category_position_lookup_for_year(
    year,
    region: str | None,
    municipio: str | None,
    fallback_positions: dict[int, pd.DataFrame],
) -> dict[str, object]:
    if year is None or not region or not municipio:
        return {}
    row_year = int(year)
    if row_year not in fallback_positions:
        fallback_positions[row_year] = _category_positions_for_year(row_year, region)
    positions = fallback_positions[row_year]
    if positions.empty or "category" not in positions.columns:
        return {}
    municipio_positions = positions[positions["municipio"] == municipio]
    if municipio_positions.empty:
        return {}
    value_column = (
        "ranking_dimensao"
        if "ranking_dimensao" in municipio_positions.columns
        else "position"
    )
    if value_column not in municipio_positions.columns:
        return {}
    return dict(zip(municipio_positions["category"], municipio_positions[value_column]))


def _general_dimension_history_table(
    year,
    region: str | None,
    municipio: str | None,
    ranking: pd.DataFrame | None = None,
):
    if not region or not municipio:
        return html.Div()

    ranking_frame = ranking if ranking is not None else _safe_ranking_data()
    if ranking_frame.empty:
        return _empty_state("Sem dados hist\u00f3ricos para o munic\u00edpio.")

    required_ranking_columns = {
        "ano",
        "regiao_funcional",
        "municipio",
        "ranking_regiao_funcional",
    }
    if not required_ranking_columns.issubset(ranking_frame.columns):
        return _empty_state("Sem dados hist\u00f3ricos para o munic\u00edpio.")

    ranking_history = ranking_frame[
        (ranking_frame["regiao_funcional"] == region)
        & (ranking_frame["municipio"] == municipio)
    ].copy()

    if ranking_history.empty:
        return _empty_state("Sem dados hist\u00f3ricos para o munic\u00edpio.")

    ranking_history["ano"] = pd.to_numeric(ranking_history["ano"], errors="coerce")
    ranking_history = (
        ranking_history.dropna(subset=["ano"])
        .sort_values("ano", ascending=False)
        .drop_duplicates("ano")
        .head(5)
    )

    if ranking_history.empty:
        return _empty_state("Sem dados hist\u00f3ricos para o munic\u00edpio.")

    summary = _safe_municipio_summary(None, region, None, municipio)
    summary_by_year = {}

    if not summary.empty and {"ano", "regiao_funcional", "municipio"}.issubset(
        summary.columns
    ):
        summary = summary[
            (summary["regiao_funcional"] == region)
            & (summary["municipio"] == municipio)
        ].copy()
        summary["ano"] = pd.to_numeric(summary["ano"], errors="coerce")
        summary = summary.dropna(subset=["ano"]).drop_duplicates("ano")
        summary_by_year = {
            int(summary_row["ano"]): summary_row
            for _, summary_row in summary.iterrows()
        }

    fallback_positions: dict[int, pd.DataFrame] = {}
    rows = []
    for _, row in ranking_history.iterrows():
        row_year = int(row["ano"])
        total_for_year = _region_total_for_rank_color(row_year, region, ranking_frame)
        fallback_lookup = {}

        general_position = row.get("ranking_regiao_funcional")

        cells = [
            html.Td(str(row_year), className="general-history-year-cell"),
            html.Td(
                html.Span(
                    _fmt_pos(general_position),
                    className=_dimension_rank_class(
                        general_position,
                        total_for_year,
                    ),
                ),
                className="dimension-rank-cell",
            ),
        ]

        for category in CATEGORY_ORDER:
            ranking_column = f"ranking_{category}"
            position = row.get(ranking_column) if ranking_column in row.index else None

            if position is None or pd.isna(position):
                summary_row = summary_by_year.get(row_year)
                if summary_row is not None and ranking_column in summary_row.index:
                    position = summary_row.get(ranking_column)

            if position is None or pd.isna(position):
                if not fallback_lookup:
                    fallback_lookup = _category_position_lookup_for_year(
                        row_year, region, municipio, fallback_positions
                    )
                position = fallback_lookup.get(category)

            cells.append(
                html.Td(
                    html.Span(
                        _fmt_pos(position),
                        className=_dimension_rank_class(position, total_for_year),
                    ),
                    className="dimension-rank-cell",
                )
            )
        rows.append(html.Tr(cells))

    header = html.Thead(
        html.Tr(
            [
                html.Th("Ano"),
                html.Th("Geral"),
                *[
                    html.Th(CATEGORY_LABELS.get(category, _fmt_text(category)))
                    for category in CATEGORY_ORDER
                ],
            ]
        )
    )

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            _icon("search", 18),
                            html.Span(
                                "Posi\u00e7\u00f5es por dimens\u00e3o ao longo do tempo"
                            ),
                        ],
                        className="chart-title",
                    )
                ],
                className="general-history-header",
            ),
            html.Div(
                html.Table(
                    [header, html.Tbody(rows)],
                    className="region-summary-table municipio-info-general-history-table",
                ),
                className="municipio-info-general-history-table-scroll",
            ),
        ],
        className="chart-card municipio-info-general-history-card",
    )


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
        **_top_line_chart_layout(),
        xaxis=_compact_line_xaxis(),
        yaxis=_compact_position_yaxis(
            max_rank, rank_values=history["ranking_dimensao"]
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
    regional_medians: pd.DataFrame | None = None,
):
    if not region or not municipio or year is None:
        return _empty_figure("Selecione um munic\u00edpio.", height=260)

    municipio_frame = (
        category_data if category_data is not None else _safe_category_data(category)
    )
    if municipio_frame.empty:
        return _empty_figure("Sem dados para a categoria.", height=260)

    current_frame = municipio_frame[
        (municipio_frame["ano"] == int(year))
        & (municipio_frame["regiao_funcional"] == region)
        & (municipio_frame["municipio"] == municipio)
    ].copy()

    fallback_regional_frame: pd.DataFrame | None = None

    def fallback_regional_data() -> pd.DataFrame:
        nonlocal fallback_regional_frame
        if fallback_regional_frame is None:
            fallback_regional_frame = _safe_category_data(category)
            if fallback_regional_frame.empty:
                fallback_regional_frame = municipio_frame
        return fallback_regional_frame

    if current_frame.empty:
        regional_frame = fallback_regional_data()
        current_frame = regional_frame[
            (regional_frame["ano"] == int(year))
            & (regional_frame["regiao_funcional"] == region)
            & (regional_frame["municipio"] == municipio)
        ].copy()

    if current_frame.empty:
        return _empty_figure("Sem dados para o recorte.", height=260)

    indicadores = current_frame["indicador"].dropna().unique()
    if len(indicadores) == 0:
        return _empty_figure("Sem indicadores na categoria.", height=260)

    values = []
    medianas = []
    labels = []

    for indicador in indicadores:
        municipio_row = current_frame[current_frame["indicador"] == indicador]

        if municipio_row.empty or pd.isna(municipio_row.iloc[0]["nota_indicador"]):
            values.append(0)
        else:
            values.append(float(municipio_row.iloc[0]["nota_indicador"]))

        median_value = _regional_median_value(
            regional_medians,
            category,
            region,
            year,
            indicador,
            "mediana_nota_indicador_regiao",
        )
        if median_value is not None and not pd.isna(median_value):
            medianas.append(float(median_value))
        else:
            regional_frame = fallback_regional_data()
            indicador_rows_region = regional_frame[
                (regional_frame["ano"] == int(year))
                & (regional_frame["regiao_funcional"] == region)
                & (regional_frame["indicador"] == indicador)
            ].copy()
            if (
                not indicador_rows_region.empty
                and "nota_indicador" in indicador_rows_region.columns
            ):
                median_value = indicador_rows_region["nota_indicador"].median()
                medianas.append(float(median_value) if not pd.isna(median_value) else 0)
            else:
                medianas.append(0)

        labels.append(_radar_label(indicador))

    labels_closed = labels + [labels[0]]
    values_closed = values + [values[0]]
    medianas_closed = medianas + [medianas[0]]

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
            r=medianas_closed,
            theta=labels_closed,
            customdata=[_fmt_num(v) for v in medianas_closed],
            mode="lines+markers",
            name=f"{REGIONAL_REFERENCE_LABEL} da {region}",
            line=dict(color=MUNICIPIO_AVERAGE, width=2, dash="dash"),
            marker=dict(size=6, color=MUNICIPIO_AVERAGE),
            hovertemplate="<b>%{fullData.name}</b><br>%{theta}: %{customdata}<extra></extra>",
        )
    )
    figure.update_layout(**_compact_radar_layout(category, labels))
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
    rows = current_rows.copy()
    rows["_indicator_label_sort"] = rows.apply(
        lambda row: _normalize_sort_text(
            _indicator_display_label(row["indicador"], row)
        ),
        axis=1,
    )
    rows = rows.sort_values(["_indicator_label_sort", "indicador"]).drop_duplicates(
        "indicador"
    )
    return [
        {
            "label": _indicator_option_label(
                _indicator_display_label(row["indicador"], row)
            ),
            "value": row["indicador"],
        }
        for _, row in rows.iterrows()
    ]


def _sort_indicators_alphabetically(
    indicators, rows: pd.DataFrame | None = None
) -> list:
    unique_indicators = []
    seen = set()
    for indicator in indicators:
        key = str(indicator)
        if key not in seen:
            seen.add(key)
            unique_indicators.append(indicator)

    def sort_key(indicator):
        row = None
        if rows is not None and not rows.empty and "indicador" in rows.columns:
            match = rows[rows["indicador"] == indicator]
            if not match.empty:
                row = match.iloc[0]
        return (
            _normalize_sort_text(_indicator_display_label(indicator, row)),
            str(indicator),
        )

    return sorted(unique_indicators, key=sort_key)


def _category_indicator_history_table(
    category: str,
    year,
    region: str | None,
    municipio: str | None,
    category_data: pd.DataFrame | None = None,
):
    if not category or category == GENERAL_CATEGORY or not region or not municipio:
        return html.Div()

    frame = (
        category_data if category_data is not None else _safe_category_data(category)
    )
    if frame.empty:
        return _empty_state(
            "Sem dados hist\u00f3ricos dos indicadores para a dimens\u00e3o."
        )

    required_columns = {"ano", "regiao_funcional", "municipio", "indicador"}
    if not required_columns.issubset(frame.columns):
        return _empty_state(
            "Sem dados hist\u00f3ricos dos indicadores para a dimens\u00e3o."
        )

    ranking_column = _indicator_rank_column(frame)
    if ranking_column not in frame.columns:
        return _empty_state(
            "Sem dados hist\u00f3ricos dos indicadores para a dimens\u00e3o."
        )

    municipio_history = frame[
        (frame["regiao_funcional"] == region) & (frame["municipio"] == municipio)
    ].copy()
    if municipio_history.empty:
        return _empty_state(
            "Sem dados hist\u00f3ricos dos indicadores para a dimens\u00e3o."
        )

    municipio_history["ano"] = pd.to_numeric(municipio_history["ano"], errors="coerce")
    municipio_history = municipio_history.dropna(subset=["ano"])
    if municipio_history.empty:
        return _empty_state(
            "Sem dados hist\u00f3ricos dos indicadores para a dimens\u00e3o."
        )

    years = (
        municipio_history["ano"]
        .dropna()
        .astype(int)
        .drop_duplicates()
        .sort_values(ascending=False)
        .tolist()
    )[:5]
    if not years:
        return _empty_state(
            "Sem dados hist\u00f3ricos dos indicadores para a dimens\u00e3o."
        )

    current_year_rows = (
        municipio_history[municipio_history["ano"] == int(year)].copy()
        if year is not None
        else pd.DataFrame()
    )
    indicator_order_frame = (
        current_year_rows if not current_year_rows.empty else municipio_history
    )
    raw_indicators = (
        indicator_order_frame["indicador"].dropna().drop_duplicates().tolist()
    )
    indicators = _sort_indicators_alphabetically(raw_indicators, indicator_order_frame)
    if not indicators:
        return _empty_state("Sem indicadores hist\u00f3ricos para a dimens\u00e3o.")

    rows = []
    for row_year in years:
        year_frame = municipio_history[municipio_history["ano"] == row_year].copy()
        total_for_year = None
        if "total_municipios_regiao" in year_frame.columns:
            total_value = pd.to_numeric(
                year_frame["total_municipios_regiao"], errors="coerce"
            ).dropna()
            if not total_value.empty:
                total_for_year = int(total_value.iloc[0])

        cells = [html.Td(str(row_year), className="general-history-year-cell")]
        for indicator in indicators:
            indicator_row = year_frame[year_frame["indicador"] == indicator]
            position = None
            if not indicator_row.empty:
                position = indicator_row.iloc[0].get(ranking_column)

            has_position = position is not None and not pd.isna(position)
            cells.append(
                html.Td(
                    html.Span(
                        _fmt_pos(position) if has_position else "-",
                        className=(
                            _dimension_rank_class(position, total_for_year)
                            if has_position
                            else "dimension-rank-pill is-neutral"
                        ),
                    ),
                    className="dimension-rank-cell",
                )
            )
        rows.append(html.Tr(cells))

    category_label = CATEGORY_LABELS.get(category, _fmt_text(category))
    header = html.Thead(
        html.Tr(
            [
                html.Th("Ano"),
                *[
                    html.Th(_indicator_display_label(indicator))
                    for indicator in indicators
                ],
            ]
        )
    )

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            _icon("bar-chart", 18),
                            html.Span(
                                "Posi\u00e7\u00e3o do munic\u00edpio nos indicadores da dimens\u00e3o ao longo do tempo"
                            ),
                        ],
                        className="chart-title",
                    ),
                    html.Div(
                        html.Span(
                            f"Evolu\u00e7\u00e3o da posi\u00e7\u00e3o do munic\u00edpio nos indicadores que comp\u00f5em a dimens\u00e3o {category_label}."
                        ),
                        className="general-history-note",
                    ),
                ],
                className="general-history-header",
            ),
            html.Div(
                html.Table(
                    [header, html.Tbody(rows)],
                    className="region-summary-table municipio-info-category-indicator-history-table",
                ),
                className="municipio-info-category-indicator-history-table-scroll",
            ),
        ],
        className="chart-card municipio-info-category-indicator-history-card",
    )


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
                "Valor do indicador: %{customdata[0]}<br>"
                "Nota: %{customdata[1]}<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        **_lower_line_chart_layout(),
        xaxis=_compact_line_xaxis(),
        yaxis=_compact_position_yaxis(max_rank, rank_values=history[ranking_column]),
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
    regional_medians: pd.DataFrame | None = None,
):
    _t_entry = time.perf_counter()
    history, _ = _indicator_history(
        category, region, municipio, indicator, category_data
    )
    if history.empty:
        return _empty_figure("Selecione um indicador.", height=260)

    _t_format = time.perf_counter()
    display_values = [
        _indicator_observed_display_value(value, indicator)
        for value in history["valor_original"]
    ]
    formatted_values = [
        _fmt_indicator_display_value(value, indicator)
        for value in history["valor_original"]
    ]
    is_percent = _is_percent_indicator(indicator)
    is_monetary = _is_monetary_indicator(indicator)
    y_axis_title = _indicator_axis_title(indicator)
    _perf_elapsed("indicator_value.load_and_format", _t_entry)
    regional_median_series = None
    median_source = "none"
    history_years = sorted(history["ano"].dropna().astype(int).tolist())

    _t_medians = time.perf_counter()
    mediana_por_ano = None

    filtered_medians = _filter_regional_medians(
        regional_medians, category, region, None, indicator
    )
    if (
        not filtered_medians.empty
        and "ano" in filtered_medians.columns
        and "mediana_valor_original_regiao" in filtered_medians.columns
    ):
        mediana_por_ano = (
            filtered_medians.assign(
                ano=pd.to_numeric(filtered_medians["ano"], errors="coerce"),
                mediana_valor_original_regiao=pd.to_numeric(
                    filtered_medians["mediana_valor_original_regiao"],
                    errors="coerce",
                ),
            )
            .dropna(subset=["ano", "mediana_valor_original_regiao"])
            .groupby("ano")["mediana_valor_original_regiao"]
            .first()
        )
        if not mediana_por_ano.empty:
            regional_median_series = (
                history["ano"].map(mediana_por_ano).reset_index(drop=True)
            )
            median_source = "regional_medians"
    regional_years = (
        sorted(mediana_por_ano.index.astype(int).tolist())
        if mediana_por_ano is not None and not mediana_por_ano.empty
        else []
    )
    nan_after_step1 = (
        int(pd.Series(regional_median_series).isna().sum())
        if regional_median_series is not None
        else len(history_years)
    )
    _perf_elapsed("indicator_value.use_regional_medians", _t_medians)

    needs_specific = (
        regional_median_series is None or pd.Series(regional_median_series).isna().any()
    )
    specific_por_ano = None
    specific_years = []
    nan_after_step2 = nan_after_step1
    if needs_specific:
        _t_specific = time.perf_counter()
        specific_medians = _safe_indicator_regional_medians(
            category, region, None, indicator
        )
        if (
            not specific_medians.empty
            and "ano" in specific_medians.columns
            and "mediana_valor_original_regiao" in specific_medians.columns
        ):
            specific_por_ano = (
                specific_medians.assign(
                    ano=pd.to_numeric(specific_medians["ano"], errors="coerce"),
                    mediana_valor_original_regiao=pd.to_numeric(
                        specific_medians["mediana_valor_original_regiao"],
                        errors="coerce",
                    ),
                )
                .dropna(subset=["ano", "mediana_valor_original_regiao"])
                .groupby("ano")["mediana_valor_original_regiao"]
                .first()
            )
            if not specific_por_ano.empty:
                specific_series = (
                    history["ano"].map(specific_por_ano).reset_index(drop=True)
                )
                if regional_median_series is None:
                    regional_median_series = specific_series
                    median_source = "specific_indicator_medians"
                else:
                    regional_median_series = regional_median_series.fillna(
                        specific_series
                    )
                    median_source = "regional_medians+specific_indicator_medians"
                specific_years = sorted(specific_por_ano.index.astype(int).tolist())
        nan_after_step2 = (
            int(pd.Series(regional_median_series).isna().sum())
            if regional_median_series is not None
            else len(history_years)
        )
        _perf_elapsed("indicator_value.specific_indicator_medians", _t_specific)

    needs_history_patch = (
        regional_median_series is not None
        and pd.Series(regional_median_series).isna().any()
        and "mediana_valor_original_regiao" in history.columns
        and history["mediana_valor_original_regiao"].notna().any()
    )
    if needs_history_patch:
        history_median_map = (
            history[["ano", "mediana_valor_original_regiao"]]
            .dropna(subset=["mediana_valor_original_regiao"])
            .set_index("ano")["mediana_valor_original_regiao"]
        )
        fill_values = history["ano"].map(history_median_map).reset_index(drop=True)
        regional_median_series = regional_median_series.fillna(fill_values)
        median_source += "+history_column"
    nan_after_step3 = (
        int(pd.Series(regional_median_series).isna().sum())
        if regional_median_series is not None
        else len(history_years)
    )

    has_any_median = (
        regional_median_series is not None
        and pd.Series(regional_median_series).notna().any()
    )
    needs_legacy_fallback = regional_median_series is None or not has_any_median
    _t_fallback = time.perf_counter()
    if needs_legacy_fallback:
        regional_frame = _safe_category_data(category)
        if (
            not regional_frame.empty
            and "valor_original" in regional_frame.columns
            and "ano" in regional_frame.columns
            and "regiao_funcional" in regional_frame.columns
            and "indicador" in regional_frame.columns
        ):
            region_indicator_frame = regional_frame[
                (regional_frame["regiao_funcional"] == region)
                & (regional_frame["indicador"] == indicator)
            ]
            if not region_indicator_frame.empty:
                mediana_por_ano = region_indicator_frame.groupby("ano")[
                    "valor_original"
                ].median()
                fallback_series = (
                    history["ano"].map(mediana_por_ano).reset_index(drop=True)
                )
                regional_median_series = (
                    fallback_series
                    if regional_median_series is None
                    else regional_median_series.fillna(fallback_series)
                )
                median_source += "+fallback_category_data_legacy"
        _perf_elapsed("indicator_value.fallback_category_data_legacy", _t_fallback)

    missing_after_all = []
    if regional_median_series is not None:
        missing_mask = pd.Series(regional_median_series).isna()
        if missing_mask.any():
            missing_after_all = sorted(
                y for y, is_missing in zip(history_years, missing_mask) if is_missing
            )

    logger.debug(
        "[PERF] indicator_value.median_coverage: history_years=%s regional_years=%s specific_years=%s missing_after_all=%s",
        history_years,
        regional_years,
        specific_years if needs_specific else [],
        missing_after_all,
    )
    logger.debug(
        "[PERF] indicator_value.nan_count: total_years=%d after_regional=%d after_specific=%d after_history_patch=%d after_all=%d",
        len(history_years),
        nan_after_step1,
        nan_after_step2,
        nan_after_step3,
        len(missing_after_all),
    )
    logger.debug("[PERF] indicator_value.median_source: %s", median_source)
    _perf_elapsed("indicator_value.resolve_medians", _t_medians)

    _t_build = time.perf_counter()
    has_regional_median = bool(
        regional_median_series is not None
        and pd.Series(regional_median_series).notna().any()
    )

    regional_median_values = []
    formatted_regional_median_values = []

    if has_regional_median:
        regional_median_values = [
            _indicator_observed_display_value(value, indicator)
            for value in regional_median_series
        ]
        formatted_regional_median_values = [
            _fmt_indicator_display_value(value, indicator)
            for value in regional_median_series
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
            showlegend=has_regional_median,
            hovertemplate=(
                "<b>%{x}</b><br>Valor do indicador: %{customdata}<extra></extra>"
            ),
        )
    )
    if has_regional_median:
        figure.add_trace(
            go.Scatter(
                x=history["ano"],
                y=regional_median_values,
                mode="lines+markers",
                name=f"{REGIONAL_REFERENCE_LABEL} da {region}",
                customdata=formatted_regional_median_values,
                line=dict(color=MUNICIPIO_AVERAGE, width=2, dash="dot"),
                marker=dict(size=6, color=MUNICIPIO_AVERAGE),
                connectgaps=True,
                showlegend=True,
                hovertemplate=(
                    f"<b>%{{x}}</b><br>{REGIONAL_REFERENCE_LABEL} regional: %{{customdata}}<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        height=210,
        margin=dict(l=44, r=24, t=46, b=28),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            tickmode="linear", showgrid=False, color="#102542", tickfont=dict(size=9)
        ),
        yaxis=dict(
            title=dict(text=y_axis_title, font=dict(size=9, color="#526277")),
            gridcolor="#e5ebef",
            zeroline=False,
            fixedrange=True,
            tickfont=dict(size=9),
            ticksuffix="%" if is_percent else "",
            tickprefix="R$ " if is_monetary else "",
            automargin=True,
        ),
        hoverlabel=dict(
            bgcolor="#ffffff",
            bordercolor="#dfe6ec",
            font=dict(color="#102542"),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.14,
            xanchor="right",
            x=1,
            font=dict(size=9, color="#526277"),
            bgcolor="rgba(255,255,255,0.92)",
            bordercolor="rgba(0,0,0,0)",
            borderwidth=0,
        ),
        showlegend=has_regional_median,
    )
    _perf_elapsed("indicator_value.figure_build", _t_build)
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
                [_icon("arrow-left", 16), html.Span("Voltar")],
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
                                        CATEGORY_SELECTOR_ICONS.get(key, "circle"),
                                        label,
                                    ),
                                    "value": key,
                                }
                                for key in CATEGORY_SELECTOR_ORDER
                                for label in [CATEGORY_SELECTOR_LABELS[key]]
                            ],
                            value=GENERAL_CATEGORY,
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
            id="municipio-info-category-indicator-history-section",
            className="municipio-info-category-indicator-history-section",
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
            id="municipio-info-general-history-section",
            className="municipio-info-general-history-section",
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
                            [
                                html.Div(
                                    "Evolu\u00e7\u00e3o do indicador",
                                    id="municipio-info-indicator-value-title",
                                    className="chart-title",
                                ),
                                html.Div(
                                    id="municipio-info-indicator-methodology-subtitle",
                                    className="indicator-methodology-subtitle is-hidden",
                                ),
                                html.Div(
                                    id="municipio-info-indicator-value-subtitle",
                                    className="indicator-direction-subtitle is-hidden",
                                ),
                            ],
                            className="indicator-value-title-block",
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
    Input("app-location", "pathname"),
    prevent_initial_call=True,
)
def apply_municipio_query_params(search, pathname):
    if pathname != "/municipios":
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    if not search:
        return dash.no_update, None, None, None

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
        regiao_value = regiao or None

    corede_value = dash.no_update
    if "corede" in params:
        corede = params.get("corede", [None])[0]
        corede_value = corede or None

    municipio_value = dash.no_update
    if "municipio" in params:
        municipio = params.get("municipio", [None])[0]
        municipio_value = municipio or None

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
    Output("app-location", "search", allow_duplicate=True),
    Input("clear-filters", "n_clicks"),
    State("app-location", "pathname"),
    prevent_initial_call=True,
)
def clear_municipio_query_params(n_clicks, pathname):
    if pathname != "/municipios" or not n_clicks:
        return dash.no_update
    return ""


@callback(
    Output("app-location", "search", allow_duplicate=True),
    Input("filter-corede", "value"),
    Input("filter-municipio", "value"),
    State("filter-ano", "value"),
    State("filter-regiao", "value"),
    State("app-location", "pathname"),
    State("app-location", "search"),
    prevent_initial_call=True,
)
def sync_direct_municipio_selection_url(
    corede, municipio, year, region, pathname, search
):
    if pathname != "/municipios" or year is None or (not corede and not municipio):
        return dash.no_update

    ranking = _safe_ranking_data()
    params = {
        "ano": year,
    }

    if municipio:
        selected_row, resolved_region = _selected_context(
            year, region, municipio, ranking
        )
        if selected_row is None or not resolved_region:
            return dash.no_update

        resolved_corede = corede
        if "corede" in selected_row and not pd.isna(selected_row.get("corede")):
            resolved_corede = str(selected_row.get("corede")).strip() or None

        params["regiao"] = resolved_region
        if resolved_corede:
            params["corede"] = resolved_corede
        params["municipio"] = str(selected_row["municipio"])
    else:
        if region:
            params["regiao"] = region
        params["corede"] = str(corede)

    next_search = f"?{urlencode(params)}"
    return dash.no_update if next_search == (search or "") else next_search


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
    _t0 = time.perf_counter()
    if category == GENERAL_CATEGORY:
        _perf_elapsed("update_indicator_options (early)", _t0)
        return [], None, [], None, {"display": "none"}

    category = category if category in CATEGORY_LABELS else CATEGORY_DEFAULT
    ranking = _safe_ranking_data() if year is not None and municipio else None
    selected_row, resolved_region = _selected_context(year, region, municipio, ranking)
    if selected_row is None:
        _perf_elapsed("update_indicator_options (no context)", _t0)
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
    _perf_elapsed("update_indicator_options", _t0)
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
    Output("municipio-info-category-indicator-history-section", "children"),
    Output("municipio-info-category-indicator-history-section", "style"),
    Output("municipio-info-indicator-selector", "style"),
    Output("municipio-info-lower-grid", "style"),
    Output("municipio-info-general-history-section", "children"),
    Output("municipio-info-general-history-section", "style"),
    Output("municipio-info-category-history-title", "children"),
    Output("municipio-info-category-radar-title", "children"),
    Output("municipio-info-indicator-history-title", "children"),
    Output("municipio-info-indicator-value-title", "children"),
    Output("municipio-info-indicator-methodology-subtitle", "children"),
    Output("municipio-info-indicator-methodology-subtitle", "className"),
    Output("municipio-info-indicator-value-subtitle", "children"),
    Output("municipio-info-indicator-value-subtitle", "className"),
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
    _t0 = time.perf_counter()
    _perf_labels.clear()
    _t1 = time.perf_counter()
    ranking_for_context = (
        _safe_ranking_data() if year is not None and municipio else None
    )
    selected_row, resolved_region = _selected_context(
        year, region, municipio, ranking_for_context
    )
    _t1a = time.perf_counter()
    if selected_row is None:
        empty_figure = _empty_figure(
            "Selecione um munic\u00edpio no filtro superior.", height=260
        )
        hero_style = {"display": "none"} if not region else {}
        context_text = (
            "Selecione um munic\u00edpio na tabela abaixo para abrir a an\u00e1lise completa."
            if region
            else "Selecione um ano e um munic\u00edpio para abrir a an\u00e1lise."
        )
        _t_region_table = time.perf_counter()
        _region_table = _region_municipalities_table(year, region, corede)
        _perf_elapsed("figure.region_municipalities_table", _t_region_table)
        _te = time.perf_counter()
        logger.debug(
            "[PERF] update_municipio_info (no selection): %.1f ms | sel_context=%.1f ms | region_table=%.1f ms",
            (_te - _t0) * 1000,
            (_t1a - _t1) * 1000,
            (_te - _t1a) * 1000,
        )
        return (
            html.Div(
                context_text,
                className="municipio-info-context-empty",
            ),
            "Informa\u00e7\u00f5es dos munic\u00edpios",
            "Acompanhe a posi\u00e7\u00e3o do munic\u00edpio dentro da sua regi\u00e3o funcional por categoria e por indicador.",
            hero_style,
            [],
            {"display": "none"},
            _region_table,
            {},
            {"display": "none"},
            {"display": "none"},
            {"display": "none"},
            html.Div(),
            {"display": "none"},
            {"display": "none"},
            {"display": "none"},
            html.Div(),
            {"display": "none"},
            "Hist\u00f3rico de posi\u00e7\u00e3o",
            "Notas da dimens\u00e3o",
            "Hist\u00f3rico de posi\u00e7\u00e3o no indicador",
            "Evolu\u00e7\u00e3o do indicador",
            "",
            "indicator-methodology-subtitle is-hidden",
            "",
            "indicator-direction-subtitle is-hidden",
            empty_figure,
            empty_figure,
            empty_figure,
            empty_figure,
        )

    municipio_name = str(selected_row["municipio"])
    category = category if category in CATEGORY_SELECTOR_LABELS else GENERAL_CATEGORY
    is_general_category = category == GENERAL_CATEGORY

    _t_data = time.perf_counter()
    ranking = (
        ranking_for_context if ranking_for_context is not None else _safe_ranking_data()
    )
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
    category_history_data = pd.DataFrame()
    indicator_data = pd.DataFrame()
    regional_medians = pd.DataFrame()
    if not is_general_category:
        category_history_data = _safe_municipio_category_history(
            category, resolved_region, municipio_name
        )
        indicator_data = _safe_municipio_indicator_data(
            category, resolved_region, municipio_name
        )
        regional_medians = _safe_indicator_regional_medians(
            category,
            resolved_region,
            year,
            None,
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
    selected_indicator_row = (
        selected_indicator_rows.iloc[0] if not selected_indicator_rows.empty else None
    )
    indicator_label = (
        _indicator_display_label(indicator, selected_indicator_row)
        if indicator and selected_indicator_row is not None
        else _indicator_label(indicator or "indicador")
    )
    indicator_direction = _indicator_direction(indicator, selected_indicator_row)
    indicator_direction_subtitle = _indicator_direction_text(
        indicator_direction, indicator, selected_indicator_row
    )
    indicator_direction_subtitle_class = f"indicator-direction-subtitle {_indicator_direction_class(indicator_direction)}"
    category_label = CATEGORY_SELECTOR_LABELS.get(category, _fmt_text(category))
    current_general_position = selected_row.get("ranking_regiao_funcional")
    previous_general_position = _previous_general_position(
        ranking, previous_year, resolved_region, municipio_name
    )
    previous_general_label = (
        f"{previous_year}: {_fmt_pos(previous_general_position)}"
        if previous_year is not None and previous_general_position is not None
        else "Ano anterior: -"
    )
    _t_context = time.perf_counter()

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
                            html.Strong(_fmt_pos(current_general_position)),
                            html.Span(
                                _icon("trophy", 22),
                                className="municipio-info-rank-trophy",
                            ),
                        ],
                        className="municipio-info-rank-main",
                    ),
                    html.Div(
                        [
                            html.Span(
                                previous_general_label,
                                className="municipio-info-rank-previous",
                            ),
                            _position_variation_chip(
                                current_general_position,
                                previous_general_position,
                            ),
                        ],
                        className="municipio-info-rank-meta",
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

    _t_context_done = time.perf_counter()
    if is_general_category:
        _t_figure = time.perf_counter()
        general_history_section = _general_dimension_history_table(
            year, resolved_region, municipio_name, ranking
        )
        _perf_elapsed("figure.general_dimension_history_table", _t_figure)
        category_history_title = (
            f"Hist\u00f3rico de posi\u00e7\u00e3o geral - {municipio_name}"
        )
        category_radar_title = "Radar das dimens\u00f5es - vis\u00e3o geral"
        category_indicator_history_section = html.Div()
        category_indicator_history_style = {"display": "none"}
        indicator_selector_style = {"display": "none"}
        lower_grid_style = {"display": "none"}
        general_section_style = {}
        _t_figure = time.perf_counter()
        category_history_figure = _general_position_history_figure(
            year, resolved_region, municipio_name, ranking
        )
        _perf_elapsed("figure.general_position_history_figure", _t_figure)
        _t_figure = time.perf_counter()
        category_radar_figure = _general_dimension_radar_figure(
            year, resolved_region, municipio_name, ranking, current_positions
        )
        _perf_elapsed("figure.general_dimension_radar_figure", _t_figure)
        indicator_history_title = "Hist\u00f3rico de posi\u00e7\u00e3o no indicador"
        indicator_value_title = "Evolu\u00e7\u00e3o do indicador"
        indicator_methodology_text = ""
        indicator_methodology_class = "indicator-methodology-subtitle is-hidden"
        indicator_value_subtitle = ""
        indicator_value_subtitle_class = "indicator-direction-subtitle is-hidden"
        indicator_history_figure = _empty_figure(
            "Selecione uma dimens\u00e3o.", height=260
        )
        indicator_value_figure = _empty_figure(
            "Selecione uma dimens\u00e3o.", height=260
        )
    else:
        general_history_section = html.Div()
        category_history_title = (
            f"Hist\u00f3rico de posi\u00e7\u00e3o - {category_label}"
        )
        category_radar_title = f"Notas da dimens\u00e3o - {category_label}"
        _t_figure = time.perf_counter()
        category_indicator_history_section = _category_indicator_history_table(
            category,
            year,
            resolved_region,
            municipio_name,
            indicator_data,
        )
        _perf_elapsed("figure.category_indicator_history_table", _t_figure)
        category_indicator_history_style = {}
        indicator_selector_style = {}
        lower_grid_style = {}
        general_section_style = {"display": "none"}
        _t_figure = time.perf_counter()
        category_history_figure = _category_history_figure(
            category, resolved_region, municipio_name, category_history_data
        )
        _perf_elapsed("figure.category_history_figure", _t_figure)
        _t_figure = time.perf_counter()
        category_radar_figure = _category_radar_figure(
            category,
            year,
            resolved_region,
            municipio_name,
            indicator_data,
            regional_medians,
        )
        _perf_elapsed("figure.category_radar_figure", _t_figure)
        indicator_history_title = (
            f"Hist\u00f3rico de posi\u00e7\u00e3o - {indicator_label}"
        )
        indicator_value_title = f"Evolu\u00e7\u00e3o do indicador - {indicator_label}"
        indicator_methodology_text = get_indicator_methodology(indicator)
        if indicator_methodology_text:
            indicator_methodology_class = "indicator-methodology-subtitle"
        else:
            indicator_methodology_text = ""
            indicator_methodology_class = "indicator-methodology-subtitle is-hidden"
        indicator_value_subtitle = indicator_direction_subtitle
        indicator_value_subtitle_class = indicator_direction_subtitle_class
        _t_figure = time.perf_counter()
        indicator_history_figure = _indicator_history_figure(
            category, resolved_region, municipio_name, indicator, indicator_data
        )
        _perf_elapsed("figure.indicator_history_figure", _t_figure)
        _t_figure = time.perf_counter()
        indicator_value_figure = _indicator_value_history_figure(
            category,
            resolved_region,
            municipio_name,
            indicator,
            indicator_data,
            regional_medians,
        )
        _perf_elapsed("figure.indicator_value_history_figure", _t_figure)

    _t_figures_done = time.perf_counter()
    cards = _category_cards(
        year,
        resolved_region,
        municipio_name,
        category,
        current_positions,
        previous_positions,
        previous_year,
    )
    _t_cards_done = time.perf_counter()

    _te = time.perf_counter()
    logger.debug(
        "[PERF] update_municipio_info: %.1f ms"
        " | sel_context=%.1f"
        " | data_load=%.1f"
        " | context=%.1f"
        " | figures=%.1f"
        " | cards=%.1f",
        (_te - _t0) * 1000,
        (_t1a - _t1) * 1000,
        (_t_context - _t_data) * 1000,
        (_t_context_done - _t_context) * 1000,
        (_t_figures_done - _t_context_done) * 1000,
        (_t_cards_done - _t_figures_done) * 1000,
    )
    return (
        context,
        title,
        subtitle,
        {},
        cards,
        {},
        html.Div(),
        {"display": "none"},
        {},
        {},
        {},
        category_indicator_history_section,
        category_indicator_history_style,
        indicator_selector_style,
        lower_grid_style,
        general_history_section,
        general_section_style,
        category_history_title,
        category_radar_title,
        indicator_history_title,
        indicator_value_title,
        indicator_methodology_text,
        indicator_methodology_class,
        indicator_value_subtitle,
        indicator_value_subtitle_class,
        category_history_figure,
        category_radar_figure,
        indicator_history_figure,
        indicator_value_figure,
    )


@callback(
    Output("filter-municipio", "value", allow_duplicate=True),
    Output("filter-corede", "value", allow_duplicate=True),
    Input({"type": "municipio-info-row", "municipio": ALL, "corede": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def select_municipio_from_region_table(_clicks):
    _t0 = time.perf_counter()
    if not _clicks or not any(clicks for clicks in _clicks if clicks):
        return dash.no_update, dash.no_update

    triggered = ctx.triggered_id
    if isinstance(triggered, dict):
        _perf_elapsed("select_municipio_from_region_table", _t0)
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
