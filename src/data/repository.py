import os
import re
import time
from functools import lru_cache
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

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
EXPECTED_TABLE_SCHEMA = "public"
EXPECTED_TABLE_NAME = "ranking_municipios"
RANKING_QUERY_FILE = QUERIES_DIR / "ranking_municipios.sql"
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


def _build_engine(
    db_user: str, db_password: str, db_host: str, db_port: str, db_name: str
) -> Engine:
    return create_engine(
        f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    )


def _has_expected_table(engine: Engine) -> bool:
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
                "table_name": EXPECTED_TABLE_NAME,
            },
        )
        return result.scalar() is not None


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


def _region_sort_key(value: str) -> tuple[int, str]:
    match = re.search(r"(\d+)", value or "")
    if match:
        return int(match.group(1)), value
    return 999, value or ""


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    numeric_columns = ["ano", "ranking_regiao_funcional", "nota_final", *SECTOR_LABELS]
    for column in numeric_columns:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    text_columns = ["municipio", "regiao_funcional", "corede"]
    for column in text_columns:
        if column in normalized.columns:
            normalized[column] = normalized[column].fillna("").astype(str)

    if "ano" in normalized.columns:
        normalized["ano"] = normalized["ano"].astype("Int64")
    if "ranking_regiao_funcional" in normalized.columns:
        normalized["ranking_regiao_funcional"] = normalized[
            "ranking_regiao_funcional"
        ].astype("Int64")

    return normalized


def _load_ranking_data_uncached() -> pd.DataFrame:
    if not RANKING_QUERY_FILE.exists():
        raise FileNotFoundError(f"Query nao encontrada: {RANKING_QUERY_FILE}")
    query = RANKING_QUERY_FILE.read_text(encoding="utf-8")
    frame = _read_sql(query)
    return _normalize_frame(frame)


@lru_cache(maxsize=4)
def _load_ranking_data_cached(cache_bucket: int) -> pd.DataFrame:
    return _load_ranking_data_uncached()


def load_ranking_data() -> pd.DataFrame:
    ttl_seconds = get_data_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return _load_ranking_data_uncached().copy()
    return _load_ranking_data_cached(_current_cache_bucket()).copy()


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


def clear_data_cache() -> None:
    get_local_postgres_engine.cache_clear()
    _load_ranking_data_cached.cache_clear()
