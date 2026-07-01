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
#include <math.h>
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
static const size_t MAX_INCOMING_LINE_LEN = 256;

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
 * socketWaitForWifi — aguarda a interface WiFi ficar conectada.
 * O auto-reconnect e configurado em setup(); aqui apenas evitamos aceitar
 * clientes enquanto o ESP32 estiver fora da rede.
 */
static void socketWaitForWifi() {
    while (WiFi.status() != WL_CONNECTED) {
        Serial.println("[comms/socket] WiFi desconectado — aguardando reconexao...");
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
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
    Serial.printf("[comms/socket] Desktop conectado de %s\n",
                  client.remoteIP().toString().c_str());
    return client;
}

/**
 * socketSendLine — serializa um JsonDocument para o cliente como string terminada em nova linha.
 * Retorna false se o envio falhar (cliente desconectado).
 */
static bool socketSendLine(WiFiClient &client, const JsonDocument &doc) {
    String line;
    serializeJson(doc, line);
    line += '\n';
    size_t written = client.print(line);
    return (written == line.length());
}

/**
 * socketReadLine — acumula bytes recebidos ate formar uma linha completa.
 * Retorna true apenas quando uma mensagem terminada em '\n' esta pronta.
 */
static bool socketReadLine(WiFiClient &client, String &rxBuffer, bool &overflowed, String &line) {
    while (client.available()) {
        int value = client.read();
        if (value < 0) {
            break;
        }

        char ch = static_cast<char>(value);
        if (ch == '\r') {
            continue;
        }

        if (ch == '\n') {
            if (overflowed) {
                overflowed = false;
                rxBuffer = "";
                Serial.println("[comms/socket] Linha recebida excedeu o limite — descartada");
                continue;
            }

            line = rxBuffer;
            rxBuffer = "";
            line.trim();
            if (!line.isEmpty()) {
                return true;
            }
            continue;
        }

        if (overflowed) {
            continue;
        }

        if (rxBuffer.length() >= MAX_INCOMING_LINE_LEN) {
            overflowed = true;
            rxBuffer = "";
            continue;
        }

        rxBuffer += ch;
    }

    return false;
}

// ============================================================================
// SEÇÃO 2 — PROTOCOLO
// ============================================================================

/**
 * protocolBuildReading — constrói uma mensagem JSON "reading" a partir do SystemState atual.
 * O chamador deve manter xStateMutex antes de chamar esta função, ou passar uma cópia local (preferível para minimizar o tempo com o mutex).
 */
static float roundOneDecimal(float value) {
    return roundf(value * 10.0f) / 10.0f;
}

static void protocolBuildReading(JsonDocument &doc, const SystemState &snap, const Config &cfg) {
    doc["type"]        = "reading";
    doc["seq"]         = snap.seq;
    doc["temp"]        = roundOneDecimal(snap.temp);
    doc["hum"]         = roundOneDecimal(snap.hum);
    doc["heat"]        = snap.heat_on;
    doc["dehum"]       = snap.dehum_on;
    doc["rec"]         = snap.vent_rec;
    doc["temp_thresh"] = roundOneDecimal(cfg.temp_thresh);
    doc["hum_thresh"]  = roundOneDecimal(cfg.hum_thresh);
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

    Config new_config = { new_temp, new_hum };

    // Atualiza g_config sob mutex; a escrita em flash fica fora da seção crítica.
    if (xSemaphoreTake(xConfigMutex, pdMS_TO_TICKS(200)) == pdTRUE) {
        g_config = new_config;
        xSemaphoreGive(xConfigMutex);
    } else {
        Serial.println("[comms/persist] Timeout no xConfigMutex — configuracao nao aplicada");
        return false;
    }

    storageSaveConfig(&new_config);
    Serial.printf("[comms/persist] Configuracao atualizada e salva — temp=%.1f  hum=%.1f\n",
                  new_temp, new_hum);
    return true;
}

// ============================================================================
// PONTO DE ENTRADA DA TAREFA
// ============================================================================

void vTaskComms(void *pvParameters) {
    (void)pvParameters;

    socketInit();

    for (;;) {
        socketWaitForWifi();
        WiFiClient client = socketWaitForClient();

        uint32_t lastSentSeq = 0;
        bool forceSendState = false;
        String rxBuffer;
        bool rxOverflow = false;
        const TickType_t kStatePollInterval = pdMS_TO_TICKS(250);
        TickType_t xLastStatePoll = xTaskGetTickCount() - kStatePollInterval;

        while (client.connected()) {
            if (WiFi.status() != WL_CONNECTED) {
                Serial.println("[comms/socket] WiFi caiu — encerrando cliente atual");
                break;
            }

            // --- Envio: envia o estado assim que houver leitura valida nova ---
            TickType_t now = xTaskGetTickCount();
            if ((now - xLastStatePoll) >= kStatePollInterval) {
                xLastStatePoll = now;

                SystemState snap;
                if (xSemaphoreTake(xStateMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
                    snap = g_state;
                    xSemaphoreGive(xStateMutex);
                } else {
                    vTaskDelay(pdMS_TO_TICKS(100));
                    continue;
                }

                Config cfg;
                if (xSemaphoreTake(xConfigMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
                    cfg = g_config;
                    xSemaphoreGive(xConfigMutex);
                } else {
                    vTaskDelay(pdMS_TO_TICKS(100));
                    continue;
                }

                // seq == 0 representa o estado inicial, antes de qualquer leitura real.
                if (snap.seq > 0 && (forceSendState || snap.seq != lastSentSeq)) {
                    StaticJsonDocument<512> txDoc;
                    protocolBuildReading(txDoc, snap, cfg);
                    if (!socketSendLine(client, txDoc)) {
                        Serial.println("[comms/socket] Falha no envio — cliente desconectado");
                        break;
                    }
                    lastSentSeq = snap.seq;
                    forceSendState = false;
                }
            }

            // --- Recebimento: processa somente linhas JSON completas --------
            String line;
            bool keepClient = true;
            while (socketReadLine(client, rxBuffer, rxOverflow, line)) {
                StaticJsonDocument<192> rxDoc;
                String msgType = protocolParseIncoming(line, rxDoc);

                if (msgType == "config") {
                    bool ok = persistApplyConfig(rxDoc);
                    StaticJsonDocument<128> ackDoc;
                    protocolBuildAck(ackDoc,
                                     ok ? "ok" : "error",
                                     ok ? nullptr : "Valores invalidos ou fora do intervalo");
                    if (!socketSendLine(client, ackDoc)) {
                        keepClient = false;
                        break;
                    }
                    if (ok) {
                        forceSendState = true;
                    }
                } else if (!msgType.isEmpty()) {
                    Serial.printf("[comms/proto] Tipo de mensagem desconhecido: %s\n",
                                  msgType.c_str());
                    StaticJsonDocument<128> ackDoc;
                    protocolBuildAck(ackDoc, "error", "Tipo de mensagem desconhecido");
                    if (!socketSendLine(client, ackDoc)) {
                        keepClient = false;
                        break;
                    }
                }
            }

            if (!keepClient) {
                break;
            }

            vTaskDelay(pdMS_TO_TICKS(50));
        }

        client.stop();
        Serial.println("[comms/socket] Desktop desconectado. Aguardando nova conexao.");
    }
}
