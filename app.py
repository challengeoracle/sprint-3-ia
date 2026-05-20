import logging
from flask import Flask, jsonify, request
from flask_cors import CORS
from prophet import Prophet
import pandas as pd
import numpy as np

# tira os logs do motor do prophet no terminal
logging.getLogger('cmdstanpy').setLevel(logging.ERROR)

app = Flask(__name__)
# libera o cors pro apex nao bloquear a requisicao
CORS(app) 

def gera_historico():
    # cria 3 meses de dados terminando hoje
    hoje = pd.Timestamp.today()
    datas = pd.date_range(end=hoje, periods=90, freq="D")
    
    np.random.seed(42) 
    base = 25
    
    # joga o movimento pra baixo no final de semana
    sazonalidade = np.where(datas.weekday < 5, 1.2, 0.4)
    ruido = np.random.normal(0, 3, 90)
    
    y = np.array(base * sazonalidade + ruido)
    y = y.clip(min=0).round().astype(int)
    
    return pd.DataFrame({'ds': datas, 'y': y})

# rota de teste pra ver se esta rodando
@app.route('/', methods=['GET'])
def home():
    return jsonify({"api": "medix ia online", "status": "ok"})

@app.route('/api/previsao', methods=['POST', 'GET'])
def previsao():
    try:
        df = gera_historico()
        
        # configura o modelo desligando sazonalidades que nao fazem sentido pra 3 meses
        m = Prophet(yearly_seasonality=False, daily_seasonality=False)
        m.fit(df)
        
        # preve 7 dias pra frente
        futuro = m.make_future_dataframe(periods=7)
        forecast = m.predict(futuro)
        
        # pega somente a previsao futura e as colunas pro apex
        res = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(7)
        
        res['ds'] = res['ds'].dt.strftime('%Y-%m-%d')
        
        # arredonda tudo pra int pq nao existe meio paciente
        for col in ['yhat', 'yhat_lower', 'yhat_upper']:
            res[col] = res[col].round().astype(int)
            
        return jsonify(res.to_dict(orient='records')), 200

    except Exception as e:
        print(f"erro interno: {e}")
        return jsonify({"erro": str(e)}), 500

if __name__ == '__main__':
    # host 0.0.0.0 expoe pra rede
    app.run(host='0.0.0.0', port=5000, debug=True)