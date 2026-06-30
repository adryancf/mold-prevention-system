/*
 * task_sensor.cpp — T1: Tarefa de aquisição de dados do sensor
 *
 * Esta tarefa é responsável por:
 *   - Ler periodicamente temperatura e umidade do DHT22.
 *   - Encapsular cada leitura em uma struct SensorReading.
 *   - Enviar a struct para xQueueSensor para que T2 (vTaskDecision) consuma.
 *
 * A tarefa executa a cada SENSOR_INTERVAL_MS milissegundos usando vTaskDelayUntil(),
 * que garante um período estável independente do tempo gasto na leitura do DHT.
 *
 * Se o DHT22 retornar NaN (erro de comunicação / falha de CRC), a leitura ainda
 * é enfileirada com valid = false para que T2 possa contabilizar e registrar falhas.
 *
 * Nenhum mutex é necessário aqui pois xQueueSensor é o único recurso compartilhado
 * acessado por esta tarefa, e filas do FreeRTOS são intrinsecamente thread-safe.
 */

#include <Arduino.h>
#include <DHT.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>

#include "config.h"
#include "types.h"

// Definido em main.cpp
extern QueueHandle_t xQueueSensor;

static DHT dht(DHT_PIN, DHT_TYPE);

void vTaskSensor(void *pvParameters) {
    (void)pvParameters;

    dht.begin();

    // Warm-up: o DHT22 precisa de ~1 s após ligar antes da primeira leitura válida.
    vTaskDelay(pdMS_TO_TICKS(1500));

    TickType_t xLastWakeTime = xTaskGetTickCount();

    while (true) {
        SensorReading reading;
        reading.timestamp = (uint32_t)millis();
        reading.temp      = dht.readTemperature();
        reading.hum       = dht.readHumidity();
        reading.valid     = !(isnan(reading.temp) || isnan(reading.hum));

        if (!reading.valid) {
            Serial.println("[sensor] DHT22 read failed — enqueuing invalid sample");
        } else {
            Serial.printf("[sensor] temp=%.1f °C  hum=%.1f %%\n",
                          reading.temp, reading.hum);
        }

        // xQueueSend bloqueará por até 100 ms se a fila estiver cheia.
        // Se expirar o tempo, a amostra é descartada e um aviso é registrado.
        if (xQueueSend(xQueueSensor, &reading, pdMS_TO_TICKS(100)) != pdTRUE) {
            Serial.println("[sensor] WARNING: xQueueSensor full — sample dropped");
        }

        // Período estável: próximo wake-up relativo a xLastWakeTime, não ao momento atual.
        // Isso compensa o tempo gasto na leitura do DHT.
        vTaskDelayUntil(&xLastWakeTime, pdMS_TO_TICKS(SENSOR_INTERVAL_MS));
    }
}
