# teste.py — coloque na pasta sprint-3-ia/
import json
import urllib.request

# Carrega os dados históricos gerados
with open("src/data/dados_modelo.json") as f:
    todos = json.load(f)

# Filtra só Cardiologia, unidade 1
historico = [r for r in todos if r["especialidade"] == "Cardiologia" and r["unidade_id"] == 1]

payload = {
    "especialidade": "Cardiologia",
    "unidade_id": 1,
    "dias": 30,
    "dados_historicos": historico
}

req = urllib.request.Request(
    "http://localhost:5000/prever",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST"
)

with urllib.request.urlopen(req) as resp:
    resultado = json.loads(resp.read())

print("Alerta:", resultado["alerta"])
print("Motivo:", resultado["motivo"])
print("\nPrimeiros 5 dias previstos:")
for dia in resultado["previsao"][:5]:
    print(f"  {dia['ds']} → {dia['yhat']} atendimentos (entre {dia['yhat_lower']} e {dia['yhat_upper']})")