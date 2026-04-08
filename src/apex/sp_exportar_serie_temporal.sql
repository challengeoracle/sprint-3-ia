-- =============================================================================
-- Medix AI -- Sprint 3: Disruptive Architectures
-- =============================================================================
-- Script  : sp_exportar_serie_temporal.sql
-- Banco   : Oracle Database 19c+
-- Descricao:
--   Stored procedure responsavel por:
--   1. Consolidar o historico de agendamentos dos ultimos N dias
--   2. Agrupar os registros por data e especialidade
--   3. Serializar o resultado como JSON
--   4. Enviar o payload ao endpoint REST do modelo de IA via UTL_HTTP
--   5. Receber a resposta (previsao + alertas) e persistir no banco
--
-- Esta procedure e chamada pelo Oracle APEX (via ORDS) quando o gestor
-- aciona o painel de Previsao de Demanda na interface do sistema.
--
-- Uso:
--   EXEC SP_EXPORTAR_SERIE_TEMPORAL(
--     p_unidade_id    => 1,
--     p_especialidade => 'Cardiologia',
--     p_dias_futuro   => 30,
--     p_dias_historico=> 90
--   );
-- =============================================================================


-- =============================================================================
-- TABELAS DE SUPORTE (criar antes de rodar a procedure)
-- =============================================================================

-- Tabela de capacidade diaria por especialidade por unidade
-- Alimentada pelos gestores via painel APEX
CREATE TABLE TB_CAPACIDADE_UNIDADE (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    unidade_id      NUMBER        NOT NULL,
    especialidade   VARCHAR2(100) NOT NULL,
    limite_diario   NUMBER(5)     NOT NULL DEFAULT 30,
    dt_atualizacao  DATE          DEFAULT SYSDATE,
    CONSTRAINT fk_cap_unidade FOREIGN KEY (unidade_id)
        REFERENCES TB_UNIDADE(id),
    CONSTRAINT uq_cap_unidade_esp UNIQUE (unidade_id, especialidade)
);

-- Tabela de previsoes geradas pela IA (historico de resultados)
CREATE TABLE TB_PREVISAO_DEMANDA (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    unidade_id      NUMBER         NOT NULL,
    especialidade   VARCHAR2(100)  NOT NULL,
    dt_previsao     DATE           NOT NULL,  -- data prevista
    yhat            NUMBER(8,2),              -- valor central da previsao
    yhat_lower      NUMBER(8,2),              -- limite inferior (95% CI)
    yhat_upper      NUMBER(8,2),              -- limite superior (95% CI)
    excede_cap      CHAR(1)        DEFAULT 'N' CHECK (excede_cap IN ('S','N')),
    alerta          CHAR(1)        DEFAULT 'N' CHECK (alerta IN ('S','N')),
    motivo_alerta   VARCHAR2(500),
    dt_geracao      DATE           DEFAULT SYSDATE,
    CONSTRAINT fk_prev_unidade FOREIGN KEY (unidade_id)
        REFERENCES TB_UNIDADE(id)
);

-- View agregada: historico diario por especialidade e unidade
-- Usada pela procedure para montar a serie temporal de entrada
CREATE OR REPLACE VIEW VW_DEMANDA_HISTORICA AS
    SELECT
        TO_CHAR(a.data_agendamento, 'YYYY-MM-DD') AS ds,
        COUNT(*)                                   AS y,
        a.especialidade,
        a.unidade_id
    FROM
        TB_AGENDAMENTO a
    WHERE
        a.status = 'Realizado'
    GROUP BY
        TO_CHAR(a.data_agendamento, 'YYYY-MM-DD'),
        a.especialidade,
        a.unidade_id
    ORDER BY
        ds;


-- =============================================================================
-- PROCEDURE PRINCIPAL
-- =============================================================================

