/*
 * task_actuators.cpp — T3: Tarefa de controle dos atuadores
 *
 * Esta tarefa é responsável por:
 *   - Bloquear em uma notificação de tarefa enviada por T2 (vTaskDecision).
 *   - Ler o SystemState atual (protegido por xStateMutex).
 *   - Definir o nível de saída GPIO de cada LED de acordo com o estado.
 *
 * Fluxo da notificação de tarefa:
 *   T2 chama xTaskNotifyGive(xTaskActuators) após atualizar g_state.
 *   T3 chama ulTaskNotifyTake(pdTRUE, portMAX_DELAY), que bloqueia até a
 *   notificação chegar. pdTRUE limpa o contador de notificações na saída, para
 *   que notificações sucessivas rápidas não se acumulem (uma atualização por ciclo).
 *   portMAX_DELAY faz com que a tarefa consuma zero CPU enquanto aguarda.
 *
 * Mapeamento de GPIO (definido em config.h):
 *   LED_HEATING_PIN → HIGH quando g_state.heat_on  é verdadeiro
 *   LED_DEHUM_PIN   → HIGH quando g_state.dehum_on é verdadeiro
 *
 * Nenhum acesso direto ao DHT ou à fila nesta tarefa — ela apenas lê o estado
 * que T2 já calculou, mantendo o controle dos atuadores simples e determinístico.
 */

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/semphr.h>

#include "config.h"
#include "types.h"

// Definido em main.cpp
extern SemaphoreHandle_t xStateMutex;
extern SystemState       g_state;

void vTaskActuators(void *pvParameters) {
    (void)pvParameters;

    // Garante que os LEDs começam no estado desligado (OFF).
    digitalWrite(LED_HEATING_PIN, LOW);
    digitalWrite(LED_DEHUM_PIN,   LOW);

    while (true) {
        // Bloqueia aqui até T2 enviar uma notificação de tarefa.
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);

        // --- Lê o estado --------------------
        bool heat_on, dehum_on;
        if (xSemaphoreTake(xStateMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
            heat_on  = g_state.heat_on;
            dehum_on = g_state.dehum_on;
            xSemaphoreGive(xStateMutex);
        } else {
            // Se não conseguir o mutex, pula este ciclo. O estado será aplicado na próxima notificação.
            Serial.println("[actuators] AVISO: timeout no xStateMutex");
            continue;
        }

        // --- Atualiza as saídas GPIO ----------------------------------------
        digitalWrite(LED_HEATING_PIN, heat_on  ? HIGH : LOW);
        digitalWrite(LED_DEHUM_PIN,   dehum_on ? HIGH : LOW);

        Serial.printf("[actuators] LED aquecimento=%s  LED desumid=%s\n", heat_on  ? "LIGADO" : "DESLIGADO", dehum_on ? "LIGADO" : "DESLIGADO");
    }
}
