-- Execute este arquivo no SQL Editor do Supabase antes de usar carga via API.
-- Ele cobre todas as tabelas usadas pelo dashboard e pelo update_data.py.
-- As tabelas ficam com RLS ativo e leitura liberada para anon/authenticated.
--
-- Se voce quiser recriar tudo do zero, remova o comentario do bloco abaixo
-- antes de executar o script. Depois rode o update_data.py para recarregar os dados.
--
-- drop table if exists public.dash_regiao_municipio_metricas cascade;
-- drop table if exists public.dash_regiao_historico cascade;
-- drop table if exists public.dash_regiao_ranking cascade;
-- drop table if exists public.dash_regioes_resumo cascade;
-- drop table if exists public.dash_municipio_indicadores cascade;
-- drop table if exists public.dash_municipio_categoria_historico cascade;
-- drop table if exists public.dash_municipios_resumo cascade;
-- drop table if exists public.regressao_rf_previsoes cascade;
-- drop table if exists public.pesos_dimensoes_pca cascade;
-- drop table if exists public.base_socioeconomico cascade;
-- drop table if exists public.base_seguranca cascade;
-- drop table if exists public.base_saude cascade;
-- drop table if exists public.base_meio_ambiente cascade;
-- drop table if exists public.base_financas cascade;
-- drop table if exists public.base_educacao cascade;
-- drop table if exists public.ranking_municipios cascade;

grant usage on schema public to anon, authenticated;

create table if not exists public.ranking_municipios (
    id_municipio bigint,
    municipio text,
    ano bigint,
    regiao_funcional text,
    corede text,
    nota_educacao double precision,
    nota_financas double precision,
    nota_meio_ambiente double precision,
    nota_saude double precision,
    nota_seguranca double precision,
    nota_socioeconomico double precision,
    nota_final double precision,
    ranking_regiao_funcional bigint
);

create table if not exists public.base_educacao (
    id_municipio bigint,
    municipio text,
    ano bigint,
    regiao_funcional text,
    corede text,
    indicador text,
    nota_indicador double precision,
    dimensao text,
    ranking_indicador bigint,
    nota_dimensao double precision,
    ranking_dimensao bigint,
    valor_original double precision,
    valor_usado_nota double precision,
    valor_imputado text
);

create table if not exists public.base_financas (
    id_municipio bigint,
    municipio text,
    ano bigint,
    regiao_funcional text,
    corede text,
    indicador text,
    nota_indicador double precision,
    dimensao text,
    ranking_indicador bigint,
    nota_dimensao double precision,
    ranking_dimensao bigint,
    valor_original double precision,
    valor_usado_nota double precision,
    valor_imputado text
);

create table if not exists public.base_meio_ambiente (
    id_municipio bigint,
    municipio text,
    ano bigint,
    regiao_funcional text,
    corede text,
    indicador text,
    nota_indicador double precision,
    dimensao text,
    ranking_indicador bigint,
    nota_dimensao double precision,
    ranking_dimensao bigint,
    valor_original double precision,
    valor_usado_nota double precision,
    valor_imputado text
);

create table if not exists public.base_saude (
    id_municipio bigint,
    municipio text,
    ano bigint,
    regiao_funcional text,
    corede text,
    indicador text,
    nota_indicador double precision,
    dimensao text,
    ranking_indicador bigint,
    nota_dimensao double precision,
    ranking_dimensao bigint,
    valor_original double precision,
    valor_usado_nota double precision,
    valor_imputado text
);

create table if not exists public.base_seguranca (
    id_municipio bigint,
    municipio text,
    ano bigint,
    regiao_funcional text,
    corede text,
    indicador text,
    nota_indicador double precision,
    dimensao text,
    ranking_indicador bigint,
    nota_dimensao double precision,
    ranking_dimensao bigint,
    valor_original double precision,
    valor_usado_nota double precision,
    valor_imputado text
);

create table if not exists public.base_socioeconomico (
    id_municipio bigint,
    municipio text,
    ano bigint,
    regiao_funcional text,
    corede text,
    indicador text,
    nota_indicador double precision,
    dimensao text,
    ranking_indicador bigint,
    nota_dimensao double precision,
    ranking_dimensao bigint,
    valor_original double precision,
    valor_usado_nota double precision,
    valor_imputado text
);

create table if not exists public.pesos_dimensoes_pca (
    dimensao text,
    indicador text,
    peso_pca double precision
);

create table if not exists public.regressao_rf_previsoes (
    id_municipio bigint,
    municipio text,
    ano bigint,
    regiao_funcional text,
    corede text,
    nota_educacao double precision,
    nota_financas double precision,
    nota_meio_ambiente double precision,
    nota_saude double precision,
    nota_seguranca double precision,
    nota_socioeconomico double precision,
    nota_oficial double precision,
    ranking_regiao_funcional bigint,
    populacao bigint,
    log_populacao double precision,
    nota_prevista double precision,
    limite_inferior_ic double precision,
    limite_superior_ic double precision,
    diferenca_oficial_prevista double precision,
    classificacao text,
    quanto_acima double precision,
    quanto_baixo double precision
);

