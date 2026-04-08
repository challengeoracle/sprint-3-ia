"""
Medix AI — Sprint 3: Disruptive Architectures
==============================================
Script: endpoint_previsao.py

Servidor REST (Flask) que expõe o modelo Prophet treinado como um
endpoint HTTP, simulando o comportamento do OCI Data Science.

Este endpoint é chamado pelo Oracle Database via UTL_HTTP, dentro da
stored procedure SP_EXPORTAR_SERIE_TEMPORAL, conforme a arquitetura
de integração definida na Sprint 3.

Endpoints disponíveis:
  POST /prever        → realiza a previsão de demanda
  GET  /health        → verifica se o servidor está operacional
  GET  /modelos       → lista os modelos disponíveis

Uso local (MVP):
  python endpoint_previsao.py
  # Servidor disponível em: http://localhost:5000

Uso em produção (OCI):
  Substituir pelo deployment no OCI Data Science Model Deployment,
  que expõe automaticamente o modelo como endpoint HTTPS gerenciado.
"""

import os
import pickle
import json
import logging
from datetime import datetime

import pandas as pd
import numpy as np

try:
    from flask import Flask, request, jsonify
except ImportError:
    raise ImportError("Flask não encontrado. Instale com: pip install flask")

try:
    from prophet import Prophet
except ImportError:
    raise ImportError("Prophet não encontrado. Instale com: pip install prophet")


# ── Configuração ──────────────────────────────────────────────────────────────

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Diretório onde os modelos treinados (.pkl) estão salvos
MODELS_DIR = os.environ.get("MODELS_DIR", "models")

# Limite padrão de capacidade diária por especialidade (atendimentos/dia)
# Em produção, esses valores viriam da tabela TB_CAPACIDADE_UNIDADE no Oracle DB
CAPACIDADE_PADRAO = {
    "cardiologia":   25,
    "pediatria":     35,
    "ortopedia":     20,
    "clínica geral": 50,
    "ginecologia":   28,
}

# Cache de modelos em memória (evita recarregar pickle a cada requisição)
_cache_modelos: dict = {}


# ── Funções auxiliares ────────────────────────────────────────────────────────

def carregar_modelo(especialidade: str, unidade_id: int) -> Prophet:
    """
    Carrega o modelo treinado do disco para o cache em memória.
    Na primeira chamada, lê o arquivo .pkl; nas seguintes, usa o cache.
    """
    chave = f"{especialidade.lower().replace(' ', '_')}_{unidade_id}"

    if chave not in _cache_modelos:
        caminho = os.path.join(MODELS_DIR, f"{chave}.pkl")
        if not os.path.exists(caminho):
            raise FileNotFoundError(
                f"Modelo '{chave}.pkl' não encontrado em '{MODELS_DIR}/'. "
                "Execute treinar_modelo.py primeiro."
            )
        with open(caminho, "rb") as f:
            _cache_modelos[chave] = pickle.load(f)
        log.info(f"Modelo carregado: {caminho}")

    return _cache_modelos[chave]


