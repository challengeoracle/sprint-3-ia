# Evidências de Testes — Sprint 4

## Ambiente

- Python 3.12
- Bibliotecas: `flask`, `flask-cors`, `prophet`, `pandas`, `numpy`
- Servidor rodando em `http://localhost:5000`
- Túnel exposto via Ngrok para o Oracle APEX

---

## Teste 1 — API no ar

```
GET http://localhost:5000/
```

Resposta:

```json
{
  "api": "medix ia online",
  "status": "ok"
}
```

---

## Teste 2 — Previsão de demanda (GET)

```
GET http://localhost:5000/api/previsao
```

Resposta retornada em:

```json
[
  { "ds": "2026-05-23", "yhat": 11, "yhat_lower": 7,  "yhat_upper": 14 },
  { "ds": "2026-05-24", "yhat": 8,  "yhat_lower": 5,  "yhat_upper": 12 },
  { "ds": "2026-05-25", "yhat": 30, "yhat_lower": 27, "yhat_upper": 34 },
  { "ds": "2026-05-26", "yhat": 29, "yhat_lower": 26, "yhat_upper": 32 },
  { "ds": "2026-05-27", "yhat": 31, "yhat_lower": 27, "yhat_upper": 34 },
  { "ds": "2026-05-28", "yhat": 29, "yhat_lower": 26, "yhat_upper": 33 },
  { "ds": "2026-05-29", "yhat": 31, "yhat_lower": 28, "yhat_upper": 34 }
]
```

O modelo capturou a sazonalidade semanal corretamente: fins de semana (23 e 24/05) com ~8–11 atendimentos e dias úteis com ~29–31. Isso bate com o padrão real de uma clínica.

---

## Teste 3 — Previsão via POST

Mesma rota, método POST. O APEX envia requisições assim quando configurado como REST Data Source.

```
POST http://localhost:5000/api/previsao
Content-Type: application/json
```

Resposta idêntica ao GET — o endpoint trata os dois métodos da mesma forma.

---

## Teste 4 — Erro sem dependências

Derrubei o Prophet manualmente para ver o comportamento da API em caso de falha interna.

Resposta:

```json
{
  "erro": "descrição do erro"
}
```

HTTP 500. O servidor não travou, continuou respondendo normalmente depois.

---

## Teste 5 — Integração com Oracle APEX

Configurei um REST Data Source no APEX apontando para a URL do Ngrok + `/api/previsao`. Criei um Chart (Line) na página principal mapeando `ds` no eixo X e `yhat` no eixo Y.

O gráfico renderizou os 7 dias de previsão corretamente.

---

## Resultado geral

Todos os testes passaram. A API responde rápido (~2s incluindo o treinamento do Prophet), o CORS não bloqueou nenhuma requisição do APEX e o gráfico ficou igual ao esperado.
