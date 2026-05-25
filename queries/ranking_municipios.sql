SELECT
    id_municipio,
    municipio,
    ano,
    regiao_funcional,
    corede,
    nota_educacao,
    nota_financas,
    nota_meio_ambiente,
    nota_saude,
    nota_seguranca,
    nota_socioeconomico,
    nota_final,
    ranking_regiao_funcional
FROM public.ranking_municipios
WHERE municipio IS NOT NULL
ORDER BY ano DESC, regiao_funcional, ranking_regiao_funcional, municipio;
