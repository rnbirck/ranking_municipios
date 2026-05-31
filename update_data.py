# %%
from __future__ import annotations

import math
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import pandas as pd
from dotenv import load_dotenv

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
    from supabase import Client


BASE_DIR = Path(__file__).resolve().parent
QUERIES_DIR = BASE_DIR / "queries"
LOG_FILE = BASE_DIR / "log_erros.txt"

DEFAULT_SOURCE_DATA_DIR = (
    BASE_DIR.parent / "CEI" / "cei" / "ranking_municipios" / "DB" / "data"
)
DEFAULT_INDICATOR_SUMMARY_FILE = (
    BASE_DIR.parent
    / "CEI"
    / "cei"
    / "ranking_municipios"
    / "resultados"
    / "resumo_indicadores_ranking_municipios_rs.xlsx"
)
SIBLING_ENV_CANDIDATES = (
    BASE_DIR.parent / "DASHBOARD-PNE" / ".env",
    BASE_DIR.parent / "CEI" / ".env",
)
ENV_FILES = (BASE_DIR / ".env", QUERIES_DIR / ".env", *SIBLING_ENV_CANDIDATES)

BATCH_SIZE = 500


@dataclass(frozen=True)
class TableConfig:
    source_file: str
    table_name: str
    clear_column: str
    clear_sentinel: int | str


TABLES = (
    TableConfig("base_final_municipio.xlsx", "ranking_municipios", "id_municipio", -1),
    TableConfig("base_educacao.xlsx", "base_educacao", "id_municipio", -1),
    TableConfig("base_financas.xlsx", "base_financas", "id_municipio", -1),
    TableConfig("base_meio_ambiente.xlsx", "base_meio_ambiente", "id_municipio", -1),
    TableConfig("base_saude.xlsx", "base_saude", "id_municipio", -1),
    TableConfig("base_seguranca.xlsx", "base_seguranca", "id_municipio", -1),
    TableConfig("base_socioeconomico.xlsx", "base_socioeconomico", "id_municipio", -1),
    TableConfig(
        "pesos_dimensoes_pca.xlsx", "pesos_dimensoes_pca", "dimensao", "__none__"
    ),
    TableConfig(
        "regressao_rf_previsoes.xlsx", "regressao_rf_previsoes", "id_municipio", -1
    ),
)

CATEGORY_TABLES = {
    "educacao": "base_educacao",
    "financas": "base_financas",
    "meio_ambiente": "base_meio_ambiente",
    "saude": "base_saude",
    "seguranca": "base_seguranca",
    "socioeconomico": "base_socioeconomico",
}
REGIONAL_SCORE_COLUMNS = {
    "nota_educacao": "Educação",
    "nota_financas": "Finanças",
    "nota_meio_ambiente": "Meio ambiente",
    "nota_saude": "Saúde",
    "nota_seguranca": "Segurança",
    "nota_socioeconomico": "Socioeconômico",
    "nota_final": "Ranking geral",
}
REGIONAL_SCORE_ORDER = tuple(REGIONAL_SCORE_COLUMNS)

DERIVED_TABLES = (
    TableConfig("", "dash_municipios_resumo", "id_municipio", -1),
    TableConfig("", "dash_municipio_categoria_historico", "id_municipio", -1),
    TableConfig("", "dash_municipio_indicadores", "id_municipio", -1),
    TableConfig("", "dash_regioes_resumo", "ano", -1),
    TableConfig("", "dash_regiao_ranking", "ano", -1),
    TableConfig("", "dash_regiao_historico", "ano", -1),
    TableConfig("", "dash_regiao_municipio_metricas", "ano", -1),
)

