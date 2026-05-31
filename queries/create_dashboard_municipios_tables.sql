-- Execute no SQL Editor do Supabase para criar as tabelas otimizadas
-- usadas pelos visuais da pagina de municipios.

grant usage on schema public to anon, authenticated;

create table if not exists public.dash_municipios_resumo (
    id_municipio bigint,
    municipio text,
    ano bigint,
    regiao_funcional text,
    corede text,
    ranking_regiao_funcional bigint,
    total_municipios_regiao bigint,
    classificacao text,
    nota_educacao double precision,
    nota_financas double precision,
    nota_meio_ambiente double precision,
    nota_saude double precision,
    nota_seguranca double precision,
    nota_socioeconomico double precision,
    nota_final double precision,
    ranking_educacao bigint,
    ranking_anterior_educacao bigint,
    ano_anterior_educacao bigint,
    ranking_financas bigint,
    ranking_anterior_financas bigint,
    ano_anterior_financas bigint,
    ranking_meio_ambiente bigint,
    ranking_anterior_meio_ambiente bigint,
    ano_anterior_meio_ambiente bigint,
    ranking_saude bigint,
    ranking_anterior_saude bigint,
    ano_anterior_saude bigint,
    ranking_seguranca bigint,
    ranking_anterior_seguranca bigint,
    ano_anterior_seguranca bigint,
    ranking_socioeconomico bigint,
    ranking_anterior_socioeconomico bigint,
    ano_anterior_socioeconomico bigint
);

create table if not exists public.dash_municipio_categoria_historico (
    id_municipio bigint,
    municipio text,
    ano bigint,
    regiao_funcional text,
    corede text,
    categoria text,
    nota_dimensao double precision,
    ranking_dimensao bigint,
    total_municipios_regiao bigint
);

create table if not exists public.dash_municipio_indicadores (
    id_municipio bigint,
    municipio text,
    ano bigint,
    regiao_funcional text,
    corede text,
    categoria text,
    indicador text,
    indicador_nome text,
    nota_indicador double precision,
    ranking_indicador bigint,
    ranking_indicador_desempatado bigint,
    nota_dimensao double precision,
    ranking_dimensao bigint,
    valor_original double precision,
    valor_usado_nota double precision,
    valor_imputado text,
    media_nota_indicador_regiao double precision,
    media_valor_original_regiao double precision,
    total_municipios_regiao bigint
);

alter table public.dash_municipio_indicadores
    add column if not exists indicador_nome text;
alter table public.dash_municipio_indicadores
    add column if not exists ranking_indicador_desempatado bigint;
alter table public.dash_municipio_indicadores
    add column if not exists media_valor_original_regiao double precision;
alter table public.dash_municipios_resumo
    add column if not exists classificacao text;

create index if not exists idx_dash_municipios_resumo_ano_regiao_corede
    on public.dash_municipios_resumo (ano, regiao_funcional, corede);
create index if not exists idx_dash_municipios_resumo_ano_regiao_municipio
    on public.dash_municipios_resumo (ano, regiao_funcional, municipio);

create index if not exists idx_dash_municipio_categoria_hist_lookup
    on public.dash_municipio_categoria_historico (regiao_funcional, municipio, categoria, ano);
create index if not exists idx_dash_municipio_categoria_hist_recorte
    on public.dash_municipio_categoria_historico (ano, regiao_funcional, categoria);

create index if not exists idx_dash_municipio_indicadores_lookup
    on public.dash_municipio_indicadores (ano, regiao_funcional, municipio, categoria);
create index if not exists idx_dash_municipio_indicadores_historico
    on public.dash_municipio_indicadores (regiao_funcional, municipio, categoria, indicador, ano);
create index if not exists idx_dash_municipio_indicadores_recorte
    on public.dash_municipio_indicadores (ano, regiao_funcional, categoria, indicador);

alter table public.dash_municipios_resumo enable row level security;
alter table public.dash_municipio_categoria_historico enable row level security;
alter table public.dash_municipio_indicadores enable row level security;

drop policy if exists dash_municipios_resumo_select_public on public.dash_municipios_resumo;
create policy dash_municipios_resumo_select_public
    on public.dash_municipios_resumo for select
    to anon, authenticated
    using (true);

drop policy if exists dash_municipio_categoria_historico_select_public on public.dash_municipio_categoria_historico;
create policy dash_municipio_categoria_historico_select_public
    on public.dash_municipio_categoria_historico for select
    to anon, authenticated
    using (true);

drop policy if exists dash_municipio_indicadores_select_public on public.dash_municipio_indicadores;
create policy dash_municipio_indicadores_select_public
    on public.dash_municipio_indicadores for select
    to anon, authenticated
    using (true);

grant select on public.dash_municipios_resumo to anon, authenticated;
grant select on public.dash_municipio_categoria_historico to anon, authenticated;
grant select on public.dash_municipio_indicadores to anon, authenticated;

grant all on public.dash_municipios_resumo to service_role;
grant all on public.dash_municipio_categoria_historico to service_role;
grant all on public.dash_municipio_indicadores to service_role;

-- Atualiza o cache do PostgREST apos alteracoes de schema.
notify pgrst, 'reload schema';
