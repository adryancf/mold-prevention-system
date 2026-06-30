/*
 * task_comms.cpp — T4: Comunicação TCP, tratamento de protocolo e persistência em NVS
 *
 * Este arquivo é organizado em três seções claramente separadas:
 *
 *   SEÇÃO 1 — SOCKET
 *     Funções que gerenciam o ciclo de vida do servidor TCP: bind, listen, accept,
 *     envio de bytes brutos, recebimento de bytes brutos e tratamento de desconexão.
 *     O ESP32 é o SERVIDOR TCP. A aplicação desktop é o CLIENTE.
 *
 *   SEÇÃO 2 — PROTOCOLO
 *     Funções que serializam e desserializam as mensagens JSON definidas em
 *     docs/protocol.md. Depende de ArduinoJson.
 *
 *   SEÇÃO 3 — PERSISTÊNCIA
 *     Chamada quando uma mensagem "config" válida é recebida. Aplica os novos
 *     limiares em g_config (sob xConfigMutex) e os persiste no NVS.
 *
 *   PONTO DE ENTRADA DA TAREFA
 *     vTaskComms orquestra as três seções em um loop:
 *       - Aceita uma conexão de cliente
 *       - Periodicamente envia leitura + estado (SEÇÃO 1 + 2)
 *       - Analisa dados recebidos (SEÇÃO 2)
 *       - Se mensagem de config: persiste (SEÇÃO 3)
 *       - Trata desconexão e aguarda próximo cliente
 *
 * ── Resumo do protocolo ───────────────────────────────────────────────────────
 *   ESP32 → Desktop  {"type":"reading","seq":N,"temp":T,"hum":H,
 *                      "heat":bool,"dehum":bool,"rec":"..."}
 *   Desktop → ESP32  {"type":"config","temp_thresh":T,"hum_thresh":H}
 *   ESP32 → Desktop  {"type":"ack","status":"ok"} ou {"type":"ack","status":"error","msg":"..."}
 *
 *   Mensagens são delimitadas por nova linha (\n), strings JSON UTF-8.
 * ─────────────────────────────────────────────────────────────────────────────
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <ArduinoJson.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/semphr.h>
#include <string.h>

#include "config.h"
#include "types.h"

// Definido em main.cpp
extern SemaphoreHandle_t xConfigMutex;
extern SemaphoreHandle_t xStateMutex;
extern Config            g_config;
extern SystemState       g_state;

// Declarações antecipadas para funções de armazenamento (definidas em storage.cpp)
void storageSaveConfig(const Config *cfg);

// ============================================================================
// SEÇÃO 1 — SOCKET
// ============================================================================

static WiFiServer tcpServer(TCP_PORT);

/**
 * socketInit — inicia o servidor TCP para que o desktop possa se conectar.
 * Chamada uma vez no início de vTaskComms.
 */
static void socketInit() {
    tcpServer.begin();
    tcpServer.setNoDelay(true);
    Serial.printf("[comms/socket] Servidor TCP aguardando na porta %d\n", TCP_PORT);
}

/**
 * socketWaitForClient — bloqueia até um cliente desktop se conectar.
 * Retorna o objeto WiFiClient conectado.
 */
static WiFiClient socketWaitForClient() {
    Serial.println("[comms/socket] Aguardando conexao do cliente desktop...");
    WiFiClient client;
    while (!client) {
        client = tcpServer.available();
        if (!client) {
            vTaskDelay(pdMS_TO_TICKS(200));
        }
    }
    client.setTimeout(5);  // timeout de leitura de 5 s
    Serial.printf("[comms/socket] Desktop conectado de %s\n",
                  client.remoteIP().toString().c_str());
    return client;
}

/**
 * socketSendLine — serializa um JsonDocument para o cliente como string terminada em nova linha.
 * Retorna false se o envio falhar (cliente desconectado).
 */
static bool socketSendLine(WiFiClient &client, JsonDocument &doc) {
    String line;
    serializeJson(doc, line);
    line += '\n';
    size_t written = client.print(line);
    return (written == line.length());
}

/**
 * socketReadLine — lê uma linha terminada em nova linha do cliente.
 * Retorna string vazia em caso de timeout ou desconexão.
 */
static String socketReadLine(WiFiClient &client) {
    if (!client.connected()) return "";
    String line = client.readStringUntil('\n');
    line.trim();
    return line;
}

// ============================================================================
// SEÇÃO 2 — PROTOCOLO
// ============================================================================

/**
 * protocolBuildReading — constrói uma mensagem JSON "reading" a partir do SystemState atual.
 * O chamador deve manter xStateMutex antes de chamar esta função, ou passar uma cópia local (preferível para minimizar o tempo com o mutex).
 */
static void protocolBuildReading(JsonDocument &doc, const SystemState &snap) {
    doc["type"]  = "reading";
    doc["seq"]   = snap.seq;
    doc["temp"]  = serialized(String(snap.temp,  1));
    doc["hum"]   = serialized(String(snap.hum,   1));
    doc["heat"]  = snap.heat_on;
    doc["dehum"] = snap.dehum_on;
    doc["rec"]   = snap.vent_rec;
}

