-- Execute no SQL Editor do Supabase para criar a materialized view de
-- medianas regionais usadas nos graficos da pagina /municipios.
--
-- A materialized view evita recalcular medianas no callback com todos os
-- municipios da categoria. Depois de atualizar public.dash_municipio_indicadores,
-- rode o refresh ao final deste arquivo para atualizar as medianas.

create materialized view if not exists public.mv_municipio_indicador_mediana_regiao as
with municipio_indicador_unico as (
    select
        ano,
        regiao_funcional,
        categoria,
        indicador,
        id_municipio,
        municipio,
        avg(nota_indicador) filter (where nota_indicador is not null) as nota_indicador,
        avg(valor_original) filter (where valor_original is not null) as valor_original
    from public.dash_municipio_indicadores
    where nota_indicador is not null
       or valor_original is not null
    group by
        ano,
        regiao_funcional,
        categoria,
        indicador,
        id_municipio,
        municipio
),
medianas as (
    select
        ano,
        regiao_funcional,
        categoria,
        indicador,
        case
            when count(*) filter (where nota_indicador is not null) > 1
            then percentile_cont(0.5) within group (order by nota_indicador)
                 filter (where nota_indicador is not null)
            else null
        end as mediana_nota_indicador_regiao,
        case
            when count(*) filter (where valor_original is not null) > 1
            then percentile_cont(0.5) within group (order by valor_original)
                 filter (where valor_original is not null)
            else null
        end as mediana_valor_original_regiao,
        count(*) filter (
            where nota_indicador is not null
               or valor_original is not null
        ) as total_municipios_mediana
    from municipio_indicador_unico
    group by
        ano,
        regiao_funcional,
        categoria,
        indicador
)
select
    ano,
    regiao_funcional,
    categoria,
    indicador,
    mediana_nota_indicador_regiao,
    mediana_valor_original_regiao,
    total_municipios_mediana
from medianas
where total_municipios_mediana > 1;

create index if not exists idx_mv_municipio_indicador_mediana_regiao_lookup
    on public.mv_municipio_indicador_mediana_regiao
    (ano, regiao_funcional, categoria, indicador);

grant select on public.mv_municipio_indicador_mediana_regiao to anon, authenticated;
grant all on public.mv_municipio_indicador_mediana_regiao to service_role;

-- Atualiza os dados materializados.
refresh materialized view public.mv_municipio_indicador_mediana_regiao;

-- Atualiza o cache do PostgREST apos a criacao da view.
notify pgrst, 'reload schema';

-- Para atualizar as medianas depois de novas cargas de dados, rode:
-- refresh materialized view public.mv_municipio_indicador_mediana_regiao;