create index if not exists idx_ranking_municipios_ano_regiao
    on public.ranking_municipios (ano, regiao_funcional);

create index if not exists idx_base_educacao_ano_regiao_municipio
    on public.base_educacao (ano, regiao_funcional, municipio);
create index if not exists idx_base_educacao_indicador
    on public.base_educacao (dimensao, indicador);

create index if not exists idx_base_financas_ano_regiao_municipio
    on public.base_financas (ano, regiao_funcional, municipio);
create index if not exists idx_base_financas_indicador
    on public.base_financas (dimensao, indicador);

create index if not exists idx_base_meio_ambiente_ano_regiao_municipio
    on public.base_meio_ambiente (ano, regiao_funcional, municipio);
create index if not exists idx_base_meio_ambiente_indicador
    on public.base_meio_ambiente (dimensao, indicador);

create index if not exists idx_base_saude_ano_regiao_municipio
    on public.base_saude (ano, regiao_funcional, municipio);
create index if not exists idx_base_saude_indicador
    on public.base_saude (dimensao, indicador);

create index if not exists idx_base_seguranca_ano_regiao_municipio
    on public.base_seguranca (ano, regiao_funcional, municipio);
create index if not exists idx_base_seguranca_indicador
    on public.base_seguranca (dimensao, indicador);

create index if not exists idx_base_socioeconomico_ano_regiao_municipio
    on public.base_socioeconomico (ano, regiao_funcional, municipio);
create index if not exists idx_base_socioeconomico_indicador
    on public.base_socioeconomico (dimensao, indicador);

create index if not exists idx_pesos_dimensoes_pca_dimensao_indicador
    on public.pesos_dimensoes_pca (dimensao, indicador);

create index if not exists idx_regressao_rf_previsoes_ano_regiao_municipio
    on public.regressao_rf_previsoes (ano, regiao_funcional, municipio);

alter table public.ranking_municipios enable row level security;
alter table public.base_educacao enable row level security;
alter table public.base_financas enable row level security;
alter table public.base_meio_ambiente enable row level security;
alter table public.base_saude enable row level security;
alter table public.base_seguranca enable row level security;
alter table public.base_socioeconomico enable row level security;
alter table public.pesos_dimensoes_pca enable row level security;
alter table public.regressao_rf_previsoes enable row level security;

drop policy if exists ranking_municipios_select_public on public.ranking_municipios;
create policy ranking_municipios_select_public
    on public.ranking_municipios for select
    to anon, authenticated
    using (true);

drop policy if exists base_educacao_select_public on public.base_educacao;
create policy base_educacao_select_public
    on public.base_educacao for select
    to anon, authenticated
    using (true);

drop policy if exists base_financas_select_public on public.base_financas;
create policy base_financas_select_public
    on public.base_financas for select
    to anon, authenticated
    using (true);

drop policy if exists base_meio_ambiente_select_public on public.base_meio_ambiente;
create policy base_meio_ambiente_select_public
    on public.base_meio_ambiente for select
    to anon, authenticated
    using (true);

drop policy if exists base_saude_select_public on public.base_saude;
create policy base_saude_select_public
    on public.base_saude for select
    to anon, authenticated
    using (true);

drop policy if exists base_seguranca_select_public on public.base_seguranca;
create policy base_seguranca_select_public
    on public.base_seguranca for select
    to anon, authenticated
    using (true);

drop policy if exists base_socioeconomico_select_public on public.base_socioeconomico;
create policy base_socioeconomico_select_public
    on public.base_socioeconomico for select
    to anon, authenticated
    using (true);

drop policy if exists pesos_dimensoes_pca_select_public on public.pesos_dimensoes_pca;
create policy pesos_dimensoes_pca_select_public
    on public.pesos_dimensoes_pca for select
    to anon, authenticated
    using (true);

drop policy if exists regressao_rf_previsoes_select_public on public.regressao_rf_previsoes;
create policy regressao_rf_previsoes_select_public
    on public.regressao_rf_previsoes for select
    to anon, authenticated
    using (true);

grant select on public.ranking_municipios to anon, authenticated;
grant select on public.base_educacao to anon, authenticated;
grant select on public.base_financas to anon, authenticated;
grant select on public.base_meio_ambiente to anon, authenticated;
grant select on public.base_saude to anon, authenticated;
grant select on public.base_seguranca to anon, authenticated;
grant select on public.base_socioeconomico to anon, authenticated;
grant select on public.pesos_dimensoes_pca to anon, authenticated;
grant select on public.regressao_rf_previsoes to anon, authenticated;

grant all on public.ranking_municipios to service_role;
grant all on public.base_educacao to service_role;
grant all on public.base_financas to service_role;
grant all on public.base_meio_ambiente to service_role;
grant all on public.base_saude to service_role;
grant all on public.base_seguranca to service_role;
grant all on public.base_socioeconomico to service_role;
grant all on public.pesos_dimensoes_pca to service_role;
grant all on public.regressao_rf_previsoes to service_role;

-- Tabelas derivadas para acelerar os visuais da pagina de municipios.
-- Elas sao carregadas pelo update_data.py depois das tabelas brutas.

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

-- Tabelas derivadas para acelerar os visuais da pagina de regioes funcionais.

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
