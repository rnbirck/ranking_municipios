import os
import re
import time
import unicodedata
from functools import lru_cache
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent.parent.parent
QUERIES_DIR = BASE_DIR / "queries"
SIBLING_ENV_CANDIDATES = (
    BASE_DIR.parent / "DASHBOARD-PNE" / ".env",
    BASE_DIR.parent / "CEI" / ".env",
)
ENV_FILES = (BASE_DIR / ".env", QUERIES_DIR / ".env", *SIBLING_ENV_CANDIDATES)
DEFAULT_CACHE_TTL_SECONDS = 900
DEFAULT_DB_HOST = "localhost"
DEFAULT_DB_PORT = "5432"
DEFAULT_DB_NAME = "cei"
SUPABASE_PAGE_SIZE = 1000
EXPECTED_TABLE_SCHEMA = "public"
EXPECTED_TABLE_NAME = "ranking_municipios"
RANKING_QUERY_FILE = QUERIES_DIR / "ranking_municipios.sql"
DEFAULT_INDICATOR_SUMMARY_FILE = (
    BASE_DIR.parent
    / "CEI"
    / "cei"
    / "ranking_municipios"
    / "resultados"
    / "resumo_indicadores_ranking_municipios_rs.xlsx"
)
CATEGORY_TABLES = {
    "educacao": "base_educacao",
    "financas": "base_financas",
    "meio_ambiente": "base_meio_ambiente",
    "saude": "base_saude",
    "seguranca": "base_seguranca",
    "socioeconomico": "base_socioeconomico",
}
DASH_MUNICIPIOS_RESUMO_TABLE = "dash_municipios_resumo"
DASH_MUNICIPIO_CATEGORIA_HISTORICO_TABLE = "dash_municipio_categoria_historico"
DASH_MUNICIPIO_INDICADORES_TABLE = "dash_municipio_indicadores"
MUNICIPIO_INDICADOR_MEDIANA_REGIAO_VIEW = "mv_municipio_indicador_mediana_regiao"
CATEGORY_LABELS = {
    "educacao": "Educa\u00e7\u00e3o",
    "financas": "Finan\u00e7as",
    "meio_ambiente": "Meio ambiente",
    "saude": "Sa\u00fade",
    "seguranca": "Seguran\u00e7a",
    "socioeconomico": "Socioecon\u00f4mico",
}
SECTOR_LABELS = {
    "nota_educacao": "Educação",
    "nota_financas": "Finanças",
    "nota_meio_ambiente": "Meio ambiente",
    "nota_saude": "Saúde",
    "nota_seguranca": "Segurança",
    "nota_socioeconomico": "Socioeconômico",
}


@lru_cache(maxsize=1)
def load_environment() -> None:
    for env_file in ENV_FILES:
        if env_file.exists():
            load_dotenv(env_file, override=False)


