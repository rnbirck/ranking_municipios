# %%
from __future__ import annotations

import math
import os
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from supabase import Client, create_client


BASE_DIR = Path(__file__).resolve().parent
QUERIES_DIR = BASE_DIR / "queries"
QUERY_FILE = QUERIES_DIR / "ranking_municipios.sql"
LOG_FILE = BASE_DIR / "log_erros.txt"

SIBLING_ENV_CANDIDATES = (
    BASE_DIR.parent / "DASHBOARD-PNE" / ".env",
    BASE_DIR.parent / "CEI" / ".env",
)
ENV_FILES = (BASE_DIR / ".env", QUERIES_DIR / ".env", *SIBLING_ENV_CANDIDATES)

TARGET_TABLE = "ranking_municipios"
BATCH_SIZE = 500


def load_environment() -> None:
    loaded_files = []

    for env_file in ENV_FILES:
        if env_file.exists():
            load_dotenv(env_file, override=False)
            loaded_files.append(env_file)

    if not loaded_files:
        searched_paths = ", ".join(str(path) for path in ENV_FILES)
        raise FileNotFoundError(
            "Nenhum arquivo .env encontrado. Crie um arquivo .env na raiz do "
            f"projeto com as variaveis reais. Caminhos verificados: {searched_paths}"
        )

    print(
        "Variaveis de ambiente carregadas de: "
        + ", ".join(str(path) for path in loaded_files)
    )


def require_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if not value:
        raise RuntimeError(f"Variavel de ambiente obrigatoria ausente: {name}")
    return value


def create_local_engine() -> Engine:
    db_user = require_env("DB_USUARIO")
    db_password = require_env("DB_SENHA")
    db_host = require_env("DB_HOST", "localhost")
    db_port = require_env("DB_PORT", "5432")
    db_name = require_env("DB_BANCO", "cei")

    engine = create_engine(
        f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    )
    print("Conexao com o banco local estabelecida.")
    return engine


def create_supabase_client() -> Client:
    supabase_url = require_env("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or require_env("SUPABASE_KEY")

    client = create_client(supabase_url, supabase_key)
    print("Conexao com o Supabase estabelecida.")
    return client


def create_supabase_engine() -> Engine | None:
    database_url = os.getenv("SUPABASE_DB_URL") or os.getenv("SUPABASE_DATABASE_URL")
    if not database_url:
        print(
            "SUPABASE_DB_URL nao configurada; a criacao da tabela sera pulada. "
            "Se a tabela ja existir, a carga via API continua normalmente."
        )
        return None

    engine = create_engine(database_url)
    print("Conexao Postgres direta com o Supabase estabelecida.")
    return engine


def read_source_data(engine: Engine) -> pd.DataFrame:
    if not QUERY_FILE.exists():
        raise FileNotFoundError(f"Query nao encontrada: {QUERY_FILE}")

    query = QUERY_FILE.read_text(encoding="utf-8")
    frame = pd.read_sql_query(text(query), engine)
    print(f"Dados lidos do banco local: {len(frame)} linhas.")
    return frame


def normalize_scalar(value: Any) -> Any:
    if value is None:
        return None

    if hasattr(value, "item") and not isinstance(value, (str, bytes, bytearray)):
        try:
            value = value.item()
        except (TypeError, ValueError):
            pass

    if pd.isna(value):
        return None

    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, float) and not math.isfinite(value):
        return None

    return value


def dataframe_to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    normalized = frame.copy()

    for column in normalized.columns:
        series = normalized[column]
        if pd.api.types.is_float_dtype(series):
            non_null_series = series.dropna()
            if (
                not non_null_series.empty
                and non_null_series.map(lambda value: float(value).is_integer()).all()
            ):
                normalized[column] = series.astype("Int64")

    records = normalized.to_dict(orient="records")
    return [
        {str(column): normalize_scalar(value) for column, value in record.items()}
        for record in records
    ]


def replace_table_with_frame(engine: Engine, frame: pd.DataFrame) -> None:
    print(f"Criando/substituindo public.{TARGET_TABLE} no Supabase...")
    frame.to_sql(
        TARGET_TABLE,
        engine,
        schema="public",
        if_exists="replace",
        index=False,
        chunksize=BATCH_SIZE,
        method="multi",
    )
    print(f"Tabela public.{TARGET_TABLE} atualizada com {len(frame)} linha(s).")


def clear_target_table(client: Client) -> None:
    client.table(TARGET_TABLE).delete().gte("ano", 0).execute()


def upload_records(client: Client, records: list[dict[str, Any]]) -> None:
    if not records:
        print("Nenhum registro para inserir.")
        return

    total_batches = math.ceil(len(records) / BATCH_SIZE)
    for batch_number, start in enumerate(range(0, len(records), BATCH_SIZE), start=1):
        batch = records[start : start + BATCH_SIZE]
        client.table(TARGET_TABLE).insert(batch).execute()
        print(f"Lote {batch_number}/{total_batches} inserido.")


def main() -> None:
    start_time = time.time()
    load_environment()

    local_engine = create_local_engine()
    supabase_engine = create_supabase_engine()
    supabase_client = None if supabase_engine is not None else create_supabase_client()

    try:
        frame = read_source_data(local_engine)

        if supabase_engine is not None:
            replace_table_with_frame(supabase_engine, frame)
            elapsed = time.time() - start_time
            print(f"Carga concluida em {elapsed:.1f}s.")
            return

        records = dataframe_to_records(frame)

        print(f"Limpando dados atuais de public.{TARGET_TABLE}...")
        assert supabase_client is not None
        clear_target_table(supabase_client)

        print(f"Inserindo {len(records)} registro(s) em public.{TARGET_TABLE}...")
        upload_records(supabase_client, records)

        elapsed = time.time() - start_time
        print(f"Carga concluida em {elapsed:.1f}s.")
    except Exception as exc:
        print(f"Erro na carga de {TARGET_TABLE}: {exc}")
        with LOG_FILE.open("a", encoding="utf-8") as log_file:
            log_file.write(f"Erro na tabela {TARGET_TABLE}: {exc}\n")
        raise


if __name__ == "__main__":
    main()
