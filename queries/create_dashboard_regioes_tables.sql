-- Execute no SQL Editor do Supabase para criar as tabelas otimizadas
-- usadas pelos visuais da pagina de regioes funcionais.

grant usage on schema public to anon, authenticated;

create table if not exists public.dash_regioes_resumo (
    ano bigint,
    regiao_funcional text,
    regiao_codigo text,
    total_municipios bigint,
    total_coredes bigint,
    coredes_txt text,
    nota_educacao_media double precision,
    nota_financas_media double precision,
    nota_meio_ambiente_media double precision,
    nota_saude_media double precision,
    nota_seguranca_media double precision,
    nota_socioeconomico_media double precision,
    nota_final_media double precision
);

create table if not exists public.dash_regiao_ranking (
    id_municipio bigint,
    municipio text,
    ano bigint,
    ano_referencia_anterior bigint,
    regiao_funcional text,
    regiao_codigo text,
    corede text,
    ranking_regiao_funcional bigint,
    ranking_regiao_funcional_anterior bigint,
    delta_posicao_regiao bigint,
    classificacao text,
    classificacao_status text,
    nota_final double precision,
    nota_final_anterior double precision,
    delta_nota_final double precision,
    nota_educacao double precision,
    nota_financas double precision,
    nota_meio_ambiente double precision,
    nota_saude double precision,
    nota_seguranca double precision,
    nota_socioeconomico double precision,
    total_municipios_regiao bigint
);

create table if not exists public.dash_regiao_historico (
    ano bigint,
    regiao_funcional text,
    regiao_codigo text,
    nivel_recorte text,
    recorte_valor text,
    total_municipios_recorte bigint,
    nota_educacao_media double precision,
    nota_financas_media double precision,
    nota_meio_ambiente_media double precision,
    nota_saude_media double precision,
    nota_seguranca_media double precision,
    nota_socioeconomico_media double precision,
    nota_final_media double precision
);

create table if not exists public.dash_regiao_municipio_metricas (
    id_municipio bigint,
    municipio text,
    ano bigint,
    ano_referencia_anterior bigint,
    regiao_funcional text,
    regiao_codigo text,
    corede text,
    nivel_recorte text,
    recorte_valor text,
    indicador_chave text,
    indicador_label text,
    ordem bigint,
    nota_atual double precision,
    nota_anterior double precision,
    delta_nota double precision,
    posicao_recorte bigint,
    posicao_recorte_anterior bigint,
    delta_posicao bigint,
    media_recorte_indicador double precision,
    total_municipios_recorte bigint
);

create index if not exists idx_dash_regioes_resumo_ano_regiao
    on public.dash_regioes_resumo (ano, regiao_funcional);

create index if not exists idx_dash_regiao_ranking_ano_regiao_corede_rank
    on public.dash_regiao_ranking (ano, regiao_funcional, corede, ranking_regiao_funcional);
create index if not exists idx_dash_regiao_ranking_hist
    on public.dash_regiao_ranking (regiao_funcional, municipio, ano);

create index if not exists idx_dash_regiao_historico_lookup
    on public.dash_regiao_historico (regiao_funcional, nivel_recorte, recorte_valor, ano);

create index if not exists idx_dash_regiao_metricas_lookup
    on public.dash_regiao_municipio_metricas (ano, regiao_funcional, municipio, nivel_recorte, recorte_valor);
create index if not exists idx_dash_regiao_metricas_recorte_indicador
    on public.dash_regiao_municipio_metricas (ano, regiao_funcional, nivel_recorte, recorte_valor, indicador_chave);

alter table public.dash_regioes_resumo enable row level security;
alter table public.dash_regiao_ranking enable row level security;
alter table public.dash_regiao_historico enable row level security;
alter table public.dash_regiao_municipio_metricas enable row level security;

drop policy if exists dash_regioes_resumo_select_public on public.dash_regioes_resumo;
create policy dash_regioes_resumo_select_public
    on public.dash_regioes_resumo for select
    to anon, authenticated
    using (true);

drop policy if exists dash_regiao_ranking_select_public on public.dash_regiao_ranking;
create policy dash_regiao_ranking_select_public
    on public.dash_regiao_ranking for select
    to anon, authenticated
    using (true);

drop policy if exists dash_regiao_historico_select_public on public.dash_regiao_historico;
create policy dash_regiao_historico_select_public
    on public.dash_regiao_historico for select
    to anon, authenticated
    using (true);

drop policy if exists dash_regiao_municipio_metricas_select_public on public.dash_regiao_municipio_metricas;
create policy dash_regiao_municipio_metricas_select_public
    on public.dash_regiao_municipio_metricas for select
    to anon, authenticated
    using (true);

grant select on public.dash_regioes_resumo to anon, authenticated;
grant select on public.dash_regiao_ranking to anon, authenticated;
grant select on public.dash_regiao_historico to anon, authenticated;
grant select on public.dash_regiao_municipio_metricas to anon, authenticated;

grant all on public.dash_regioes_resumo to service_role;
grant all on public.dash_regiao_ranking to service_role;
grant all on public.dash_regiao_historico to service_role;
grant all on public.dash_regiao_municipio_metricas to service_role;

-- Atualiza o cache do PostgREST apos alteracoes de schema.
notify pgrst, 'reload schema';