TABLE_INDEXES = {
    "ranking_municipios": (
        ("idx_ranking_municipios_ano_regiao", ("ano", "regiao_funcional")),
    ),
    "base_educacao": (
        (
            "idx_base_educacao_ano_regiao_municipio",
            ("ano", "regiao_funcional", "municipio"),
        ),
        ("idx_base_educacao_indicador", ("dimensao", "indicador")),
    ),
    "base_financas": (
        (
            "idx_base_financas_ano_regiao_municipio",
            ("ano", "regiao_funcional", "municipio"),
        ),
        ("idx_base_financas_indicador", ("dimensao", "indicador")),
    ),
    "base_meio_ambiente": (
        (
            "idx_base_meio_ambiente_ano_regiao_municipio",
            ("ano", "regiao_funcional", "municipio"),
        ),
        ("idx_base_meio_ambiente_indicador", ("dimensao", "indicador")),
    ),
    "base_saude": (
        (
            "idx_base_saude_ano_regiao_municipio",
            ("ano", "regiao_funcional", "municipio"),
        ),
        ("idx_base_saude_indicador", ("dimensao", "indicador")),
    ),
    "base_seguranca": (
        (
            "idx_base_seguranca_ano_regiao_municipio",
            ("ano", "regiao_funcional", "municipio"),
        ),
        ("idx_base_seguranca_indicador", ("dimensao", "indicador")),
    ),
    "base_socioeconomico": (
        (
            "idx_base_socioeconomico_ano_regiao_municipio",
            ("ano", "regiao_funcional", "municipio"),
        ),
        ("idx_base_socioeconomico_indicador", ("dimensao", "indicador")),
    ),
    "pesos_dimensoes_pca": (
        ("idx_pesos_dimensoes_pca_dimensao_indicador", ("dimensao", "indicador")),
    ),
    "regressao_rf_previsoes": (
        (
            "idx_regressao_rf_previsoes_ano_regiao_municipio",
            ("ano", "regiao_funcional", "municipio"),
        ),
    ),
    "dash_municipios_resumo": (
        (
            "idx_dash_municipios_resumo_ano_regiao_corede",
            ("ano", "regiao_funcional", "corede"),
        ),
        (
            "idx_dash_municipios_resumo_ano_regiao_municipio",
            ("ano", "regiao_funcional", "municipio"),
        ),
    ),
    "dash_municipio_categoria_historico": (
        (
            "idx_dash_municipio_categoria_hist_lookup",
            ("regiao_funcional", "municipio", "categoria", "ano"),
        ),
        (
            "idx_dash_municipio_categoria_hist_recorte",
            ("ano", "regiao_funcional", "categoria"),
        ),
    ),
    "dash_municipio_indicadores": (
        (
            "idx_dash_municipio_indicadores_lookup",
            ("ano", "regiao_funcional", "municipio", "categoria"),
        ),
        (
            "idx_dash_municipio_indicadores_historico",
            ("regiao_funcional", "municipio", "categoria", "indicador", "ano"),
        ),
        (
            "idx_dash_municipio_indicadores_recorte",
            ("ano", "regiao_funcional", "categoria", "indicador"),
        ),
    ),
    "dash_regioes_resumo": (
        (
            "idx_dash_regioes_resumo_ano_regiao",
            ("ano", "regiao_funcional"),
        ),
    ),
    "dash_regiao_ranking": (
        (
            "idx_dash_regiao_ranking_ano_regiao_corede_rank",
            ("ano", "regiao_funcional", "corede", "ranking_regiao_funcional"),
        ),
        (
            "idx_dash_regiao_ranking_hist",
            ("regiao_funcional", "municipio", "ano"),
        ),
    ),
    "dash_regiao_historico": (
        (
            "idx_dash_regiao_historico_lookup",
            ("regiao_funcional", "nivel_recorte", "recorte_valor", "ano"),
        ),
    ),
    "dash_regiao_municipio_metricas": (
        (
            "idx_dash_regiao_metricas_lookup",
            ("ano", "regiao_funcional", "municipio", "nivel_recorte", "recorte_valor"),
        ),
        (
            "idx_dash_regiao_metricas_recorte_indicador",
            (
                "ano",
                "regiao_funcional",
                "nivel_recorte",
                "recorte_valor",
                "indicador_chave",
            ),
        ),
    ),
}


def load_environment() -> None:
    loaded_files = []

    for env_file in ENV_FILES:
        if env_file.exists():
            load_dotenv(env_file, override=not loaded_files)
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


def resolve_source_data_dir() -> Path:
    configured_path = os.getenv("RANKING_DATA_DIR") or os.getenv("SOURCE_DATA_DIR")
    data_dir = Path(configured_path) if configured_path else DEFAULT_SOURCE_DATA_DIR
    data_dir = data_dir.expanduser().resolve()

    if not data_dir.exists():
        raise FileNotFoundError(
            "Pasta de dados nao encontrada. Configure RANKING_DATA_DIR no .env "
            f"ou crie a pasta padrao: {data_dir}"
        )

    return data_dir


def create_supabase_engine() -> Engine | None:
    database_url = os.getenv("SUPABASE_DB_URL") or os.getenv("SUPABASE_DATABASE_URL")
    if not database_url:
        print(
            "SUPABASE_DB_URL nao configurada; usando API do Supabase. "
            "As tabelas precisam existir e SUPABASE_SERVICE_KEY deve estar configurada."
        )
        return None

    from sqlalchemy import create_engine

    engine = create_engine(database_url)
    print("Conexao Postgres direta com o Supabase estabelecida.")
    return engine


