"""
Medix AI — Sprint 3: Disruptive Architectures
==============================================
Script: treinar_modelo.py

Treina o modelo de previsão de demanda Prophet para cada combinação de
(especialidade, unidade_id) presente nos dados históricos.

O modelo treinado é serializado em disco (pickle) e reutilizado pelo
endpoint REST (endpoint_previsao.py) para realizar inferências sem
precisar retreinar a cada requisição.

Fluxo:
  1. Carrega dados históricos (CSV gerado por gerar_dados_sinteticos.py)
  2. Para cada (especialidade, unidade_id), treina um modelo Prophet
  3. Avalia o modelo com validação cruzada
  4. Salva o modelo treinado em models/<especialidade>_<unidade_id>.pkl
  5. Exibe métricas de erro (MAE, RMSE)

Uso:
  python treinar_modelo.py
  python treinar_modelo.py --dados ../../dados_sinteticos.csv --horizonte 30
"""

import argparse
import os
import pickle
import warnings
import pandas as pd
import numpy as np
from datetime import datetime

# Suprime warnings verbosos do Prophet durante o treinamento
warnings.filterwarnings("ignore")

try:
    from prophet import Prophet
    from prophet.diagnostics import cross_validation, performance_metrics
except ImportError:
    raise ImportError(
        "Prophet não encontrado. Instale com: pip install prophet"
    )


# ── Configuração do Modelo ────────────────────────────────────────────────────

# Feriados nacionais brasileiros para o Prophet considerar na sazonalidade
FERIADOS_BR = pd.DataFrame({
    "holiday": "feriado_nacional",
    "ds": pd.to_datetime([
        "2024-01-01", "2024-04-19", "2024-04-21", "2024-05-01",
        "2024-05-30", "2024-09-07", "2024-10-12", "2024-11-02",
        "2024-11-15", "2024-12-25",
        "2025-01-01", "2025-04-18", "2025-04-21", "2025-05-01",
        "2025-06-19", "2025-09-07", "2025-10-12", "2025-11-02",
        "2025-11-15", "2025-12-25",
    ]),
    "lower_window": 0,
    "upper_window": 1,
})


def criar_modelo() -> Prophet:
    """
    Instancia e configura o modelo Prophet com parâmetros otimizados
    para dados de demanda hospitalar.

    Configurações:
      - sazonalidade semanal: modo multiplicativo (intensidade varia)
      - sazonalidade anual: modo multiplicativo
      - feriados brasileiros incluídos
      - intervalo de confiança: 95%
    """
    modelo = Prophet(
        seasonality_mode="multiplicative",   # melhor para dados com variância crescente
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,             # dados diários agregados, não horários
        holidays=FERIADOS_BR,
        interval_width=0.95,                 # banda de confiança de 95%
        changepoint_prior_scale=0.05,        # regularização da tendência (evita overfitting)
    )

    # Adiciona sazonalidade mensal manualmente (Prophet não a inclui por padrão)
    modelo.add_seasonality(
        name="monthly",
        period=30.5,
        fourier_order=5,
        mode="multiplicative",
    )

    return modelo


# ── Treinamento ───────────────────────────────────────────────────────────────

def treinar(df_grupo: pd.DataFrame) -> Prophet:
    """
    Treina o Prophet em um subconjunto de dados (uma especialidade/unidade).

    O Prophet espera um DataFrame com colunas obrigatórias:
      - 'ds' : datas (datetime ou string YYYY-MM-DD)
      - 'y'  : valores numéricos a prever
    """
    df_treino = df_grupo[["ds", "y"]].copy()
    df_treino["ds"] = pd.to_datetime(df_treino["ds"])
    df_treino = df_treino.sort_values("ds").reset_index(drop=True)

    modelo = criar_modelo()
    modelo.fit(df_treino)

    return modelo


def avaliar_modelo(
    modelo: Prophet,
    df_grupo: pd.DataFrame,
    horizonte: int = 30,
) -> dict:
    """
    Avalia o modelo com validação cruzada temporal.

    Parâmetros:
      horizonte : número de dias futuros para avaliar (deve ser < 50% do histórico)

    Retorna dicionário com métricas MAE e RMSE.
    """
    df_treino = df_grupo[["ds", "y"]].copy()
    df_treino["ds"] = pd.to_datetime(df_treino["ds"])
    n_dias = len(df_treino)

    # Validação cruzada com janela inicial de 60% do histórico
    initial_days = max(60, int(n_dias * 0.6))

    try:
        df_cv = cross_validation(
            modelo,
            initial=f"{initial_days} days",
            period=f"{horizonte // 2} days",
            horizon=f"{horizonte} days",
            disable_tqdm=True,
        )
        metricas = performance_metrics(df_cv, rolling_window=1)
        return {
            "mae":  round(float(metricas["mae"].mean()), 2),
            "rmse": round(float(metricas["rmse"].mean()), 2),
            "mape": round(float(metricas["mape"].mean() * 100), 1),
        }
    except Exception:
        # Histórico insuficiente para validação cruzada — retorna N/A
        return {"mae": None, "rmse": None, "mape": None}


