/*
 * task_decision.cpp — T2: Tarefa de processamento e decisão
 *
 * Esta tarefa é responsável por:
 *   - Bloquear em xQueueSensor e consumir cada SensorReading conforme chega.
 *   - Ler os limites atuais de g_config (protegido por xConfigMutex).
 *   - Calcular o novo SystemState (heat_on, dehum_on, vent_rec).
 *   - Escrever o novo estado em g_state (protegido por xStateMutex).
 *   - Enviar uma notificação de tarefa para T3 (vTaskActuators) via xTaskNotify().
 *
 * Notificação de tarefa para T3:
 *   xTaskNotify() é usado em vez de semáforo binário porque:
 *     1. É mais leve — sem alocação de objeto semáforo.
 *     2. O valor da notificação não importa (apenas o sinal é relevante).
 *   T3 bloqueia em ulTaskNotifyTake(pdTRUE, portMAX_DELAY).
 *
 * Lógica de decisão:
 *   heat_on  = (temp < temp_thresh)
 *   dehum_on = (hum  > hum_thresh)
 *   vent_rec depende da combinação de temperatura e umidade:
 *     - Quente + úmido:  sugerir ventilação mais longa
 *     - Frio + úmido:    sugerir ventilação breve (evitar desconforto térmico)
 *     - Confortável:     nenhuma ação imediata recomendada
 */

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>
#include <math.h>
#include <string.h>

#include "config.h"
#include "types.h"

// Definido em main.cpp
extern QueueHandle_t    xQueueSensor;
extern SemaphoreHandle_t xConfigMutex;
extern SemaphoreHandle_t xStateMutex;
extern TaskHandle_t      xTaskActuators;
extern Config            g_config;
extern SystemState       g_state;

// ---------------------------------------------------------------------------
// Lógica de recomendação de ventilação
// ---------------------------------------------------------------------------
static void buildVentRec(float temp, float hum, bool heat_on, bool dehum_on, char *buf, size_t buflen) {
    if (!dehum_on && !heat_on) {
        snprintf(buf, buflen, "Condicoes adequadas. Ventilacao opcional.");
    } else if (heat_on && dehum_on) {
        snprintf(buf, buflen, "Frio e umido. Ventilar brevemente (5-10 min) e depois fechar.");
    } else if (!heat_on && dehum_on) {
        snprintf(buf, buflen, "Ambiente quente e umido. Ventilar por 15-30 min.");
    } else {
        snprintf(buf, buflen, "Temperatura baixa. Evite ventilacao prolongada.");
    }
}

// ---------------------------------------------------------------------------
// Ponto de entrada da tarefa
// ---------------------------------------------------------------------------
void vTaskDecision(void *pvParameters) {
    (void)pvParameters;

    SensorReading reading;

    while (true) {
        // Bloqueia indefinidamente até uma SensorReading estar disponível.
        if (xQueueReceive(xQueueSensor, &reading, portMAX_DELAY) != pdTRUE) {
            continue;
        }

        // Descarta leituras inválidas do sensor (erro do DHT) sem atualizar o estado.
        if (!reading.valid) {
            Serial.println("[decision] Leitura invalida recebida — ignorada");
            continue;
        }

        // --- Lê os limites atuais --------------------------
        // xConfigMutex garante que g_config não está sendo modificado por T4 ao mesmo tempo que estamos lendo.
        float temp_thresh, hum_thresh;
        if (xSemaphoreTake(xConfigMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            temp_thresh = g_config.temp_thresh;
            hum_thresh  = g_config.hum_thresh;
            xSemaphoreGive(xConfigMutex);
        } else {
            Serial.println("[decision] AVISO: timeout no xConfigMutex — estado anterior mantido");
            continue;
        }

        // --- Calcula o novo estado do sistema --------------------------------
        bool heat_on  = (reading.temp < temp_thresh);
        bool dehum_on = (reading.hum  > hum_thresh);
        char vent_rec[128];
        buildVentRec(reading.temp, reading.hum, heat_on, dehum_on, vent_rec, sizeof(vent_rec));

        // --- Escreve o novo estado (seção crítica) ---------------------------
        // xStateMutex impede que T3 e T4 leiam um estado parcialmente escrito.
        if (xSemaphoreTake(xStateMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            g_state.temp     = reading.temp;
            g_state.hum      = reading.hum;
            g_state.heat_on  = heat_on;
            g_state.dehum_on = dehum_on;
            strncpy(g_state.vent_rec, vent_rec, sizeof(g_state.vent_rec) - 1);
            g_state.vent_rec[sizeof(g_state.vent_rec) - 1] = '\0';
            g_state.seq++;
            xSemaphoreGive(xStateMutex);
        } else {
            Serial.println("[decision] AVISO: timeout no xStateMutex — estado nao atualizado");
            continue;
        }

        Serial.printf("[decision] heat=%d  dehum=%d  seq=%u  rec: %s\n",
                      heat_on, dehum_on, g_state.seq, vent_rec);

        // --- Notifica T3 (vTaskActuators) ------------------------------------                
        xTaskNotify(xTaskActuators, 0, eNoAction);
    }
}