def create_supabase_client_for_writes() -> Client:
    from supabase import create_client

    supabase_url = require_env("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    if not supabase_key:
        raise RuntimeError(
            "SUPABASE_SERVICE_KEY e obrigatoria para carga via API com RLS ativo. "
            "Alternativamente, configure SUPABASE_DB_URL para carga direta no Postgres."
        )

    client = create_client(supabase_url, supabase_key)
    host = urlparse(supabase_url).hostname or ""
    project_ref = host.split(".")[0] if host else "desconhecido"
    print(f"Conexao com a API do Supabase estabelecida. Projeto alvo: {project_ref}.")
    return client


def normalize_identifier(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    identifier = re.sub(r"[^0-9a-zA-Z_]+", "_", ascii_value.strip().lower())
    identifier = re.sub(r"_+", "_", identifier).strip("_")

    if not identifier:
        raise ValueError(f"Nome invalido para identificador SQL: {value!r}")
    if identifier[0].isdigit():
        identifier = f"col_{identifier}"

    return identifier


def normalize_columns(columns: pd.Index) -> list[str]:
    normalized_columns = []
    seen: dict[str, int] = {}

    for column in columns:
        identifier = normalize_identifier(str(column))
        count = seen.get(identifier, 0) + 1
        seen[identifier] = count
        normalized_columns.append(identifier if count == 1 else f"{identifier}_{count}")

    return normalized_columns


def read_source_table(data_dir: Path, config: TableConfig) -> pd.DataFrame:
    path = data_dir / config.source_file
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de origem nao encontrado: {path}")

    frame = pd.read_excel(path)
    frame.columns = normalize_columns(frame.columns)
    print(f"{config.source_file} lido: {len(frame)} linha(s).")
    return frame


def resolve_indicator_summary_file(data_dir: Path) -> Path:
    configured_path = os.getenv("INDICATOR_SUMMARY_FILE") or os.getenv(
        "RESUMO_INDICADORES_FILE"
    )
    if configured_path:
        return Path(configured_path).expanduser().resolve()

    derived_path = (
        data_dir.parent.parent
        / "resultados"
        / "resumo_indicadores_ranking_municipios_rs.xlsx"
    )
    return derived_path if derived_path.exists() else DEFAULT_INDICATOR_SUMMARY_FILE


def read_indicator_names(data_dir: Path) -> pd.DataFrame:
    path = resolve_indicator_summary_file(data_dir)
    if not path.exists():
        print(
            "Arquivo de resumo de indicadores nao encontrado; "
            "os nomes amigaveis nao serao carregados."
        )
        return pd.DataFrame(columns=["indicador", "indicador_nome"])

    frame = pd.read_excel(path)
    frame.columns = normalize_columns(frame.columns)
    if "indicador" not in frame.columns or "nome" not in frame.columns:
        raise ValueError(
            "O resumo de indicadores precisa conter as colunas 'indicador' e 'nome'."
        )

    names = frame[["indicador", "nome"]].copy()
    names["indicador"] = names["indicador"].fillna("").astype(str).str.strip()
    names["indicador_nome"] = names["nome"].fillna("").astype(str).str.strip()
    names = names[names["indicador"] != ""]
    names = names.drop_duplicates("indicador")
    print(f"{path.name} lido: {len(names)} indicador(es) nomeado(s).")
    return names[["indicador", "indicador_nome"]]


def quote_identifier(identifier: str) -> str:
    normalized = normalize_identifier(identifier)
    if normalized != identifier:
        raise ValueError(f"Identificador SQL invalido: {identifier!r}")
    return f'"{identifier}"'


def apply_rls_and_read_policy(engine: Engine, table_name: str) -> None:
    from sqlalchemy import text

    table_identifier = quote_identifier(table_name)
    policy_name = quote_identifier(f"{table_name}_select_public")

    statements = (
        f"alter table public.{table_identifier} enable row level security",
        f"drop policy if exists {policy_name} on public.{table_identifier}",
        (
            f"create policy {policy_name} on public.{table_identifier} "
            "for select to anon, authenticated using (true)"
        ),
        f"grant select on public.{table_identifier} to anon, authenticated",
        f"grant all on public.{table_identifier} to service_role",
    )

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def apply_table_indexes(engine: Engine, table_name: str) -> None:
    from sqlalchemy import text

    table_identifier = quote_identifier(table_name)
    index_configs = TABLE_INDEXES.get(table_name, ())

    with engine.begin() as connection:
        for index_name, columns in index_configs:
            index_identifier = quote_identifier(index_name)
            column_identifiers = ", ".join(
                quote_identifier(column) for column in columns
            )
            statement = (
                f"create index if not exists {index_identifier} "
                f"on public.{table_identifier} ({column_identifiers})"
            )
            connection.execute(text(statement))


def replace_table_with_frame(
    engine: Engine, config: TableConfig, frame: pd.DataFrame
) -> None:
    print(f"Criando/substituindo public.{config.table_name} no Supabase...")
    frame.to_sql(
        config.table_name,
        engine,
        schema="public",
        if_exists="replace",
        index=False,
        chunksize=BATCH_SIZE,
        method="multi",
    )
    apply_table_indexes(engine, config.table_name)
    apply_rls_and_read_policy(engine, config.table_name)
    print(f"public.{config.table_name} atualizada com {len(frame)} linha(s).")


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


def clear_target_table(client: Client, config: TableConfig) -> None:
    client.table(config.table_name).delete().neq(
        config.clear_column, config.clear_sentinel
    ).execute()


def _migration_file_for_table(table_name: str) -> str:
    if table_name in {
        "dash_municipios_resumo",
        "dash_municipio_categoria_historico",
        "dash_municipio_indicadores",
    }:
        return "queries/create_dashboard_municipios_tables.sql"

    if table_name in {
        "dash_regioes_resumo",
        "dash_regiao_ranking",
        "dash_regiao_historico",
        "dash_regiao_municipio_metricas",
    }:
        return "queries/create_dashboard_regioes_tables.sql"

    return "queries/create_supabase_tables.sql"


def _raise_schema_cache_error(config: TableConfig, exc: Exception) -> None:
    column_match = re.search(
        r"Could not find the '([^']+)' column of '([^']+)' in the schema cache",
        str(exc),
    )
    if column_match:
        missing_column, table_name = column_match.groups()
        migration_file = _migration_file_for_table(table_name)
        raise RuntimeError(
            "Schema cache do PostgREST desatualizado para "
            f"public.{table_name}: a coluna '{missing_column}' nao foi reconhecida. "
            f"Execute o script {migration_file} no SQL Editor do Supabase "
            "e depois rode `NOTIFY pgrst, 'reload schema';`. "
            "Se puder, configure SUPABASE_DB_URL para usar carga direta no Postgres "
            "e evitar esse gargalo de cache da API."
        ) from exc

    table_match = re.search(
        r"Could not find the table 'public\.([^']+)' in the schema cache",
        str(exc),
    )
    if not table_match:
        return

    table_name = table_match.group(1)
    migration_file = _migration_file_for_table(table_name)
    raise RuntimeError(
        "Schema cache do PostgREST desatualizado ou tabela ausente para "
        f"public.{table_name}. Execute o script {migration_file} no SQL Editor do Supabase "
        "para criar ou atualizar as tabelas, depois rode `NOTIFY pgrst, 'reload schema';`. "
        "Se a tabela ja existir, esse erro ainda indica que o cache do PostgREST nao foi recarregado."
    ) from exc


def upload_records(
    client: Client, config: TableConfig, records: list[dict[str, Any]]
) -> None:
    if not records:
        print(f"Nenhum registro para inserir em public.{config.table_name}.")
        return

    total_batches = math.ceil(len(records) / BATCH_SIZE)
    for batch_number, start in enumerate(range(0, len(records), BATCH_SIZE), start=1):
        batch = records[start : start + BATCH_SIZE]
        client.table(config.table_name).insert(batch).execute()
        print(
            f"public.{config.table_name}: lote {batch_number}/{total_batches} inserido."
        )


def upload_table_with_api(
    client: Client, config: TableConfig, frame: pd.DataFrame
) -> None:
    records = dataframe_to_records(frame)

    try:
        print(f"Limpando dados atuais de public.{config.table_name}...")
        clear_target_table(client, config)

        print(f"Inserindo {len(records)} registro(s) em public.{config.table_name}...")
        upload_records(client, config, records)
    except Exception as exc:
        _raise_schema_cache_error(config, exc)
        raise


def _empty_category_summary() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "id_municipio",
            "municipio",
            "ano",
            "regiao_funcional",
            "corede",
            "categoria",
            "nota_dimensao",
            "ranking_dimensao",
        ]
    )


