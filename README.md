# 🤖 Medix AI — Arquitetura de Inteligência Artificial
### Sprint 3 · Disruptive Architectures: IoT, Big Data & AI · FIAP × Oracle

---

## 👥 Integrantes

| Nome | RM | Responsabilidade |
|------|----|-----------------|
| Arthur Thomas Mariano de Souza | 561061 | IoT & IA Generativa, .NET e Mobile |
| Davi Cavalcanti Jorge | 559873 | Compliance & Q.A, DevOps e Mobile |
| Mateus da Silveira Lima | 559728 | Banco de Dados, Java e Mobile |

---

## 🎯 Objetivo desta Sprint

Esta sprint foca no **planejamento estratégico e na arquitetura de integração** do componente de Inteligência Artificial da plataforma Medix dentro do ecossistema Oracle.

O objetivo não é codificar a IA neste momento, mas sim definir formalmente:
- Qual problema real será resolvido com IA
- Qual modelo foi escolhido e por quê
- Como os dados fluem entre as camadas Oracle APEX → Oracle Database → Modelo de IA

---

## 🧠 Componente de IA — Previsão de Demanda

### Problema

Os gestores hospitalares tomam decisões de escala de colaboradores, alocação de leitos e gestão de recursos de forma **reativa** — somente após o pico de demanda já ter ocorrido. Isso resulta em sobrecarga de equipes, ociosidade de recursos e piora na qualidade do atendimento.

### Solução com IA

Um modelo de **previsão de séries temporais** analisa o histórico de agendamentos por especialidade e unidade, e projeta a demanda para os próximos 30 dias — permitindo ao gestor ajustar escalas e recursos **antes** do pico acontecer.

> Este objetivo está declarado explicitamente no escopo do projeto Medix: *"utilizar ferramentas de análise de dados para prever picos de demanda"*.

---

## 📊 Modelo de IA Escolhido

| Atributo | Detalhe |
|----------|---------|
| **Tipo** | Time Series Forecasting |
| **Modelo principal** | Prophet (Meta/Facebook) |
| **Modelo alternativo** | Gradient Boosting — XGBoost / LightGBM |
| **Ambiente** | OCI Data Science (Oracle Cloud Infrastructure) |
| **Linguagem** | Python 3.x |
| **Bibliotecas** | `prophet`, `scikit-learn`, `pandas`, `numpy` |

### Por que Prophet e não outros modelos?

| Modelo | Por que não? |
|--------|-------------|
| **CNN** | Projetada para dados com estrutura espacial (imagens, sinais 2D). Dados de agendamento são uma sequência 1D de contagens — CNN não agrega valor. |
| **NLP puro** | Ideal para texto livre. O problema de previsão de demanda é quantitativo, não linguístico. |
| **LSTM / RNN** | Viável, mas exige volume maior de dados e custo computacional mais alto para um ganho marginal neste caso. |
| **Prophet ✅** | Captura múltiplas sazonalidades sobrepostas (semanal + mensal + anual), lida bem com feriados e dados faltantes, e gera componentes interpretáveis — o gestor entende *por que* o pico foi previsto. |

---

## 🔄 Caso de Uso no Oracle APEX

Fluxo completo quando o gestor aciona a funcionalidade:

```
1. Gestor acessa "Previsão de Demanda" no painel APEX
2. Seleciona: unidade de saúde + especialidade + horizonte (7, 15 ou 30 dias)
3. APEX dispara chamada via ORDS (Oracle REST Data Services)
4. Oracle DB executa SP_EXPORTAR_SERIE_TEMPORAL
   → agrupa histórico de agendamentos por data e especialidade
   → serializa como JSON
5. ORDS encaminha JSON ao endpoint REST no OCI Data Science
6. Modelo processa a série temporal e retorna previsão + intervalos de confiança
7. APEX renderiza gráfico de linha com:
   ├── Histórico real (linha sólida)
   ├── Previsão central (linha tracejada)
   └── Banda de confiança (área sombreada)
8. Se previsão > limiar de capacidade configurado → alerta vermelho automático
```

