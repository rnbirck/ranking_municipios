import re
import unicodedata


def _normalize_indicator_key(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", ascii_value.lower())).strip("_")


INDICATOR_METADATA = {
    # Educação
    "adequacao_formacao_docente": {
        "methodology": "Considera a proporção de docentes do ensino fundamental com formação adequada à área em que atuam."
    },
    "saeb_ensino_fundamental": {
        "methodology": "Sintetiza o desempenho em Português e Matemática no SAEB, considerando os anos iniciais e finais do ensino fundamental."
    },
    "taxa_cobertura_creche": {
        "methodology": "Expressa a cobertura de matrículas em creche na rede municipal."
    },
    "taxa_distorcao_fundamental": {
        "methodology": "Indica a proporção de estudantes do ensino fundamental com idade acima da esperada para a série."
    },
    "qt_acesso_infor": {
        "methodology": "Considera a disponibilidade de recursos de acesso à informação nas escolas, como infraestrutura associada à conectividade e ao uso de tecnologias."
    },
    "acesso_informacao": {
        "methodology": "Considera a disponibilidade de recursos de acesso à informação nas escolas, como infraestrutura associada à conectividade e ao uso de tecnologias."
    },

    # Finanças
    "exec_orc_corrente": {
        "methodology": "Relaciona as despesas correntes às receitas correntes, indicando o nível de comprometimento do orçamento."
    },
    "autonomia_fiscal": {
        "methodology": "Avalia a capacidade do município de financiar suas atividades com receitas próprias."
    },
    "endividamento": {
        "methodology": "Expressa o peso da dívida consolidada líquida sobre a receita corrente líquida."
    },
    "despesas_pessoal": {
        "methodology": "Indica a participação das despesas com pessoal na receita corrente líquida do município."
    },
    "investimento": {
        "methodology": "Representa a parcela da receita corrente líquida destinada a investimentos e despesas de capital."
    },
    "disponibilidade_caixa": {
        "methodology": "Compara a disponibilidade líquida de caixa com a receita corrente líquida."
    },
    "geracao_de_caixa": {
        "methodology": "Mostra a variação da disponibilidade líquida de caixa em relação ao ano anterior."
    },
    "restos_a_pagar": {
        "methodology": "Relaciona o saldo de restos a pagar à receita corrente líquida."
    },

    # Meio ambiente
    "desmatamento_por_area": {
        "methodology": "Expressa a parcela da área municipal afetada pelo desmatamento."
    },
    "emissao_gases_per_capita": {
        "methodology": "Relaciona as emissões de gases de efeito estufa ao tamanho da população."
    },
    "incidencia_coliformes": {
        "methodology": "Indica a presença de coliformes nas análises da água distribuída."
    },
    "indice_perdas_distribuicao": {
        "methodology": "Representa a parcela da água produzida que se perde durante a distribuição."
    },
    "prop_atendimento_agua": {
        "methodology": "Expressa a proporção da população atendida pelo abastecimento de água."
    },
    "prop_coleta_residuos": {
        "methodology": "Indica a proporção da população atendida pela coleta de resíduos."
    },

    # Saúde
    "obitos_causas_evitaveis_mil_habitantes": {
        "methodology": "Relaciona os óbitos por causas evitáveis ao tamanho da população."
    },
    "proporcao_consultas_pre_natal": {
        "methodology": "Indica a proporção de nascidos vivos cujas mães realizaram sete ou mais consultas de pré-natal."
    },
    "proporcao_gravidez_adolescencia": {
        "methodology": "Expressa a participação de mães adolescentes no total de nascidos vivos do município."
    },
    "medicos_por_mil_habitantes": {
        "methodology": "Relaciona o número de médicos disponíveis ao tamanho da população."
    },
    "cobertura_aps": {
        "methodology": "Representa a cobertura potencial da Atenção Primária à Saúde no município."
    },
    "cobertura_acs": {
        "methodology": "Indica a cobertura estimada dos agentes comunitários de saúde."
    },
    "cobertura_vacinal_penta_polio_media": {
        "methodology": "Sintetiza a cobertura das vacinas pentavalente e poliomielite."
    },

    # Segurança
    "delitos_com_armas_por_10mil_hab": {
        "methodology": "Relaciona as ocorrências de delitos com armas e munições ao tamanho da população."
    },
    "furtos_por_10mil_hab": {
        "methodology": "Expressa as ocorrências de furto em relação ao tamanho da população."
    },
    "homicidio_doloso_por_10mil_hab": {
        "methodology": "Indica a incidência de homicídios dolosos em relação ao tamanho da população."
    },
    "roubos_por_10mil_hab": {
        "methodology": "Relaciona as ocorrências de roubo ao tamanho da população."
    },
    "roubos_furtos_veiculos_por_10mil_veiculos": {
        "methodology": "Compara os roubos e furtos de veículos com o tamanho da frota municipal."
    },
    "estupro_por_10mil_mulheres": {
        "methodology": "Relaciona as ocorrências de estupro à população feminina do município."
    },
    "ameaca_por_10mil_mulheres": {
        "methodology": "Relaciona as ocorrências de ameaça à população feminina do município."
    },

    # Socioeconômico
    "pib_per_capita": {
        "methodology": "Relaciona o valor do PIB municipal ao número de habitantes."
    },
    "mulheres_empregadas_ensino_medio_ou_mais_por_1000_mulheres": {
        "methodology": "Expressa os vínculos formais de mulheres com ensino médio ou mais em relação à população feminina."
    },
    "renda_media": {
        "methodology": "Representa a remuneração média dos vínculos formais no mês de dezembro."
    },
    "vinculos_per_capita": {
        "methodology": "Relaciona o número de vínculos formais ativos à população do município."
    },
    "formalidade_mercado_trabalho": {
        "methodology": "Compara os vínculos formais ativos com a população de 15 a 69 anos."
    },
    "geracao_emprego_per_capita": {
        "methodology": "Relaciona o saldo de empregos formais gerados ao tamanho da população."
    },
    "vulnerabilidade_social": {
        "methodology": "Indica a proporção da população registrada no Cadastro Único."
    },
    "proporcao_pessoas_baixa_renda": {
        "methodology": "Expressa a proporção de pessoas em famílias de baixa renda no município."
    },
}


def get_indicator_methodology(indicator):
    if not indicator:
        return None
    key = _normalize_indicator_key(indicator)
    metadata = INDICATOR_METADATA.get(key, {})
    return metadata.get("methodology")