def build_category_long_frame(loaded_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames = []
    for category, table_name in CATEGORY_TABLES.items():
        frame = loaded_frames.get(table_name, pd.DataFrame()).copy()
        if frame.empty:
            continue
        frame["categoria"] = category
        frames.append(frame)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def build_category_summary_frame(category_long: pd.DataFrame) -> pd.DataFrame:
    if category_long.empty:
        return _empty_category_summary()

    columns = [
        "id_municipio",
        "municipio",
        "ano",
        "regiao_funcional",
        "corede",
        "categoria",
        "nota_dimensao",
        "ranking_dimensao",
    ]
    missing = [column for column in columns if column not in category_long.columns]
    if missing:
        raise ValueError(
            "Colunas ausentes para gerar resumo de categorias: " + ", ".join(missing)
        )

    summary = category_long[columns].copy()
    summary = summary.drop_duplicates(
        ["id_municipio", "ano", "regiao_funcional", "categoria"]
    )
    return summary.sort_values(
        ["ano", "regiao_funcional", "ranking_dimensao", "municipio", "categoria"]
    ).reset_index(drop=True)


def _region_totals(ranking: pd.DataFrame) -> pd.DataFrame:
    if ranking.empty:
        return pd.DataFrame(
            columns=["ano", "regiao_funcional", "total_municipios_regiao"]
        )
    return (
        ranking.groupby(["ano", "regiao_funcional"], dropna=False)["municipio"]
        .nunique()
        .reset_index(name="total_municipios_regiao")
    )


def _region_code(value: str) -> str:
    text = str(value or "").strip()
    match = re.search(r"RF\s*\d+|RF\d+", text, re.IGNORECASE)
    if match:
        return match.group(0).replace(" ", "").upper()
    return text.split("—")[0].split("-")[0].strip()


def _classification_status(value: Any) -> str:
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


def _previous_year_lookup(ranking: pd.DataFrame) -> pd.DataFrame:
    if ranking.empty or "ano" not in ranking.columns:
        return pd.DataFrame(columns=["ano", "ano_referencia_anterior"])

    years = sorted(
        pd.to_numeric(ranking["ano"], errors="coerce").dropna().astype(int).unique()
    )
    if len(years) < 2:
        return pd.DataFrame(columns=["ano", "ano_referencia_anterior"])

    return pd.DataFrame(
        {
            "ano": years[1:],
            "ano_referencia_anterior": years[:-1],
        }
    )


def _score_mean_aggregations() -> dict[str, tuple[str, str]]:
    return {f"{column}_media": (column, "mean") for column in REGIONAL_SCORE_ORDER}


def _empty_dash_regioes_resumo() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "ano",
            "regiao_funcional",
            "regiao_codigo",
            "total_municipios",
            "total_coredes",
            "coredes_txt",
            *[f"{column}_media" for column in REGIONAL_SCORE_ORDER],
        ]
    )