CREATE OR REPLACE PROCEDURE SP_EXPORTAR_SERIE_TEMPORAL (
    p_unidade_id     IN NUMBER,
    p_especialidade  IN VARCHAR2,
    p_dias_futuro    IN NUMBER DEFAULT 30,    -- horizonte de previsao (7, 15 ou 30)
    p_dias_historico IN NUMBER DEFAULT 90     -- janela historica para o modelo
)
AS
    -- ── Variaveis de configuracao ──────────────────────────────────────────
    v_endpoint_url   VARCHAR2(500)  := 'http://localhost:5000/prever';
    v_timeout        NUMBER         := 30;    -- timeout HTTP em segundos

    -- ── Variaveis de execucao ──────────────────────────────────────────────
    v_http_req       UTL_HTTP.REQ;
    v_http_resp      UTL_HTTP.RESP;
    v_payload        CLOB;
    v_resposta       CLOB;
    v_buffer         VARCHAR2(32767);
    v_capacidade     NUMBER;
    v_alerta         VARCHAR2(10);
    v_motivo         VARCHAR2(500);

    -- ── Cursor: historico de agendamentos ─────────────────────────────────
    CURSOR c_historico IS
        SELECT ds, y
        FROM   VW_DEMANDA_HISTORICA
        WHERE  unidade_id    = p_unidade_id
          AND  especialidade = p_especialidade
          AND  TO_DATE(ds, 'YYYY-MM-DD') >= SYSDATE - p_dias_historico
        ORDER BY ds;

    v_primeiro  BOOLEAN := TRUE;
    v_linha     c_historico%ROWTYPE;

BEGIN

    -- ── 1. Busca o limite de capacidade configurado ───────────────────────
    BEGIN
        SELECT limite_diario
        INTO   v_capacidade
        FROM   TB_CAPACIDADE_UNIDADE
        WHERE  unidade_id    = p_unidade_id
          AND  especialidade = p_especialidade;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            v_capacidade := 30;  -- valor padrao se nao configurado
    END;

    -- ── 2. Serializa o historico como JSON ────────────────────────────────
    -- Monta o payload no formato esperado pelo modelo Prophet:
    -- {
    --   "especialidade": "Cardiologia",
    --   "unidade_id": 1,
    --   "dias": 30,
    --   "capacidade_diaria": 25,
    --   "dados_historicos": [
    --     {"ds": "2025-01-01", "y": 18},
    --     ...
    --   ]
    -- }

    v_payload := '{';
    v_payload := v_payload || '"especialidade":"'  || p_especialidade            || '",';
    v_payload := v_payload || '"unidade_id":'      || TO_CHAR(p_unidade_id)      || ',';
    v_payload := v_payload || '"dias":'            || TO_CHAR(p_dias_futuro)     || ',';
    v_payload := v_payload || '"capacidade_diaria":' || TO_CHAR(v_capacidade)   || ',';
    v_payload := v_payload || '"dados_historicos":[';

    OPEN c_historico;
    LOOP
        FETCH c_historico INTO v_linha;
        EXIT WHEN c_historico%NOTFOUND;

        IF NOT v_primeiro THEN
            v_payload := v_payload || ',';
        END IF;

        v_payload := v_payload
            || '{"ds":"' || v_linha.ds || '",'
            || '"y":'    || TO_CHAR(v_linha.y) || '}';

        v_primeiro := FALSE;
    END LOOP;
    CLOSE c_historico;

    v_payload := v_payload || ']}';

    -- ── 3. Envia o payload ao endpoint REST via UTL_HTTP ──────────────────
    UTL_HTTP.SET_TRANSFER_TIMEOUT(v_timeout);

    v_http_req := UTL_HTTP.BEGIN_REQUEST(
        url    => v_endpoint_url,
        method => 'POST'
    );

    UTL_HTTP.SET_HEADER(v_http_req, 'Content-Type',   'application/json');
    UTL_HTTP.SET_HEADER(v_http_req, 'Content-Length', LENGTH(v_payload));
    UTL_HTTP.WRITE_TEXT(v_http_req, v_payload);

    -- ── 4. Le a resposta do modelo ────────────────────────────────────────
    v_http_resp := UTL_HTTP.GET_RESPONSE(v_http_req);
    v_resposta  := EMPTY_CLOB();

    BEGIN
        LOOP
            UTL_HTTP.READ_LINE(v_http_resp, v_buffer, FALSE);
            v_resposta := v_resposta || v_buffer;
        END LOOP;
    EXCEPTION
        WHEN UTL_HTTP.END_OF_BODY THEN NULL;
    END;

    UTL_HTTP.END_RESPONSE(v_http_resp);

    -- ── 5. Persiste as previsoes na tabela TB_PREVISAO_DEMANDA ────────────
    -- Limpa previsoes antigas para esta especialidade/unidade antes de inserir
    DELETE FROM TB_PREVISAO_DEMANDA
    WHERE  unidade_id    = p_unidade_id
      AND  especialidade = p_especialidade
      AND  dt_geracao   >= TRUNC(SYSDATE);

    -- Insere cada linha de previsao parseando o JSON de resposta
    -- Nota: em producao usar APEX_JSON ou JSON_TABLE para parse mais robusto
    FOR rec IN (
        SELECT
            jt.dt_previsao,
            jt.yhat,
            jt.yhat_lower,
            jt.yhat_upper,
            jt.excede_cap
        FROM
            JSON_TABLE(
                v_resposta,
                '$.previsao[*]'
                COLUMNS (
                    dt_previsao  DATE          PATH '$.ds'               FORMAT 'YYYY-MM-DD',
                    yhat         NUMBER(8,2)   PATH '$.yhat',
                    yhat_lower   NUMBER(8,2)   PATH '$.yhat_lower',
                    yhat_upper   NUMBER(8,2)   PATH '$.yhat_upper',
                    excede_cap   VARCHAR2(10)  PATH '$.excede_capacidade'
                )
            ) jt
    )
    LOOP
        INSERT INTO TB_PREVISAO_DEMANDA (
            unidade_id, especialidade,
            dt_previsao, yhat, yhat_lower, yhat_upper,
            excede_cap, alerta, motivo_alerta, dt_geracao
        ) VALUES (
            p_unidade_id, p_especialidade,
            rec.dt_previsao, rec.yhat, rec.yhat_lower, rec.yhat_upper,
            CASE WHEN rec.excede_cap = 'true' THEN 'S' ELSE 'N' END,
            CASE WHEN rec.excede_cap = 'true' THEN 'S' ELSE 'N' END,
            'Previsao gerada automaticamente pelo modelo Prophet.',
            SYSDATE
        );
    END LOOP;

    COMMIT;

    DBMS_OUTPUT.PUT_LINE('OK - Previsao gerada e persistida com sucesso.');
    DBMS_OUTPUT.PUT_LINE('Unidade: ' || p_unidade_id || ' | Especialidade: ' || p_especialidade);

