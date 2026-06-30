#pragma once

/* =============================================================================
 * config.h — Configuração centralizada em tempo de compilação
 *
 * Edite WIFI_SSID e WIFI_PASSWORD antes de gravar o firmware.
 * Todos os outros valores podem ser alterados sem quebrar o contrato do sistema.
 * ============================================================================= */

// ---------------------------------------------------------------------------
// Credenciais WiFi
// ---------------------------------------------------------------------------
#define WIFI_SSID     ""
#define WIFI_PASSWORD ""

// ---------------------------------------------------------------------------
// Servidor TCP (ESP32 é o servidor; o cliente desktop conecta nesta porta)
// ---------------------------------------------------------------------------
#define TCP_PORT      8080

// ---------------------------------------------------------------------------
// Atribuições dos pinos GPIO
// ---------------------------------------------------------------------------
#define DHT_PIN           4    // Pino de dados do sensor DHT22
#define LED_HEATING_PIN   25   // LED representando o atuador de aquecimento
#define LED_DEHUM_PIN     26   // LED representando o atuador de desumidificação

// ---------------------------------------------------------------------------
// Tipo do sensor DHT — deve corresponder ao sensor físico
// ---------------------------------------------------------------------------
#define DHT_TYPE DHT22

// ---------------------------------------------------------------------------
// Intervalo de amostragem do sensor
// ---------------------------------------------------------------------------
#define SENSOR_INTERVAL_MS 2000   // 2 s entre leituras

// ---------------------------------------------------------------------------
// Limiares padrão de operação (sobrescritos pelos valores do NVS quando presentes)
// ---------------------------------------------------------------------------
#define DEFAULT_TEMP_THRESH  20.0f   // °C — abaixo disso, o aquecimento é ativado
#define DEFAULT_HUM_THRESH   60.0f   // %  — acima disso, a desumidificação é ativada

// ---------------------------------------------------------------------------
// Configuração das tarefas FreeRTOS
// ---------------------------------------------------------------------------
#define SENSOR_QUEUE_SIZE             5      // Número de slots SensorReading em xQueueSensor

#define TASK_SENSOR_STACK_SIZE        4096
#define TASK_DECISION_STACK_SIZE      4096
#define TASK_ACTUATORS_STACK_SIZE     2048
#define TASK_COMMS_STACK_SIZE         8192

// Prioridade 3 (maior) → comms, para que I/O de socket não sofra starvation
// Prioridade 2         → sensor + decision, sensíveis ao tempo
// Prioridade 1 (menor) → actuators, acordada apenas por notificação de tarefa
#define TASK_SENSOR_PRIORITY          2
#define TASK_DECISION_PRIORITY        2
#define TASK_ACTUATORS_PRIORITY       1
#define TASK_COMMS_PRIORITY           3

// ---------------------------------------------------------------------------
// Chaves NVS (Non-Volatile Storage)
// ---------------------------------------------------------------------------
#define NVS_NAMESPACE        "mold_cfg"
#define NVS_KEY_TEMP_THRESH  "temp_thr"
#define NVS_KEY_HUM_THRESH   "hum_thr"
