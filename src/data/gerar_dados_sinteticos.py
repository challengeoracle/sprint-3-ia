"""
Medix AI — Sprint 3: Disruptive Architectures
==============================================
Script: gerar_dados_sinteticos.py

Gera um histórico de agendamentos médicos sintético e realista para
validar o pipeline completo do modelo de previsão de demanda.

Os dados simulam padrões reais de uma unidade de saúde:
  - Maior demanda em dias úteis (segunda a sexta)
  - Queda nos fins de semana
  - Sazonalidade mensal (variação suave ao longo do ano)
  - Ruído gaussiano para simular imprevisibilidade natural

Uso:
  python gerar_dados_sinteticos.py
  python gerar_dados_sinteticos.py --dias 365 --especialidade Pediatria --unidade 2

Saída:
  dados_sinteticos.csv  — arquivo pronto para importar no Oracle DB
  dados_modelo.json     — formato de entrada esperado pelo modelo Prophet
"""

import argparse
import json
import os
import pandas as pd
import numpy as np
from datetime import datetime


# ── Configurações padrão ──────────────────────────────────────────────────────

ESPECIALIDADES = [
    "Cardiologia",
    "Pediatria",
    "Ortopedia",
    "Clínica Geral",
    "Ginecologia",
]

FERIADOS_NACIONAIS = [
    "2025-01-01",  # Ano Novo
    "2025-04-18",  # Sexta-feira Santa
    "2025-04-21",  # Tiradentes
    "2025-05-01",  # Dia do Trabalho
    "2025-06-19",  # Corpus Christi
    "2025-09-07",  # Independência
    "2025-10-12",  # Nossa Senhora Aparecida
    "2025-11-02",  # Finados
    "2025-11-15",  # Proclamação da República
    "2025-12-25",  # Natal
]


# ── Função principal de geração ───────────────────────────────────────────────