def _empty_dash_regiao_ranking() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "id_municipio",
            "municipio",
            "ano",
            "ano_referencia_anterior",
            "regiao_funcional",
            "regiao_codigo",
            "corede",
            "ranking_regiao_funcional",
            "ranking_regiao_funcional_anterior",
            "delta_posicao_regiao",
            "classificacao",
            "classificacao_status",
            "nota_final",
            "nota_final_anterior",
            "delta_nota_final",
            "nota_educacao",
            "nota_financas",
            "nota_meio_ambiente",
            "nota_saude",
            "nota_seguranca",
            "nota_socioeconomico",
            "total_municipios_regiao",
        ]
    )


def _empty_dash_regiao_historico() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "ano",
            "regiao_funcional",
            "regiao_codigo",
            "nivel_recorte",
            "recorte_valor",
            "total_municipios_recorte",
            *[f"{column}_media" for column in REGIONAL_SCORE_ORDER],
        ]
    )


def _empty_dash_regiao_municipio_metricas() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "id_municipio",
            "municipio",
            "ano",
            "ano_referencia_anterior",
            "regiao_funcional",
            "regiao_codigo",
            "corede",
            "nivel_recorte",
            "recorte_valor",
            "indicador_chave",
            "indicador_label",
            "ordem",
            "nota_atual",
            "nota_anterior",
            "delta_nota",
            "posicao_recorte",
            "posicao_recorte_anterior",
            "delta_posicao",
            "media_recorte_indicador",
            "total_municipios_recorte",
        ]
    )


def _merge_regression_classification(
    ranking: pd.DataFrame, predictions: pd.DataFrame
) -> pd.DataFrame:
    if ranking.empty or predictions.empty or "classificacao" not in predictions.columns:
        return ranking

    if "classificacao" in ranking.columns:
        return ranking

    key_candidates = [
        ["id_municipio", "ano", "regiao_funcional"],
        ["municipio", "ano", "regiao_funcional"],
    ]
    for keys in key_candidates:
        if all(
            column in ranking.columns and column in predictions.columns
            for column in keys
        ):
            lookup = (
                predictions[keys + ["classificacao"]]
                .dropna(subset=["classificacao"])
                .drop_duplicates(keys)
            )
            if lookup.empty:
                return ranking
            return ranking.merge(lookup, on=keys, how="left")

    return ranking


def _pivot_category_column(
    summary: pd.DataFrame,
    value_column: str,
    prefix: str,
) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame()

    index_columns = [
        "id_municipio",
        "municipio",
        "ano",
        "regiao_funcional",
        "corede",
    ]
    wide = (
        summary.pivot_table(
            index=index_columns,
            columns="categoria",
            values=value_column,
            aggfunc="first",
        )
        .rename(
            columns={category: f"{prefix}_{category}" for category in CATEGORY_TABLES}
        )
        .reset_index()
    )
    wide.columns.name = None
    return wide


def build_dash_municipios_resumo(
    ranking: pd.DataFrame, category_summary: pd.DataFrame
) -> pd.DataFrame:
    if ranking.empty:
        return pd.DataFrame()

    index_columns = [
        "id_municipio",
        "municipio",
        "ano",
        "regiao_funcional",
        "corede",
    ]
    resumo = ranking.copy()

    current_rankings = _pivot_category_column(
        category_summary, "ranking_dimensao", "ranking"
    )
    if not current_rankings.empty:
        resumo = resumo.merge(current_rankings, on=index_columns, how="left")

    previous = category_summary.sort_values(
        ["id_municipio", "regiao_funcional", "categoria", "ano"]
    ).copy()
    previous_group = previous.groupby(
        ["id_municipio", "regiao_funcional", "categoria"], dropna=False
    )
    previous["ranking_dimensao_anterior"] = previous_group["ranking_dimensao"].shift(1)
    previous["ano_anterior_categoria"] = previous_group["ano"].shift(1)

    previous_rankings = _pivot_category_column(
        previous, "ranking_dimensao_anterior", "ranking_anterior"
    )
    previous_years = _pivot_category_column(
        previous, "ano_anterior_categoria", "ano_anterior"
    )
    if not previous_rankings.empty:
        resumo = resumo.merge(previous_rankings, on=index_columns, how="left")
    if not previous_years.empty:
        resumo = resumo.merge(previous_years, on=index_columns, how="left")

    resumo = resumo.merge(
        _region_totals(ranking), on=["ano", "regiao_funcional"], how="left"
    )

    ordered_columns = [
        "id_municipio",
        "municipio",
        "ano",
        "regiao_funcional",
        "corede",
        "ranking_regiao_funcional",
        "total_municipios_regiao",
        "classificacao",
        "nota_educacao",
        "nota_financas",
        "nota_meio_ambiente",
        "nota_saude",
        "nota_seguranca",
        "nota_socioeconomico",
        "nota_final",
    ]
    for category in CATEGORY_TABLES:
        ordered_columns.append(f"ranking_{category}")
        ordered_columns.append(f"ranking_anterior_{category}")
        ordered_columns.append(f"ano_anterior_{category}")

    existing_columns = [
        column for column in ordered_columns if column in resumo.columns
    ]
    remaining_columns = [
        column for column in resumo.columns if column not in existing_columns
    ]
    return resumo[existing_columns + remaining_columns]