---

## 🏗️ Arquitetura de Integração

```
┌─────────────────────────────────────────────────────┐
│                   CAMADA 1                          │
│                 Oracle APEX                         │
│                                                     │
│  Painel do Gestor                                   │
│  ┌─────────────────────────────────────────────┐   │
│  │ Formulário: unidade + especialidade + dias  │   │
│  │ Gráfico: histórico + previsão + alertas     │   │
│  └─────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────┘
                       │
            ORDS — HTTP/JSON Request
                       │
┌──────────────────────▼──────────────────────────────┐
│                   CAMADA 2                          │
│                Oracle Database                      │
│                                                     │
│  TB_AGENDAMENTO  ──►  VW_DEMANDA_HISTORICA          │
│  TB_UNIDADE                 │                       │
│  TB_CAPACIDADE_UNIDADE      ▼                       │
│                   SP_EXPORTAR_SERIE_TEMPORAL        │
│                   (serializa JSON via UTL_HTTP)     │
└──────────────────────┬──────────────────────────────┘
                       │
            REST API — JSON payload
            { "ds": "2025-01-15", "y": 23, ... }
                       │
┌──────────────────────▼──────────────────────────────┐
│                   CAMADA 3                          │
│          Modelo de IA — OCI Data Science            │
│                                                     │
│  Input:  série temporal de agendamentos (90+ dias)  │
│  Modelo: Prophet / Gradient Boosting                │
│  Output: previsão 30 dias + intervalos confiança    │
│                                                     │
│  Endpoint REST gerenciado pelo OCI                  │
└─────────────────────────────────────────────────────┘
```

---

## 📦 Estratégia de Dados

### Origem
- **Fonte:** Oracle Database — tabela `TB_AGENDAMENTO` (entidade Consulta/Agendamento)
- **Campos mínimos:** `id`, `data_agendamento` (DATE), `especialidade` (VARCHAR), `unidade_id` (FK), `status` (VARCHAR)

### Formato de entrada do modelo
```json
[
  { "ds": "2025-01-01", "y": 18, "especialidade": "Cardiologia", "unidade_id": 1 },
  { "ds": "2025-01-02", "y": 23, "especialidade": "Cardiologia", "unidade_id": 1 },
  { "ds": "2025-01-03", "y": 9,  "especialidade": "Cardiologia", "unidade_id": 1 }
]
```

### Formato de saída do modelo
```json
{
  "previsao": [
    { "ds": "2025-04-07", "yhat": 27, "yhat_lower": 21, "yhat_upper": 33 },
    { "ds": "2025-04-08", "yhat": 19, "yhat_lower": 14, "yhat_upper": 24 }
  ],
  "alerta": true,
  "motivo": "Previsão de 27 atendimentos excede o limite configurado de 25 para Cardiologia."
}
```

### Volume mínimo
- **MVP:** 90 dias de histórico por especialidade por unidade (pode ser sintético)
- **Produção:** 365+ dias para capturar sazonalidade anual completa

### Estratégia para MVP (dados sintéticos)
Para a demonstração desta sprint, será utilizado um script Python que gera dados históricos realistas com os padrões típicos de uma unidade de saúde:

```python
import pandas as pd
import numpy as np

def gerar_dados_sinteticos(dias=180, especialidade="Cardiologia", unidade_id=1):
    datas = pd.date_range(start="2024-10-01", periods=dias, freq="D")
    np.random.seed(42)
    
    base = 20
    sazonalidade_semana = np.where(datas.weekday < 5, 1.2, 0.4)  # mais em dias úteis
    sazonalidade_mes = 1 + 0.15 * np.sin(2 * np.pi * datas.dayofyear / 365)
    ruido = np.random.normal(0, 2, dias)
    
    y = (base * sazonalidade_semana * sazonalidade_mes + ruido).clip(0).astype(int)
    
    return pd.DataFrame({
        "data_agendamento": datas,
        "y": y,
        "especialidade": especialidade,
        "unidade_id": unidade_id,
        "status": "Realizado"
    })
```