/**
 * protocolBuildAck — constrói uma mensagem de confirmação (acknowledgement).
 * status: "ok" ou "error". msg é opcional, usado quando status = "error".
 */
static void protocolBuildAck(JsonDocument &doc, const char *status, const char *msg = nullptr) {
    doc["type"]   = "ack";
    doc["status"] = status;
    if (msg != nullptr) {
        doc["msg"] = msg;
    }
}

/**
 * protocolParseIncoming — tenta analisar uma linha recebida como mensagem JSON.
 * Retorna a string do tipo de mensagem ("config", desconhecido, ou vazio em erro de parse).
 */
static String protocolParseIncoming(const String &line, JsonDocument &doc) {
    if (line.isEmpty()) return "";
    DeserializationError err = deserializeJson(doc, line);
    if (err) {
        Serial.printf("[comms/proto] Erro ao parsear JSON: %s\n", err.c_str());
        return "";
    }
    const char *type = doc["type"] | "";
    return String(type);
}

// ============================================================================
// SEÇÃO 3 — PERSISTÊNCIA
// ============================================================================

/**
 * persistApplyConfig — valida e aplica novos limiares recebidos do desktop.
 * Atualiza g_config (protegido por xConfigMutex) e salva no NVS.
 * Retorna true em sucesso, false se os valores estiverem fora de uma faixa razoável.
 */
static bool persistApplyConfig(const JsonDocument &doc) {
    float new_temp = doc["temp_thresh"] | NAN;
    float new_hum  = doc["hum_thresh"]  | NAN;

    // Verificação básica: rejeita valores implausíveis.
    if (isnan(new_temp) || isnan(new_hum) ||
        new_temp < -10.0f || new_temp > 50.0f ||
        new_hum  <   0.0f || new_hum  > 100.0f) {
        Serial.println("[comms/persist] Config com valores fora do intervalo recebida — rejeitada");
        return false;
    }

    // Atualiza g_config sob mutex e persiste.
    if (xSemaphoreTake(xConfigMutex, pdMS_TO_TICKS(200)) == pdTRUE) {
        g_config.temp_thresh = new_temp;
        g_config.hum_thresh  = new_hum;
        storageSaveConfig(&g_config);
        xSemaphoreGive(xConfigMutex);
        Serial.printf("[comms/persist] Configuracao atualizada e salva — temp=%.1f  hum=%.1f\n",
                      new_temp, new_hum);
        return true;
    }

    Serial.println("[comms/persist] Timeout no xConfigMutex — configuracao nao aplicada");
    return false;
}

// ============================================================================
// PONTO DE ENTRADA DA TAREFA
// ============================================================================

void vTaskComms(void *pvParameters) {
    (void)pvParameters;

    socketInit();

    for (;;) {
        WiFiClient client = socketWaitForClient();

        uint32_t lastSentSeq = UINT32_MAX;  // Força envio na primeira iteração
        TickType_t xLastSendTime = xTaskGetTickCount();
        const TickType_t kSendInterval = pdMS_TO_TICKS(2500);

        while (client.connected()) {
            // --- Envio: periodicamente envia o estado atual ao desktop ------
            TickType_t now = xTaskGetTickCount();
            if ((now - xLastSendTime) >= kSendInterval) {
                xLastSendTime = now;

                SystemState snap;
                if (xSemaphoreTake(xStateMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
                    snap = g_state;
                    xSemaphoreGive(xStateMutex);
                } else {
                    vTaskDelay(pdMS_TO_TICKS(100));
                    continue;
                }

                // Envia apenas se o estado mudou desde a última transmissão.
                if (snap.seq != lastSentSeq) {
                    StaticJsonDocument<256> txDoc;
                    protocolBuildReading(txDoc, snap);
                    if (!socketSendLine(client, txDoc)) {
                        Serial.println("[comms/socket] Falha no envio — cliente desconectado");
                        break;
                    }
                    lastSentSeq = snap.seq;
                }
            }

            // --- Recebimento: verifica dados chegando do desktop ------------
            if (client.available()) {
                String line = socketReadLine(client);
                if (line.isEmpty()) {
                    vTaskDelay(pdMS_TO_TICKS(10));
                    continue;
                }

                StaticJsonDocument<128> rxDoc;
                String msgType = protocolParseIncoming(line, rxDoc);

                if (msgType == "config") {
                    bool ok = persistApplyConfig(rxDoc);
                    StaticJsonDocument<64> ackDoc;
                    protocolBuildAck(ackDoc,
                                     ok ? "ok" : "error",
                                     ok ? nullptr : "Valores invalidos ou fora do intervalo");
                    socketSendLine(client, ackDoc);
                } else if (!msgType.isEmpty()) {
                    Serial.printf("[comms/proto] Tipo de mensagem desconhecido: %s\n",
                                  msgType.c_str());
                }
            }

            vTaskDelay(pdMS_TO_TICKS(50));
        }

        client.stop();
        Serial.println("[comms/socket] Desktop desconectado. Aguardando nova conexao.");
    }
}