EXCEPTION
    WHEN UTL_HTTP.REQUEST_FAILED THEN
        ROLLBACK;
        DBMS_OUTPUT.PUT_LINE('ERRO - Falha na requisicao HTTP ao endpoint do modelo.');
        DBMS_OUTPUT.PUT_LINE('Verifique se o servidor endpoint_previsao.py esta em execucao.');
        RAISE;
    WHEN OTHERS THEN
        ROLLBACK;
        DBMS_OUTPUT.PUT_LINE('ERRO - ' || SQLERRM);
        RAISE;
END SP_EXPORTAR_SERIE_TEMPORAL;
/


-- =============================================================================
-- EXEMPLO DE EXECUCAO
-- =============================================================================

-- Gerar previsao para Cardiologia, unidade 1, horizonte de 30 dias:
/*
SET SERVEROUTPUT ON;

EXEC SP_EXPORTAR_SERIE_TEMPORAL(
    p_unidade_id    => 1,
    p_especialidade => 'Cardiologia',
    p_dias_futuro   => 30,
    p_dias_historico=> 90
);

-- Consultar as previsoes geradas:
SELECT
    especialidade,
    TO_CHAR(dt_previsao, 'DD/MM/YYYY') AS data,
    yhat                               AS previsao_central,
    yhat_lower                         AS limite_inferior,
    yhat_upper                         AS limite_superior,
    excede_cap                         AS excede_capacidade
FROM
    TB_PREVISAO_DEMANDA
WHERE
    unidade_id    = 1
  AND especialidade = 'Cardiologia'
  AND dt_geracao >= TRUNC(SYSDATE)
ORDER BY
    dt_previsao;
*/