def gerar_previsao(
    modelo: Prophet,
    dados_historicos: list[dict],
    dias: int,
    capacidade: int,
) -> dict:
    """
    Executa a previsão e formata a resposta no padrão esperado pelo APEX.

    Parâmetros:
        modelo            : modelo Prophet treinado
        dados_historicos  : lista de dicts {"ds": "YYYY-MM-DD", "y": N}
        dias              : número de dias futuros a prever
        capacidade        : limite diário configurado para a especialidade

    Retorna:
        dict com 'previsao' (lista), 'alerta' (bool) e 'motivo' (str)
    """
    # Monta DataFrame histórico para o Prophet
    df_hist = pd.DataFrame(dados_historicos)[["ds", "y"]]
    df_hist["ds"] = pd.to_datetime(df_hist["ds"])
    df_hist = df_hist.sort_values("ds").reset_index(drop=True)

    # Cria datas futuras e executa a previsão
    futuro   = modelo.make_future_dataframe(periods=dias, freq="D", include_history=False)
    forecast = modelo.predict(futuro)

    # Filtra apenas as datas futuras e formata
    previsao = []
    alerta   = False
    dia_pico = None
    val_pico = 0

    for _, row in forecast.iterrows():
        yhat       = max(0, round(float(row["yhat"])))
        yhat_lower = max(0, round(float(row["yhat_lower"])))
        yhat_upper = max(0, round(float(row["yhat_upper"])))

        previsao.append({
            "ds":         row["ds"].strftime("%Y-%m-%d"),
            "yhat":       yhat,
            "yhat_lower": yhat_lower,
            "yhat_upper": yhat_upper,
            "excede_capacidade": yhat > capacidade,
        })

        # Detecta o pico previsto
        if yhat > val_pico:
            val_pico = yhat
            dia_pico = row["ds"].strftime("%Y-%m-%d")

        # Alerta se qualquer dia previsto superar a capacidade
        if yhat > capacidade:
            alerta = True

    motivo = (
        f"Previsão de {val_pico} atendimentos em {dia_pico} excede "
        f"o limite configurado de {capacidade} para esta especialidade. "
        f"Recomendado reforço de escala."
        if alerta else
        "Demanda prevista dentro da capacidade configurada para todos os dias."
    )

    return {
        "previsao":       previsao,
        "total_dias":     dias,
        "alerta":         alerta,
        "motivo":         motivo,
        "gerado_em":      datetime.utcnow().isoformat() + "Z",
        "modelo":         "Prophet",
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    """
    Verifica se o servidor está operacional.
    Usado pelo Oracle APEX para validar a disponibilidade do endpoint.
    """
    return jsonify({
        "status":     "ok",
        "timestamp":  datetime.utcnow().isoformat() + "Z",
        "modelos_dir": MODELS_DIR,
    }), 200


@app.route("/modelos", methods=["GET"])
def listar_modelos():
    """Lista os modelos treinados disponíveis no diretório de modelos."""
    if not os.path.exists(MODELS_DIR):
        return jsonify({"modelos": [], "mensagem": "Nenhum modelo treinado encontrado."}), 200

    arquivos = [f.replace(".pkl", "") for f in os.listdir(MODELS_DIR) if f.endswith(".pkl")]
    return jsonify({"modelos": sorted(arquivos), "total": len(arquivos)}), 200


@app.route("/prever", methods=["POST"])
def prever():
    """
    Endpoint principal de previsão de demanda.

    Recebe (JSON):
        especialidade     : str  — especialidade médica (ex: "Cardiologia")
        unidade_id        : int  — ID da unidade de saúde
        dias              : int  — horizonte de previsão (7, 15 ou 30)
        dados_historicos  : list — array de {"ds": "YYYY-MM-DD", "y": N}
        capacidade_diaria : int  — (opcional) limite diário da unidade

    Retorna (JSON):
        previsao      : list  — previsão diária com intervalos de confiança
        alerta        : bool  — true se algum dia exceder a capacidade
        motivo        : str   — descrição do alerta ou confirmação de normalidade
        gerado_em     : str   — timestamp UTC da geração
    """
    # ── Validação da requisição ────────────────────────────────
    if not request.is_json:
        return jsonify({"erro": "Content-Type deve ser application/json"}), 400

    dados = request.get_json()

    campos_obrigatorios = ["especialidade", "unidade_id", "dados_historicos", "dias"]
    for campo in campos_obrigatorios:
        if campo not in dados:
            return jsonify({"erro": f"Campo obrigatório ausente: '{campo}'"}), 400

    especialidade    = str(dados["especialidade"])
    unidade_id       = int(dados["unidade_id"])
    dias             = int(dados["dias"])
    dados_historicos = dados["dados_historicos"]
    capacidade       = int(dados.get(
        "capacidade_diaria",
        CAPACIDADE_PADRAO.get(especialidade.lower(), 30)
    ))

    if dias not in [7, 15, 30, 60, 90]:
        return jsonify({"erro": "Campo 'dias' deve ser 7, 15, 30, 60 ou 90."}), 400

    if len(dados_historicos) < 30:
        return jsonify({
            "erro": "Histórico insuficiente. Mínimo de 30 registros diários necessários.",
            "recebidos": len(dados_historicos),
        }), 400

    # ── Carregamento e execução do modelo ─────────────────────
    log.info(f"Previsão solicitada: {especialidade} | unidade {unidade_id} | {dias} dias")

    try:
        modelo    = carregar_modelo(especialidade, unidade_id)
        resultado = gerar_previsao(modelo, dados_historicos, dias, capacidade)

        log.info(
            f"Previsão gerada: {len(resultado['previsao'])} dias | "
            f"alerta={'SIM' if resultado['alerta'] else 'NÃO'}"
        )
        return jsonify(resultado), 200

    except FileNotFoundError as e:
        log.warning(str(e))
        return jsonify({"erro": str(e)}), 404

    except Exception as e:
        log.error(f"Erro interno: {e}", exc_info=True)
        return jsonify({"erro": "Erro interno no processamento do modelo."}), 500


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    print("\n Medix AI — Endpoint REST de Previsão de Demanda")
    print("=" * 50)
    print(f"  Servidor : http://localhost:{porta}")
    print(f"  Modelos  : {os.path.abspath(MODELS_DIR)}/")
    print(f"  Debug    : {'ativado' if debug else 'desativado'}")
    print("\n  Endpoints disponíveis:")
    print("  GET  /health   → verificação de disponibilidade")
    print("  GET  /modelos  → lista modelos treinados")
    print("  POST /prever   → executa a previsão")
    print("\n  Exemplo de requisição:")
    print('  curl -X POST http://localhost:5000/prever \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"especialidade":"Cardiologia","unidade_id":1,"dias":30,"dados_historicos":[...]}\'\n')

    app.run(host="0.0.0.0", port=porta, debug=debug)