def build_dash_municipio_categoria_historico(
    ranking: pd.DataFrame, category_summary: pd.DataFrame
) -> pd.DataFrame:
    if category_summary.empty:
        return category_summary.copy()

    historico = category_summary.merge(
        _region_totals(ranking), on=["ano", "regiao_funcional"], how="left"
    )
    columns = [
        "id_municipio",
        "municipio",
        "ano",
        "regiao_funcional",
        "corede",
        "categoria",
        "nota_dimensao",
        "ranking_dimensao",
        "total_municipios_regiao",
    ]
    return historico[columns].sort_values(
        ["regiao_funcional", "municipio", "categoria", "ano"]
    )


def build_dash_municipio_indicadores(
    ranking: pd.DataFrame,
    category_long: pd.DataFrame,
    indicator_names: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if category_long.empty:
        return pd.DataFrame()

    indicadores = category_long.copy()
    if indicator_names is not None and not indicator_names.empty:
        indicadores = indicadores.merge(indicator_names, on="indicador", how="left")
    if "indicador_nome" not in indicadores.columns:
        indicadores["indicador_nome"] = pd.NA
    indicadores["indicador_nome"] = (
        indicadores["indicador_nome"].fillna("").astype(str).str.strip()
    )
    indicadores["media_nota_indicador_regiao"] = indicadores.groupby(
        ["ano", "regiao_funcional", "categoria", "indicador"], dropna=False
    )["nota_indicador"].transform("mean")
    indicadores["media_valor_original_regiao"] = indicadores.groupby(
        ["ano", "regiao_funcional", "categoria", "indicador"], dropna=False
    )["valor_original"].transform("mean")
    indicadores = indicadores.sort_values(
        [
            "ano",
            "regiao_funcional",
            "categoria",
            "indicador",
            "ranking_indicador",
            "ranking_dimensao",
            "municipio",
        ],
        na_position="last",
    ).copy()
    indicadores["ranking_indicador_desempatado"] = (
        indicadores.groupby(
            ["ano", "regiao_funcional", "categoria", "indicador"], dropna=False
        ).cumcount()
        + 1
    )
    indicadores = indicadores.merge(
        _region_totals(ranking), on=["ano", "regiao_funcional"], how="left"
    )

    columns = [
        "id_municipio",
        "municipio",
        "ano",
        "regiao_funcional",
        "corede",
        "categoria",
        "indicador",
        "indicador_nome",
        "nota_indicador",
        "ranking_indicador",
        "ranking_indicador_desempatado",
        "nota_dimensao",
        "ranking_dimensao",
        "valor_original",
        "valor_usado_nota",
        "valor_imputado",
        "media_nota_indicador_regiao",
        "media_valor_original_regiao",
        "total_municipios_regiao",
    ]
    existing_columns = [column for column in columns if column in indicadores.columns]
    return indicadores[existing_columns].sort_values(
        [
            "ano",
            "regiao_funcional",
            "municipio",
            "categoria",
            "ranking_indicador_desempatado",
            "indicador",
        ]
    )


def build_dash_regioes_resumo(ranking: pd.DataFrame) -> pd.DataFrame:
    if ranking.empty:
        return _empty_dash_regioes_resumo()

    resumo = (
        ranking.groupby(["ano", "regiao_funcional"], dropna=False)
        .agg(
            total_municipios=("municipio", "nunique"),
            **_score_mean_aggregations(),
        )
        .reset_index()
    )

    corede_rows = []
    for (ano, regiao), group in ranking.groupby(
        ["ano", "regiao_funcional"], dropna=False
    ):
        coredes = sorted(
            {
                str(value).strip()
                for value in group.get("corede", pd.Series(dtype="object"))
                if not pd.isna(value) and str(value).strip()
            }
        )
        corede_rows.append(
            {
                "ano": ano,
                "regiao_funcional": regiao,
                "regiao_codigo": _region_code(regiao),
                "total_coredes": len(coredes),
                "coredes_txt": ", ".join(coredes),
            }
        )

    resumo = resumo.merge(
        pd.DataFrame(corede_rows),
        on=["ano", "regiao_funcional"],
        how="left",
    )

    ordered_columns = list(_empty_dash_regioes_resumo().columns)
    return (
        resumo[ordered_columns]
        .sort_values(
            ["ano", "regiao_funcional"],
            ascending=[False, True],
        )
        .reset_index(drop=True)
    )


def build_dash_regiao_ranking(ranking: pd.DataFrame) -> pd.DataFrame:
    if ranking.empty:
        return _empty_dash_regiao_ranking()

    frame = ranking.copy()
    frame["regiao_codigo"] = frame["regiao_funcional"].map(_region_code)
    frame["classificacao_status"] = frame.get(
        "classificacao", pd.Series(dtype="object")
    ).map(_classification_status)
    frame = frame.merge(
        _region_totals(ranking), on=["ano", "regiao_funcional"], how="left"
    )
    frame = frame.merge(_previous_year_lookup(ranking), on="ano", how="left")

    previous = ranking[
        [
            "municipio",
            "regiao_funcional",
            "ano",
            "ranking_regiao_funcional",
            "nota_final",
        ]
    ].rename(
        columns={
            "ano": "ano_referencia_anterior",
            "ranking_regiao_funcional": "ranking_regiao_funcional_anterior",
            "nota_final": "nota_final_anterior",
        }
    )

    frame = frame.merge(
        previous,
        on=["municipio", "regiao_funcional", "ano_referencia_anterior"],
        how="left",
    )
    frame["delta_nota_final"] = frame["nota_final"] - frame["nota_final_anterior"]
    frame["delta_posicao_regiao"] = (
        pd.to_numeric(frame["ranking_regiao_funcional_anterior"], errors="coerce")
        - pd.to_numeric(frame["ranking_regiao_funcional"], errors="coerce")
    ).astype("Int64")

    ordered_columns = list(_empty_dash_regiao_ranking().columns)
    existing_columns = [column for column in ordered_columns if column in frame.columns]
    return (
        frame[existing_columns]
        .sort_values(
            ["ano", "regiao_funcional", "ranking_regiao_funcional", "municipio"],
            ascending=[False, True, True, True],
        )
        .reset_index(drop=True)
    )


def build_dash_regiao_historico(ranking: pd.DataFrame) -> pd.DataFrame:
    if ranking.empty:
        return _empty_dash_regiao_historico()

    region_history = (
        ranking.groupby(["ano", "regiao_funcional"], dropna=False)
        .agg(
            total_municipios_recorte=("municipio", "nunique"),
            **_score_mean_aggregations(),
        )
        .reset_index()
    )
    region_history["regiao_codigo"] = region_history["regiao_funcional"].map(
        _region_code
    )
    region_history["nivel_recorte"] = "regiao"
    region_history["recorte_valor"] = region_history["regiao_funcional"]

    corede_frame = ranking[
        ranking.get("corede", pd.Series(dtype="object"))
        .fillna("")
        .astype(str)
        .str.strip()
        != ""
    ].copy()
    if corede_frame.empty:
        history = region_history
    else:
        corede_history = (
            corede_frame.groupby(["ano", "regiao_funcional", "corede"], dropna=False)
            .agg(
                total_municipios_recorte=("municipio", "nunique"),
                **_score_mean_aggregations(),
            )
            .reset_index()
        )
        corede_history["regiao_codigo"] = corede_history["regiao_funcional"].map(
            _region_code
        )
        corede_history["nivel_recorte"] = "corede"
        corede_history["recorte_valor"] = corede_history["corede"]
        history = pd.concat(
            [region_history, corede_history], ignore_index=True, sort=False
        )

    ordered_columns = list(_empty_dash_regiao_historico().columns)
    return (
        history[ordered_columns]
        .sort_values(
            ["regiao_funcional", "nivel_recorte", "recorte_valor", "ano"],
            ascending=[True, True, True, True],
        )
        .reset_index(drop=True)
    )


def _build_regional_metric_long_frame(ranking: pd.DataFrame) -> pd.DataFrame:
    if ranking.empty:
        return pd.DataFrame()

    value_columns = [
        column for column in REGIONAL_SCORE_ORDER if column in ranking.columns
    ]
    if not value_columns:
        return pd.DataFrame()

    long_frame = ranking[
        [
            "id_municipio",
            "municipio",
            "ano",
            "regiao_funcional",
            "corede",
            *value_columns,
        ]
    ].melt(
        id_vars=["id_municipio", "municipio", "ano", "regiao_funcional", "corede"],
        value_vars=value_columns,
        var_name="indicador_chave",
        value_name="nota_atual",
    )
    long_frame["regiao_codigo"] = long_frame["regiao_funcional"].map(_region_code)
    long_frame["indicador_label"] = long_frame["indicador_chave"].map(
        REGIONAL_SCORE_COLUMNS
    )
    long_frame["ordem"] = long_frame["indicador_chave"].map(
        {column: index + 1 for index, column in enumerate(REGIONAL_SCORE_ORDER)}
    )
    return long_frame


def _build_regional_metric_cut(long_frame: pd.DataFrame, level: str) -> pd.DataFrame:
    if long_frame.empty:
        return pd.DataFrame()

    metrics = long_frame.copy()
    if level == "regiao":
        metrics["nivel_recorte"] = "regiao"
        metrics["recorte_valor"] = metrics["regiao_funcional"]
    else:
        metrics = metrics[
            metrics.get("corede", pd.Series(dtype="object"))
            .fillna("")
            .astype(str)
            .str.strip()
            != ""
        ].copy()
        if metrics.empty:
            return metrics
        metrics["nivel_recorte"] = "corede"
        metrics["recorte_valor"] = metrics["corede"]

    grouping = [
        "ano",
        "regiao_funcional",
        "nivel_recorte",
        "recorte_valor",
        "indicador_chave",
    ]
    metrics["posicao_recorte"] = (
        metrics.groupby(grouping, dropna=False)["nota_atual"]
        .rank(method="min", ascending=False)
        .astype("Int64")
    )
    metrics["media_recorte_indicador"] = metrics.groupby(grouping, dropna=False)[
        "nota_atual"
    ].transform("mean")
    metrics["total_municipios_recorte"] = metrics.groupby(
        ["ano", "regiao_funcional", "nivel_recorte", "recorte_valor"],
        dropna=False,
    )["municipio"].transform("nunique")
    return metrics


def build_dash_regiao_municipio_metricas(ranking: pd.DataFrame) -> pd.DataFrame:
    if ranking.empty:
        return _empty_dash_regiao_municipio_metricas()

    long_frame = _build_regional_metric_long_frame(ranking)
    if long_frame.empty:
        return _empty_dash_regiao_municipio_metricas()

    metrics = pd.concat(
        [
            _build_regional_metric_cut(long_frame, "regiao"),
            _build_regional_metric_cut(long_frame, "corede"),
        ],
        ignore_index=True,
        sort=False,
    )
    if metrics.empty:
        return _empty_dash_regiao_municipio_metricas()

    metrics = metrics.merge(_previous_year_lookup(ranking), on="ano", how="left")
    previous = metrics[
        [
            "municipio",
            "regiao_funcional",
            "nivel_recorte",
            "recorte_valor",
            "indicador_chave",
            "ano",
            "nota_atual",
            "posicao_recorte",
        ]
    ].rename(
        columns={
            "ano": "ano_referencia_anterior",
            "nota_atual": "nota_anterior",
            "posicao_recorte": "posicao_recorte_anterior",
        }
    )
    metrics = metrics.merge(
        previous,
        on=[
            "municipio",
            "regiao_funcional",
            "nivel_recorte",
            "recorte_valor",
            "indicador_chave",
            "ano_referencia_anterior",
        ],
        how="left",
    )
    metrics["delta_nota"] = metrics["nota_atual"] - metrics["nota_anterior"]
    metrics["delta_posicao"] = (
        pd.to_numeric(metrics["posicao_recorte_anterior"], errors="coerce")
        - pd.to_numeric(metrics["posicao_recorte"], errors="coerce")
    ).astype("Int64")

    ordered_columns = list(_empty_dash_regiao_municipio_metricas().columns)
    return (
        metrics[ordered_columns]
        .sort_values(
            [
                "ano",
                "regiao_funcional",
                "municipio",
                "nivel_recorte",
                "recorte_valor",
                "ordem",
            ],
            ascending=[False, True, True, True, True, True],
        )
        .reset_index(drop=True)
    )


def build_derived_tables(
    loaded_frames: dict[str, pd.DataFrame],
    indicator_names: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    ranking = loaded_frames.get("ranking_municipios", pd.DataFrame()).copy()
    ranking = _merge_regression_classification(
        ranking, loaded_frames.get("regressao_rf_previsoes", pd.DataFrame()).copy()
    )
    category_long = build_category_long_frame(loaded_frames)
    category_summary = build_category_summary_frame(category_long)

    return {
        "dash_municipios_resumo": build_dash_municipios_resumo(
            ranking, category_summary
        ),
        "dash_municipio_categoria_historico": build_dash_municipio_categoria_historico(
            ranking, category_summary
        ),
        "dash_municipio_indicadores": build_dash_municipio_indicadores(
            ranking, category_long, indicator_names
        ),
        "dash_regioes_resumo": build_dash_regioes_resumo(ranking),
        "dash_regiao_ranking": build_dash_regiao_ranking(ranking),
        "dash_regiao_historico": build_dash_regiao_historico(ranking),
        "dash_regiao_municipio_metricas": build_dash_regiao_municipio_metricas(ranking),
    }


def main() -> None:
    start_time = time.time()
    load_environment()

    data_dir = resolve_source_data_dir()
    print(f"Pasta de dados: {data_dir}")

    supabase_engine = create_supabase_engine()
    supabase_client = (
        None if supabase_engine is not None else create_supabase_client_for_writes()
    )
    loaded_frames: dict[str, pd.DataFrame] = {}

    for config in TABLES:
        try:
            frame = read_source_table(data_dir, config)
            loaded_frames[config.table_name] = frame

            if supabase_engine is not None:
                replace_table_with_frame(supabase_engine, config, frame)
            else:
                assert supabase_client is not None
                upload_table_with_api(supabase_client, config, frame)
        except Exception as exc:
            print(f"Erro na carga de {config.table_name}: {exc}")
            with LOG_FILE.open("a", encoding="utf-8") as log_file:
                log_file.write(f"Erro na tabela {config.table_name}: {exc}\n")
            raise

    indicator_names = read_indicator_names(data_dir)
    derived_frames = build_derived_tables(loaded_frames, indicator_names)
    for config in DERIVED_TABLES:
        try:
            frame = derived_frames.get(config.table_name, pd.DataFrame())
            print(f"{config.table_name} gerada: {len(frame)} linha(s).")

            if supabase_engine is not None:
                replace_table_with_frame(supabase_engine, config, frame)
            else:
                assert supabase_client is not None
                upload_table_with_api(supabase_client, config, frame)
        except Exception as exc:
            print(f"Erro na carga de {config.table_name}: {exc}")
            with LOG_FILE.open("a", encoding="utf-8") as log_file:
                log_file.write(f"Erro na tabela {config.table_name}: {exc}\n")
            raise

    elapsed = time.time() - start_time
    print(f"Carga concluida em {elapsed:.1f}s.")


if __name__ == "__main__":
    main()