def gerar_dados_sinteticos(
    dias: int = 180,
    especialidade: str = "Cardiologia",
    unidade_id: int = 1,
    data_inicio: str = "2024-10-01",
    base_diaria: int = 20,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Gera um DataFrame com histórico diário de agendamentos simulados.

    Parâmetros:
        dias          : número de dias de histórico a gerar
        especialidade : especialidade médica
        unidade_id    : ID da unidade de saúde (FK para TB_UNIDADE)
        data_inicio   : data de início da série (formato YYYY-MM-DD)
        base_diaria   : média de atendimentos por dia útil
        seed          : semente para reprodutibilidade

    Retorna:
        DataFrame com colunas: ds, y, especialidade, unidade_id, status
    """
    np.random.seed(seed)

    datas = pd.date_range(start=data_inicio, periods=dias, freq="D")

    # Fator de sazonalidade semanal: dias úteis têm 1.2x, fins de semana 0.4x
    fator_semana = np.where(datas.weekday < 5, 1.2, 0.4)

    # Fator de sazonalidade anual: curva senoidal suave (pico no inverno ~julho)
    fator_anual = 1.0 + 0.15 * np.sin(2 * np.pi * (datas.dayofyear - 172) / 365)

    # Fator de feriados: redução de 70% em feriados nacionais
    feriados = pd.to_datetime(FERIADOS_NACIONAIS)
    fator_feriado = np.where(datas.isin(feriados), 0.3, 1.0)

    # Ruído gaussiano para variabilidade natural
    ruido = np.random.normal(loc=0, scale=2.5, size=dias)

    # Composição final
    valores = np.array(base_diaria * fator_semana * fator_anual * fator_feriado + ruido)
    valores = valores.clip(min=0).round().astype(int)

    df = pd.DataFrame({
        "ds":            datas.strftime("%Y-%m-%d"),
        "y":             valores,
        "especialidade": especialidade,
        "unidade_id":    unidade_id,
        "status":        "Realizado",
    })

    return df


def gerar_todas_especialidades(
    dias: int = 180,
    unidade_id: int = 1,
    data_inicio: str = "2024-10-01",
) -> pd.DataFrame:
    """
    Gera dados para todas as especialidades padrão com volumes diferentes.
    """
    bases = {
        "Cardiologia":   18,
        "Pediatria":     25,
        "Ortopedia":     15,
        "Clínica Geral": 35,
        "Ginecologia":   20,
    }
    frames = []
    for i, (esp, base) in enumerate(bases.items()):
        df = gerar_dados_sinteticos(
            dias=dias,
            especialidade=esp,
            unidade_id=unidade_id,
            data_inicio=data_inicio,
            base_diaria=base,
            seed=42 + i,
        )
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


# ── Exportação ────────────────────────────────────────────────────────────────

def exportar_csv(df: pd.DataFrame, caminho: str = "dados_sinteticos.csv") -> None:
    """Salva em CSV para importação no Oracle Database."""
    df.to_csv(caminho, index=False, encoding="utf-8")
    print(f"  ✔ CSV salvo em: {caminho} ({len(df)} registros)")


def exportar_json(df: pd.DataFrame, caminho: str = "dados_modelo.json") -> None:
    """
    Salva no formato JSON esperado pelo endpoint do modelo Prophet.
    Agrupa por data somando todas as especialidades.
    """
    registros = df[["ds", "y", "especialidade", "unidade_id"]].to_dict(orient="records")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(registros, f, ensure_ascii=False, indent=2)
    print(f"  ✔ JSON salvo em: {caminho} ({len(registros)} registros)")


def imprimir_resumo(df: pd.DataFrame) -> None:
    """Exibe um resumo estatístico dos dados gerados."""
    print("\n── Resumo dos Dados Gerados ─────────────────────────────")
    print(f"  Período    : {df['ds'].min()} → {df['ds'].max()}")
    print(f"  Registros  : {len(df)}")
    print(f"  Unidade ID : {df['unidade_id'].unique().tolist()}")
    print("\n  Estatísticas por especialidade:")
    resumo = (
        df.groupby("especialidade")["y"]
        .agg(["mean", "min", "max", "sum"])
        .rename(columns={"mean": "Média/dia", "min": "Mín", "max": "Máx", "sum": "Total"})
    )
    resumo["Média/dia"] = resumo["Média/dia"].round(1)
    print(resumo.to_string())
    print("─────────────────────────────────────────────────────────\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Medix AI — Gerador de dados sintéticos para treinamento do modelo."
    )
    parser.add_argument("--dias",          type=int,   default=180,           help="Número de dias de histórico (padrão: 180)")
    parser.add_argument("--especialidade", type=str,   default=None,          help="Especialidade específica (padrão: todas)")
    parser.add_argument("--unidade",       type=int,   default=1,             help="ID da unidade de saúde (padrão: 1)")
    parser.add_argument("--inicio",        type=str,   default="2024-10-01",  help="Data de início YYYY-MM-DD (padrão: 2024-10-01)")
    parser.add_argument("--saida",         type=str,   default=".",           help="Diretório de saída (padrão: .)")
    args = parser.parse_args()

    os.makedirs(args.saida, exist_ok=True)

    print("\n Medix AI — Geração de Dados Sintéticos")
    print("=" * 50)

    if args.especialidade:
        print(f"  Modo: especialidade única ({args.especialidade})")
        df = gerar_dados_sinteticos(
            dias=args.dias,
            especialidade=args.especialidade,
            unidade_id=args.unidade,
            data_inicio=args.inicio,
        )
    else:
        print(f"  Modo: todas as especialidades")
        df = gerar_todas_especialidades(
            dias=args.dias,
            unidade_id=args.unidade,
            data_inicio=args.inicio,
        )

    imprimir_resumo(df)

    exportar_csv(df,  os.path.join(args.saida, "dados_sinteticos.csv"))
    exportar_json(df, os.path.join(args.saida, "dados_modelo.json"))

    print("\n  Dados prontos. Próximo passo:")
    print("  → Importe dados_sinteticos.csv na tabela TB_AGENDAMENTO do Oracle DB")
    print("  → Execute treinar_modelo.py para treinar o Prophet\n")


if __name__ == "__main__":
    main()