---

## 🛠️ Tecnologias Utilizadas

| Tecnologia | Versão | Papel |
|------------|--------|-------|
| Oracle APEX | 23.x | Interface do gestor — formulário e gráfico |
| Oracle Database | 19c+ | Armazenamento e stored procedures |
| Oracle REST Data Services (ORDS) | 23.x | Gateway REST entre camadas |
| OCI Data Science | — | Hospedagem do modelo como endpoint REST |
| Python | 3.10+ | Treinamento e inferência do modelo |
| Prophet | 1.1.x | Modelo de séries temporais |
| scikit-learn | 1.3.x | Pré-processamento e métricas |
| pandas / numpy | — | Manipulação dos dados |

---

## 📁 Estrutura do Repositório

```
sprint-3-ia/
├── README.md                        ← este arquivo
├── docs/
│   └── Medix_Arquitetura_IA_Sprint3.docx  ← documento completo de arquitetura
├── src/
│   ├── data/
│   │   └── gerar_dados_sinteticos.py      ← script de dados para o MVP
│   ├── model/
│   │   ├── treinar_modelo.py              ← treinamento do Prophet
│   │   └── endpoint_previsao.py           ← endpoint REST (Flask/FastAPI)
│   └── apex/
│       └── sp_exportar_serie_temporal.sql ← stored procedure Oracle
└── assets/
    └── diagrama_arquitetura.png           ← imagem do diagrama
```

---

## ▶️ Como Executar (MVP Local)

### Pré-requisitos
- Python 3.10+
- `pip install prophet scikit-learn pandas numpy flask`

### 1. Gerar dados sintéticos
```bash
cd src/data
python gerar_dados_sinteticos.py
```

### 2. Treinar o modelo
```bash
cd src/model
python treinar_modelo.py
```

### 3. Subir o endpoint REST localmente
```bash
python endpoint_previsao.py
# Disponível em: http://localhost:5000/prever
```

### 4. Testar o endpoint
```bash
curl -X POST http://localhost:5000/prever \
  -H "Content-Type: application/json" \
  -d '{"especialidade": "Cardiologia", "unidade_id": 1, "dias": 30}'
```

---

## 🎬 Vídeo Pitch

> 📺 **[Assistir no YouTube](https://youtube.com/SUA_URL_AQUI)** *(não listado)*

**Duração:** ~5 minutos  
**Conteúdo:**
1. Problema: gestão reativa de demanda hospitalar
2. Solução: modelo de previsão de séries temporais
3. Justificativa técnica do modelo escolhido
4. Demonstração simulada do painel APEX
5. Resultados esperados e próximos passos

---

## 📊 Resultados Alcançados nesta Sprint

- ✅ Problema real identificado e documentado com base no escopo do projeto Medix
- ✅ Modelo de IA selecionado (Prophet) com justificativa técnica comparativa
- ✅ Caso de uso no Oracle APEX descrito em detalhes
- ✅ Estratégia de dados definida (origem, formato, volume, fluxo)
- ✅ Diagrama de arquitetura de três camadas elaborado
- ✅ Script de dados sintéticos para validação do pipeline no MVP
- ✅ Documento de arquitetura completo

---

## 🔗 Links do Projeto

| Repositório | Link |
|-------------|------|
| Sprint 3 — IA (este repositório) | https://github.com/challengeoracle/sprint-3-ia |
| Sprint 1 — .NET (painel admin) | https://github.com/challengeoracle/sprint-1-dotnet |
| Sprint 1 — Mobile (app paciente) | https://github.com/challengeoracle/sprint-1-mobile |
| Sprint 1 — Java (backend) | https://github.com/challengeoracle/sprint-1-java |

---

*Desenvolvido para o Challenge FIAP em parceria com a Oracle · 2025*
