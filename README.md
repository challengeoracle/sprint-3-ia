# Medix AI - Integração APEX e Inteligência Artificial

**Challenge FIAP x Oracle - Sprint 4 (Final)**

---

## Integrantes

| Nome | RM | Responsabilidade |
|------|----|-----------------|
| Arthur Thomas Mariano de Souza | 561061 | IoT & IA Generativa, .NET e Mobile |
| Davi Cavalcanti Jorge | 559873 | Compliance & Q.A, DevOps e Mobile |
| Mateus da Silveira Lima | 559728 | Banco de Dados, Java e Mobile |

---

## O que é este projeto?

Nesta última sprint, nosso foco foi tirar o modelo de IA do ambiente de testes e colocá-lo para rodar de forma integrada. O objetivo final é resolver um problema clássico da gestão hospitalar: a tomada de decisão reativa. 

Construímos uma API que conecta o nosso motor preditivo em Python diretamente ao Oracle APEX. Dessa forma, o gestor do hospital consegue abrir o sistema e visualizar em um gráfico a previsão exata de demanda de pacientes para os próximos 7 dias, permitindo ajustar a escala de médicos e leitos antes do pico acontecer.

---

## O Motor da IA

Para fazer a previsão, utilizamos o **Prophet** (desenvolvido pela Meta). A escolha se deu por um motivo prático: dados de saúde têm sazonalidades muito fortes (o movimento despenca no domingo e explode na segunda-feira). O Prophet lida com esse padrão perfeitamente sem precisar do custo computacional de uma rede neural complexa.

**Sobre os dados:** Como não podemos usar dados reais de pacientes devido à LGPD, nós criamos um gerador de dados sintéticos direto no código (`app.py`). Toda vez que a API é chamada, ela usa o `numpy` para gerar um histórico realista de 90 dias de uma clínica (incluindo ruído e variação de fim de semana), treina o modelo na hora e cospe a projeção futura.

---

## Arquitetura de Integração

O fluxo de dados para fazer o Python conversar com o Oracle APEX na nuvem funciona da seguinte forma:

```text
┌─────────────────────────────────────────────────────┐
│                 FRONT-END (Oracle APEX)             │
│                                                     │
│ - Dashboard do Gestor Hospitalar                    │
│ - Módulo de Gráfico (Line Chart) consumindo REST    │
└──────────────────────┬──────────────────────────────┘
                       │
             HTTP GET via REST Data Source
                       │
┌──────────────────────▼──────────────────────────────┐
│                 GATEWAY (Ngrok)                     │
│                                                     │
│ - Cria um túnel seguro expondo o localhost          │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                 BACK-END (Python/Flask)             │
│                                                     │
│ - Recebe o request no /api/previsao                 │
│ - Gera dados sintéticos e treina o Prophet          │
│ - Devolve o JSON com as datas (ds) e previsão (yhat)│
└─────────────────────────────────────────────────────┘

```

A API retorna uma lista limpa no formato exato que o APEX precisa para desenhar o gráfico, já com os números arredondados (afinal, não existe "meio" paciente). Exemplo do payload:

```json
[
  {
    "ds": "2026-05-21",
    "yhat": 204,
    "yhat_lower": 194,
    "yhat_upper": 213
  },
  {
    "ds": "2026-05-22",
    "yhat": 222,
    "yhat_lower": 211,
    "yhat_upper": 234
  }
]

```

---

## Como rodar o projeto localmente

Para testar a infraestrutura e ver a integração rodando na sua máquina, siga os passos abaixo.

**Pré-requisitos:** Python 3.10+, uma conta no Ngrok e as dependências instaladas (`pip install flask flask-cors prophet pandas numpy`).

**1. Suba a API**
Abra o terminal na pasta do projeto e inicie o servidor:

```bash
python app.py

```

A API vai ficar escutando na porta 5000.

**2. Abra o túnel com o Ngrok**
Em um segundo terminal, rode:

```bash
ngrok http 5000

```

Copie a URL HTTPS gerada (ex: `https://xxxx.ngrok-free.app`).

**3. Configure o APEX**

1. No seu aplicativo do Oracle APEX, vá em **Shared Components > REST Data Sources** e crie uma conexão usando a URL do Ngrok + a rota `/api/previsao`.
2. Na página principal, crie um **Chart (Line)**.
3. Aponte a origem dos dados (Source) para o REST criado.
4. No mapeamento de colunas, coloque `ds` no Label (Eixo X) e `yhat` no Value (Eixo Y).
5. Rode a página.

---

## Demonstração (Vídeo Pitch)

O vídeo mostrando o código funcionando no terminal, a integração via Ngrok e o gráfico sendo renderizado ao vivo no Oracle APEX está disponível abaixo:

👉 **https://youtu.be/I6_daeBBrtE**

---

### Entregas da Sprint 4

* API Flask construída e documentada.
* Modelo Prophet gerando séries temporais dinâmicas.
* Integração ponta a ponta finalizada com o Oracle APEX.
* Dashboard renderizando dados da IA.