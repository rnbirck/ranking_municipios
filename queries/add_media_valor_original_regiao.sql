-- Execute no SQL Editor do Supabase para atualizar uma base ja existente.
-- Depois rode update_data.py para preencher a nova coluna.

alter table public.dash_municipio_indicadores
    add column if not exists media_valor_original_regiao double precision;

notify pgrst, 'reload schema';