def require_env(name: str, default: str | None = None) -> str:
    load_environment()
    value = os.getenv(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Variavel de ambiente obrigatoria ausente: {name}")
    return value


def get_data_cache_ttl_seconds() -> int:
    load_environment()
    raw_value = os.getenv("DATA_CACHE_TTL_SECONDS", str(DEFAULT_CACHE_TTL_SECONDS))
    try:
        return max(int(raw_value), 0)
    except ValueError:
        return DEFAULT_CACHE_TTL_SECONDS


def _current_cache_bucket() -> int:
    ttl_seconds = get_data_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return -1
    return int(time.time() // ttl_seconds)


def _normalize_identifier(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    identifier = re.sub(r"[^a-z0-9]+", "_", ascii_value.strip().lower())
    return re.sub(r"_+", "_", identifier).strip("_")


def _resolve_indicator_summary_file() -> Path:
    load_environment()
    configured_path = (
        os.getenv("INDICATOR_SUMMARY_FILE")
        or os.getenv("RESUMO_INDICADORES_FILE")
    )
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return DEFAULT_INDICATOR_SUMMARY_FILE


@lru_cache(maxsize=8)
def _load_indicator_names_cached(cache_bucket: int) -> dict[str, str]:
    path = _resolve_indicator_summary_file()
    if not path.exists():
        return {}

    frame = pd.read_excel(path)
    frame.columns = [_normalize_identifier(str(column)) for column in frame.columns]
    if "indicador" not in frame.columns or "nome" not in frame.columns:
        return {}

    names = frame[["indicador", "nome"]].copy()
    names["indicador"] = names["indicador"].fillna("").astype(str).str.strip()
    names["nome"] = names["nome"].fillna("").astype(str).str.strip()
    names = names[(names["indicador"] != "") & (names["nome"] != "")]
    names = names.drop_duplicates("indicador")
    return dict(zip(names["indicador"], names["nome"]))


def load_indicator_names() -> dict[str, str]:
    return _load_indicator_names_cached(_current_cache_bucket()).copy()


def _build_engine(
    db_user: str, db_password: str, db_host: str, db_port: str, db_name: str
) -> Engine:
    return create_engine(
        URL.create(
            "postgresql+psycopg2",
            username=db_user,
            password=db_password,
            host=db_host,
            port=int(db_port),
            database=db_name,
        )
    )


def _has_table(engine: Engine, table_name: str) -> bool:
    query = text(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = :schema_name
          AND table_name = :table_name
        LIMIT 1
        """
    )
    with engine.connect() as connection:
        result = connection.execute(
            query,
            {
                "schema_name": EXPECTED_TABLE_SCHEMA,
                "table_name": table_name,
            },
        )
        return result.scalar() is not None


def _has_expected_table(engine: Engine) -> bool:
    return _has_table(engine, EXPECTED_TABLE_NAME)


def _resolve_engine() -> Engine:
    load_environment()
    database_url = (
        os.getenv("DATABASE_URL")
        or os.getenv("SUPABASE_DB_URL")
        or os.getenv("SUPABASE_DATABASE_URL")
    )
    if database_url:
        direct_engine = create_engine(database_url)
        if _has_expected_table(direct_engine):
            return direct_engine

    db_user = require_env("DB_USUARIO")
    db_password = require_env("DB_SENHA")
    db_host = require_env("DB_HOST", DEFAULT_DB_HOST)
    db_name = require_env("DB_BANCO", DEFAULT_DB_NAME)
    db_port = require_env("DB_PORT", DEFAULT_DB_PORT)

    primary_engine = _build_engine(db_user, db_password, db_host, db_port, db_name)
    if _has_expected_table(primary_engine):
        return primary_engine

    if db_name != DEFAULT_DB_NAME:
        fallback_engine = _build_engine(
            db_user, db_password, db_host, db_port, DEFAULT_DB_NAME
        )
        if _has_expected_table(fallback_engine):
            print(
                "Banco configurado nao contem public.ranking_municipios; "
                f"usando fallback para {DEFAULT_DB_NAME}."
            )
            return fallback_engine

    raise RuntimeError(
        "Tabela public.ranking_municipios nao encontrada na conexao configurada. "
        f"Banco atual: {db_name}."
    )


@lru_cache(maxsize=1)
def get_local_postgres_engine() -> Engine:
    return _resolve_engine()


def _read_sql(query: str, params: dict | None = None) -> pd.DataFrame:
    return pd.read_sql_query(text(query), get_local_postgres_engine(), params=params)


def _read_table(table_name: str) -> pd.DataFrame:
    try:
        engine = get_local_postgres_engine()
        if _has_table(engine, table_name):
            return pd.read_sql_query(text(f"SELECT * FROM public.{table_name}"), engine)
    except Exception as exc:
        if not _has_supabase_api_config():
            raise
        print(
            f"Banco direto indisponivel para public.{table_name}; "
            f"usando API do Supabase. Detalhe: {exc}"
        )

    if _has_supabase_api_config():
        return _load_table_from_supabase_api(table_name)
    raise RuntimeError(
        f"Tabela public.{table_name} nao encontrada no banco configurado."
    )


def _read_table_with_filters(
    table_name: str,
    columns: str = "*",
    filters: dict | None = None,
) -> pd.DataFrame:
    filters = {key: value for key, value in (filters or {}).items() if value is not None}
    try:
        engine = get_local_postgres_engine()
        if _has_table(engine, table_name):
            where = ""
            params = {}
            if filters:
                clauses = []
                for index, (column, value) in enumerate(filters.items()):
                    param = f"value_{index}"
                    clauses.append(f"{column} = :{param}")
                    params[param] = value
                where = " WHERE " + " AND ".join(clauses)
            return pd.read_sql_query(
                text(f"SELECT {columns} FROM public.{table_name}{where}"),
                engine,
                params=params,
            )
    except Exception as exc:
        if not _has_supabase_api_config():
            raise
        print(
            f"Banco direto indisponivel para public.{table_name}; "
            f"usando API do Supabase. Detalhe: {exc}"
        )

    if _has_supabase_api_config():
        return _load_table_from_supabase_api(table_name, columns=columns, filters=filters)
    raise RuntimeError(
        f"Tabela public.{table_name} nao encontrada no banco configurado."
    )


def _load_table_from_supabase_api(
    table_name: str,
    columns: str = "*",
    filters: dict | None = None,
) -> pd.DataFrame:
    load_environment()
    supabase_url = require_env("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY") or require_env("SUPABASE_SERVICE_KEY")
    client = create_client(supabase_url, supabase_key)

    rows = []
    start = 0
    while True:
        end = start + SUPABASE_PAGE_SIZE - 1
        query = client.table(table_name).select(columns)
        for column, value in (filters or {}).items():
            query = query.eq(column, value)
        response = query.range(start, end).execute()
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < SUPABASE_PAGE_SIZE:
            break
        start += SUPABASE_PAGE_SIZE

    return pd.DataFrame(rows)


def _load_ranking_data_from_supabase_api() -> pd.DataFrame:
    frame = _load_table_from_supabase_api(EXPECTED_TABLE_NAME)
    if frame.empty:
        return frame
    frame = _merge_regression_classification(frame)
    return frame.sort_values(
        ["ano", "regiao_funcional", "ranking_regiao_funcional", "municipio"],
        ascending=[False, True, True, True],
    )


def _merge_regression_classification(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "classificacao" in frame.columns:
        return frame

    try:
        predictions = _read_table_with_filters(
            "regressao_rf_previsoes",
            columns="id_municipio,municipio,ano,regiao_funcional,classificacao",
        )
    except Exception as exc:
        print(f"Classificacao populacional indisponivel: {exc}")
        return frame

    if predictions.empty or "classificacao" not in predictions.columns:
        return frame

    key_candidates = [
        ["id_municipio", "ano", "regiao_funcional"],
        ["municipio", "ano", "regiao_funcional"],
    ]
    for keys in key_candidates:
        if all(column in frame.columns and column in predictions.columns for column in keys):
            lookup = (
                predictions[keys + ["classificacao"]]
                .dropna(subset=["classificacao"])
                .drop_duplicates(keys)
            )
            if lookup.empty:
                return frame
            return frame.merge(lookup, on=keys, how="left")

    return frame


def _region_sort_key(value: str) -> tuple[int, str]:
    match = re.search(r"(\d+)", value or "")
    if match:
        return int(match.group(1)), value
    return 999, value or ""


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    numeric_columns = [
        "id_municipio",
        "ano",
        "ranking_regiao_funcional",
        "nota_final",
        *SECTOR_LABELS,
    ]
    for column in numeric_columns:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    text_columns = ["municipio", "regiao_funcional", "corede", "classificacao"]
    for column in text_columns:
        if column in normalized.columns:
            normalized[column] = normalized[column].fillna("").astype(str)

    if "ano" in normalized.columns:
        normalized["ano"] = normalized["ano"].astype("Int64")
    if "id_municipio" in normalized.columns:
        normalized["id_municipio"] = normalized["id_municipio"].astype("Int64")
    if "ranking_regiao_funcional" in normalized.columns:
        normalized["ranking_regiao_funcional"] = normalized[
            "ranking_regiao_funcional"
        ].astype("Int64")

    return normalized


def _normalize_category_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    numeric_columns = [
        "id_municipio",
        "ano",
        "nota_indicador",
        "ranking_indicador",
        "ranking_indicador_desempatado",
        "nota_dimensao",
        "ranking_dimensao",
        "valor_original",
        "valor_usado_nota",
        "media_nota_indicador_regiao",
        "media_valor_original_regiao",
        "mediana_nota_indicador_regiao",
        "mediana_valor_original_regiao",
        "total_municipios_mediana",
        "total_municipios_regiao",
    ]
    for column in numeric_columns:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    text_columns = [
        "municipio",
        "regiao_funcional",
        "corede",
        "indicador",
        "indicador_nome",
        "categoria",
        "dimensao",
        "valor_imputado",
    ]
    for column in text_columns:
        if column in normalized.columns:
            normalized[column] = normalized[column].fillna("").astype(str)

    for column in (
        "id_municipio",
        "ano",
        "ranking_indicador",
        "ranking_indicador_desempatado",
        "ranking_dimensao",
    ):
        if column in normalized.columns:
            normalized[column] = normalized[column].astype("Int64")

    return normalized


def _normalize_indicator_regional_medians_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = _normalize_category_frame(frame)
    expected_columns = [
        "ano",
        "regiao_funcional",
        "categoria",
        "indicador",
        "mediana_nota_indicador_regiao",
        "mediana_valor_original_regiao",
        "total_municipios_mediana",
    ]
    for column in expected_columns:
        if column not in normalized.columns:
            normalized[column] = pd.NA
    if "dimensao" not in normalized.columns and "categoria" in normalized.columns:
        normalized["dimensao"] = normalized["categoria"]
    return normalized.sort_values(
        ["ano", "regiao_funcional", "categoria", "indicador"]
    )


def _normalize_municipio_summary_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = _normalize_frame(frame)
    numeric_columns = [
        "id_municipio",
        "total_municipios_regiao",
        "ranking_educacao",
        "ranking_anterior_educacao",
        "ano_anterior_educacao",
        "ranking_financas",
        "ranking_anterior_financas",
        "ano_anterior_financas",
        "ranking_meio_ambiente",
        "ranking_anterior_meio_ambiente",
        "ano_anterior_meio_ambiente",
        "ranking_saude",
        "ranking_anterior_saude",
        "ano_anterior_saude",
        "ranking_seguranca",
        "ranking_anterior_seguranca",
        "ano_anterior_seguranca",
        "ranking_socioeconomico",
        "ranking_anterior_socioeconomico",
        "ano_anterior_socioeconomico",
    ]
    for column in numeric_columns:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    integer_columns = [
        "id_municipio",
        "ano",
        "ranking_regiao_funcional",
        "total_municipios_regiao",
        *[f"ranking_{category}" for category in CATEGORY_TABLES],
        *[f"ranking_anterior_{category}" for category in CATEGORY_TABLES],
        *[f"ano_anterior_{category}" for category in CATEGORY_TABLES],
    ]
    for column in integer_columns:
        if column in normalized.columns:
            normalized[column] = normalized[column].astype("Int64")
    return normalized


def _has_direct_database_config() -> bool:
    load_environment()
    return bool(
        os.getenv("DATABASE_URL")
        or os.getenv("SUPABASE_DB_URL")
        or os.getenv("SUPABASE_DATABASE_URL")
        or os.getenv("DB_USUARIO")
    )


def _has_supabase_api_config() -> bool:
    load_environment()
    return bool(
        os.getenv("SUPABASE_URL")
        and (os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))
    )


def _load_ranking_data_uncached() -> pd.DataFrame:
    if not RANKING_QUERY_FILE.exists():
        raise FileNotFoundError(f"Query nao encontrada: {RANKING_QUERY_FILE}")
    load_environment()
    if not _has_direct_database_config() and _has_supabase_api_config():
        frame = _load_ranking_data_from_supabase_api()
        return _normalize_frame(frame)

    query = RANKING_QUERY_FILE.read_text(encoding="utf-8")
    try:
        frame = _read_sql(query)
    except Exception as exc:
        if not _has_supabase_api_config():
            raise
        print(
            "Banco direto indisponivel para public.ranking_municipios; "
            f"usando API do Supabase. Detalhe: {exc}"
        )
        frame = _load_ranking_data_from_supabase_api()
    frame = _merge_regression_classification(frame)
    return _normalize_frame(frame)


@lru_cache(maxsize=4)
def _load_ranking_data_cached(cache_bucket: int) -> pd.DataFrame:
    return _load_ranking_data_uncached()


def load_ranking_data() -> pd.DataFrame:
    ttl_seconds = get_data_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return _load_ranking_data_uncached().copy()
    return _load_ranking_data_cached(_current_cache_bucket()).copy()


def _load_municipio_summary_uncached(
    ano: int | None = None,
    regiao_funcional: str | None = None,
    corede: str | None = None,
    municipio: str | None = None,
) -> pd.DataFrame:
    filters = {
        "ano": int(ano) if ano is not None else None,
        "regiao_funcional": regiao_funcional,
        "corede": corede,
        "municipio": municipio,
    }
    frame = _read_table_with_filters(DASH_MUNICIPIOS_RESUMO_TABLE, filters=filters)
    if frame.empty:
        return frame
    return _normalize_municipio_summary_frame(frame).sort_values(
        ["ano", "regiao_funcional", "ranking_regiao_funcional", "municipio"],
        ascending=[False, True, True, True],
    )


@lru_cache(maxsize=256)
def _load_municipio_summary_cached(
    ano: int | None,
    regiao_funcional: str | None,
    corede: str | None,
    municipio: str | None,
    cache_bucket: int,
) -> pd.DataFrame:
    return _load_municipio_summary_uncached(
        ano, regiao_funcional, corede, municipio
    )


def load_municipio_summary_data(
    ano: int | None = None,
    regiao_funcional: str | None = None,
    corede: str | None = None,
    municipio: str | None = None,
) -> pd.DataFrame:
    ttl_seconds = get_data_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return _load_municipio_summary_uncached(
            ano, regiao_funcional, corede, municipio
        ).copy()
    return _load_municipio_summary_cached(
        int(ano) if ano is not None else None,
        regiao_funcional,
        corede,
        municipio,
        _current_cache_bucket(),
    ).copy()


def filter_ranking_data(
    *,
    ano: int | None = None,
    regiao_funcional: str | None = None,
    municipio: str | None = None,
) -> pd.DataFrame:
    frame = load_ranking_data()

    if ano is not None and "ano" in frame.columns:
        frame = frame[frame["ano"] == int(ano)]
    if regiao_funcional:
        frame = frame[frame["regiao_funcional"] == regiao_funcional]
    if municipio:
        frame = frame[frame["municipio"] == municipio]

    return frame.copy()


def _load_category_data_uncached(category: str | None = None) -> pd.DataFrame:
    if category is not None and category not in CATEGORY_TABLES:
        raise ValueError(f"Categoria desconhecida: {category}")

    try:
        filters = {"categoria": category} if category else None
        frame = _read_table_with_filters(
            DASH_MUNICIPIO_INDICADORES_TABLE, filters=filters
        )
        if not frame.empty:
            normalized = _normalize_category_frame(frame)
            if "dimensao" not in normalized.columns and "categoria" in normalized.columns:
                normalized["dimensao"] = normalized["categoria"]
            return normalized
    except Exception as exc:
        print(
            "Tabela derivada dash_municipio_indicadores indisponivel; "
            f"usando bases originais. Detalhe: {exc}"
        )

    selected_categories = [category] if category else list(CATEGORY_TABLES)
    frames = []

    for selected_category in selected_categories:
        table_name = CATEGORY_TABLES[selected_category]
        if not _has_direct_database_config() and _has_supabase_api_config():
            frame = _load_table_from_supabase_api(table_name)
        else:
            frame = _read_table(table_name)

        if frame.empty:
            continue
        if "dimensao" not in frame.columns:
            frame["dimensao"] = selected_category
        frames.append(_normalize_category_frame(frame))

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


@lru_cache(maxsize=16)
def _load_category_data_cached(category: str | None, cache_bucket: int) -> pd.DataFrame:
    return _load_category_data_uncached(category)


def load_category_data(category: str | None = None) -> pd.DataFrame:
    normalized_category = category if category in CATEGORY_TABLES else None
    ttl_seconds = get_data_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return _load_category_data_uncached(normalized_category).copy()
    return _load_category_data_cached(
        normalized_category, _current_cache_bucket()
    ).copy()


def _load_category_positions_uncached(
    ano: int,
    regiao_funcional: str,
    corede: str | None = None,
) -> pd.DataFrame:
    try:
        filters = {
            "ano": int(ano),
            "regiao_funcional": regiao_funcional,
        }
        if corede:
            filters["corede"] = corede
        frame = _read_table_with_filters(
            DASH_MUNICIPIO_CATEGORIA_HISTORICO_TABLE,
            columns="municipio,categoria,ranking_dimensao",
            filters=filters,
        )
        if not frame.empty:
            positions = frame.rename(columns={"categoria": "category"})
            positions = positions[["category", "municipio", "ranking_dimensao"]].copy()
            positions["municipio"] = positions["municipio"].fillna("").astype(str)
            positions["category"] = positions["category"].fillna("").astype(str)
            positions["ranking_dimensao"] = pd.to_numeric(
                positions["ranking_dimensao"], errors="coerce"
            ).astype("Int64")
            return positions.drop_duplicates(["category", "municipio"])
    except Exception as exc:
        print(
            "Tabela derivada dash_municipio_categoria_historico indisponivel; "
            f"usando bases originais. Detalhe: {exc}"
        )

    frames = []
    for category, table_name in CATEGORY_TABLES.items():
        use_supabase_api = (
            not _has_direct_database_config() and _has_supabase_api_config()
        )
        engine = None
        if not use_supabase_api:
            try:
                engine = get_local_postgres_engine()
                if not _has_table(engine, table_name):
                    if not _has_supabase_api_config():
                        raise RuntimeError(
                            f"Tabela public.{table_name} nao encontrada no banco configurado."
                        )
                    use_supabase_api = True
            except Exception as exc:
                if not _has_supabase_api_config():
                    raise
                print(
                    f"Banco direto indisponivel para public.{table_name}; "
                    f"usando API do Supabase. Detalhe: {exc}"
                )
                use_supabase_api = True

        if use_supabase_api:
            filters = {
                "ano": int(ano),
                "regiao_funcional": regiao_funcional,
            }
            if corede:
                filters["corede"] = corede
            frame = _load_table_from_supabase_api(
                table_name,
                columns="municipio,ranking_dimensao",
                filters=filters,
            )
        else:
            where_corede = "AND corede = :corede" if corede else ""
            query = f"""
                SELECT
                    municipio,
                    MIN(ranking_dimensao) AS ranking_dimensao
                FROM public.{table_name}
                WHERE ano = :ano
                  AND regiao_funcional = :regiao_funcional
                  {where_corede}
                GROUP BY municipio
            """
            params = {
                "ano": int(ano),
                "regiao_funcional": regiao_funcional,
            }
            if corede:
                params["corede"] = corede
            frame = pd.read_sql_query(text(query), engine, params=params)

        if frame.empty:
            continue
        frame = frame[["municipio", "ranking_dimensao"]].copy()
        frame["category"] = category
        frames.append(frame.drop_duplicates(["category", "municipio"]))

    if not frames:
        return pd.DataFrame(columns=["category", "municipio", "ranking_dimensao"])

    positions = pd.concat(frames, ignore_index=True)
    positions["municipio"] = positions["municipio"].fillna("").astype(str)
    positions["category"] = positions["category"].fillna("").astype(str)
    positions["ranking_dimensao"] = pd.to_numeric(
        positions["ranking_dimensao"], errors="coerce"
    ).astype("Int64")
    return positions


@lru_cache(maxsize=128)
def _load_category_positions_cached(
    ano: int,
    regiao_funcional: str,
    corede: str | None,
    cache_bucket: int,
) -> pd.DataFrame:
    return _load_category_positions_uncached(ano, regiao_funcional, corede)


def load_category_positions(
    ano: int | None,
    regiao_funcional: str | None,
    corede: str | None = None,
) -> pd.DataFrame:
    if ano is None or not regiao_funcional:
        return pd.DataFrame(columns=["category", "municipio", "ranking_dimensao"])

    ttl_seconds = get_data_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return _load_category_positions_uncached(
            int(ano), regiao_funcional, corede
        ).copy()
    return _load_category_positions_cached(
        int(ano), regiao_funcional, corede, _current_cache_bucket()
    ).copy()


def _load_municipio_category_history_uncached(
    category: str,
    regiao_funcional: str,
    municipio: str,
) -> pd.DataFrame:
    frame = _read_table_with_filters(
        DASH_MUNICIPIO_CATEGORIA_HISTORICO_TABLE,
        filters={
            "categoria": category,
            "regiao_funcional": regiao_funcional,
            "municipio": municipio,
        },
    )
    if frame.empty:
        return frame
    normalized = _normalize_category_frame(frame)
    if "dimensao" not in normalized.columns and "categoria" in normalized.columns:
        normalized["dimensao"] = normalized["categoria"]
    return normalized.sort_values("ano")


@lru_cache(maxsize=512)
def _load_municipio_category_history_cached(
    category: str,
    regiao_funcional: str,
    municipio: str,
    cache_bucket: int,
) -> pd.DataFrame:
    return _load_municipio_category_history_uncached(
        category, regiao_funcional, municipio
    )


def load_municipio_category_history_data(
    category: str,
    regiao_funcional: str | None,
    municipio: str | None,
) -> pd.DataFrame:
    if category not in CATEGORY_TABLES or not regiao_funcional or not municipio:
        return pd.DataFrame()
    ttl_seconds = get_data_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return _load_municipio_category_history_uncached(
            category, regiao_funcional, municipio
        ).copy()
    return _load_municipio_category_history_cached(
        category, regiao_funcional, municipio, _current_cache_bucket()
    ).copy()


def _load_municipio_indicator_data_uncached(
    category: str,
    regiao_funcional: str,
    municipio: str,
    indicador: str | None = None,
) -> pd.DataFrame:
    filters = {
        "categoria": category,
        "regiao_funcional": regiao_funcional,
        "municipio": municipio,
    }
    if indicador:
        filters["indicador"] = indicador
    frame = _read_table_with_filters(
        DASH_MUNICIPIO_INDICADORES_TABLE,
        filters=filters,
    )
    if frame.empty:
        return frame
    normalized = _normalize_category_frame(frame)
    if "dimensao" not in normalized.columns and "categoria" in normalized.columns:
        normalized["dimensao"] = normalized["categoria"]
    ranking_column = (
        "ranking_indicador_desempatado"
        if "ranking_indicador_desempatado" in normalized.columns
        else "ranking_indicador"
    )
    return normalized.sort_values(["ano", ranking_column, "indicador"])


@lru_cache(maxsize=512)
def _load_municipio_indicator_data_cached(
    category: str,
    regiao_funcional: str,
    municipio: str,
    indicador: str | None,
    cache_bucket: int,
) -> pd.DataFrame:
    return _load_municipio_indicator_data_uncached(
        category, regiao_funcional, municipio, indicador
    )


def load_municipio_indicator_data(
    category: str,
    regiao_funcional: str | None,
    municipio: str | None,
    indicador: str | None = None,
) -> pd.DataFrame:
    if category not in CATEGORY_TABLES or not regiao_funcional or not municipio:
        return pd.DataFrame()
    ttl_seconds = get_data_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return _load_municipio_indicator_data_uncached(
            category, regiao_funcional, municipio, indicador
        ).copy()
    return _load_municipio_indicator_data_cached(
        category,
        regiao_funcional,
        municipio,
        indicador,
        _current_cache_bucket(),
    ).copy()


def _load_indicator_regional_medians_uncached(
    category: str,
    region: str | None = None,
    year: int | None = None,
    indicator: str | None = None,
) -> pd.DataFrame:
    filters = {
        "categoria": category,
        "regiao_funcional": region,
        "ano": int(year) if year is not None else None,
        "indicador": indicator,
    }
    frame = _read_table_with_filters(
        MUNICIPIO_INDICADOR_MEDIANA_REGIAO_VIEW,
        filters=filters,
    )
    if frame.empty:
        return frame
    return _normalize_indicator_regional_medians_frame(frame)


@lru_cache(maxsize=512)
def _load_indicator_regional_medians_cached(
    category: str,
    region: str | None,
    year: int | None,
    indicator: str | None,
    cache_bucket: int,
) -> pd.DataFrame:
    return _load_indicator_regional_medians_uncached(
        category, region, year, indicator
    )


def load_indicator_regional_medians(
    category: str,
    region: str | None = None,
    year: int | None = None,
    indicator: str | None = None,
) -> pd.DataFrame:
    if category not in CATEGORY_TABLES:
        return pd.DataFrame()
    ttl_seconds = get_data_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return _load_indicator_regional_medians_uncached(
            category, region, year, indicator
        ).copy()
    return _load_indicator_regional_medians_cached(
        category,
        region,
        int(year) if year is not None else None,
        indicator,
        _current_cache_bucket(),
    ).copy()


def load_anos() -> list[int]:
    frame = load_ranking_data()
    if frame.empty or "ano" not in frame.columns:
        return []
    anos = frame["ano"].dropna().astype(int).drop_duplicates().tolist()
    return sorted(anos, reverse=True)


def get_default_year() -> int | None:
    anos = load_anos()
    return anos[0] if anos else None


def load_regioes(ano: int | None = None) -> list[str]:
    frame = filter_ranking_data(ano=ano)
    if frame.empty or "regiao_funcional" not in frame.columns:
        return []
    regioes = frame["regiao_funcional"].dropna().astype(str).drop_duplicates().tolist()
    return sorted(regioes, key=_region_sort_key)


def load_municipios(
    ano: int | None = None, regiao_funcional: str | None = None
) -> list[str]:
    frame = filter_ranking_data(ano=ano, regiao_funcional=regiao_funcional)
    if frame.empty or "municipio" not in frame.columns:
        return []
    municipios = frame["municipio"].dropna().astype(str).drop_duplicates().tolist()
    return sorted(municipios)


def get_sector_labels() -> dict[str, str]:
    return SECTOR_LABELS.copy()


def get_category_labels() -> dict[str, str]:
    return CATEGORY_LABELS.copy()


def clear_data_cache() -> None:
    get_local_postgres_engine.cache_clear()
    _load_ranking_data_cached.cache_clear()
    _load_municipio_summary_cached.cache_clear()
    _load_category_data_cached.cache_clear()
    _load_category_positions_cached.cache_clear()
    _load_municipio_category_history_cached.cache_clear()
    _load_municipio_indicator_data_cached.cache_clear()
    _load_indicator_regional_medians_cached.cache_clear()