# ── Persistência ──────────────────────────────────────────────────────────────

def salvar_modelo(modelo: Prophet, especialidade: str, unidade_id: int, diretorio: str) -> str:
    """Serializa o modelo treinado em arquivo pickle."""
    os.makedirs(diretorio, exist_ok=True)
    nome = f"{especialidade.lower().replace(' ', '_')}_{unidade_id}.pkl"
    caminho = os.path.join(diretorio, nome)
    with open(caminho, "wb") as f:
        pickle.dump(modelo, f)
    return caminho


def carregar_modelo(especialidade: str, unidade_id: int, diretorio: str = "models") -> Prophet:
    """
    Carrega um modelo previamente treinado do disco.
    Usado pelo endpoint_previsao.py para evitar retreinamento.
    """
    nome = f"{especialidade.lower().replace(' ', '_')}_{unidade_id}.pkl"
    caminho = os.path.join(diretorio, nome)
    if not os.path.exists(caminho):
        raise FileNotFoundError(
            f"Modelo não encontrado: {caminho}\n"
            f"Execute treinar_modelo.py antes de iniciar o endpoint."
        )
    with open(caminho, "rb") as f:
        return pickle.load(f)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Medix AI — Treinamento do modelo Prophet de previsão de demanda."
    )
    parser.add_argument("--dados",      type=str, default="dados_sinteticos.csv", help="Caminho para o CSV de dados históricos")
    parser.add_argument("--horizonte",  type=int, default=30,                     help="Horizonte de previsão em dias para avaliação (padrão: 30)")
    parser.add_argument("--modelos",    type=str, default="models",               help="Diretório para salvar os modelos (padrão: ./models)")
    args = parser.parse_args()

    print("\n Medix AI — Treinamento do Modelo Prophet")
    print("=" * 55)

    # ── Carregamento dos dados ─────────────────────────────────
    if not os.path.exists(args.dados):
        print(f"\n  ERRO: arquivo '{args.dados}' não encontrado.")
        print("  Execute primeiro: python src/data/gerar_dados_sinteticos.py\n")
        return

    df = pd.read_csv(args.dados)
    print(f"\n  Dados carregados: {len(df)} registros")
    print(f"  Período: {df['ds'].min()} → {df['ds'].max()}")

    grupos = df.groupby(["especialidade", "unidade_id"])
    print(f"  Combinações a treinar: {len(grupos)}\n")

    resultados = []

    for (especialidade, unidade_id), df_grupo in grupos:
        print(f"  Treinando: {especialidade} — Unidade {unidade_id}...", end=" ", flush=True)
        inicio = datetime.now()

        modelo   = treinar(df_grupo)
        metricas = avaliar_modelo(modelo, df_grupo, horizonte=args.horizonte)
        caminho  = salvar_modelo(modelo, especialidade, int(unidade_id), args.modelos)

        duracao = (datetime.now() - inicio).total_seconds()
        print(f"OK ({duracao:.1f}s)")

        mae_str  = f"{metricas['mae']:.2f}"  if metricas["mae"]  else "N/A"
        rmse_str = f"{metricas['rmse']:.2f}" if metricas["rmse"] else "N/A"
        mape_str = f"{metricas['mape']:.1f}%" if metricas["mape"] else "N/A"

        resultados.append({
            "especialidade": especialidade,
            "unidade_id":    unidade_id,
            "registros":     len(df_grupo),
            "mae":           mae_str,
            "rmse":          rmse_str,
            "mape":          mape_str,
            "modelo":        caminho,
        })

    # ── Resumo final ───────────────────────────────────────────
    print("\n── Resultado do Treinamento ──────────────────────────────")
    df_res = pd.DataFrame(resultados)
    print(df_res[["especialidade", "unidade_id", "registros", "mae", "rmse", "mape"]].to_string(index=False))
    print("\n  Legenda:")
    print("  MAE  = Erro Absoluto Médio (atendimentos/dia)")
    print("  RMSE = Raiz do Erro Quadrático Médio")
    print("  MAPE = Erro Percentual Absoluto Médio")
    print(f"\n  Modelos salvos em: {os.path.abspath(args.modelos)}/")
    print("\n  Próximo passo:")
    print("  → Execute endpoint_previsao.py para subir o servidor REST\n")


if __name__ == "__main__":
    main()
