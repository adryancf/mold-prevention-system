/*
 * main.cpp — Ponto de entrada do firmware de prevenção de mofo
 *
 * Responsabilidades:
 *   1. Inicializar o WiFi (o ESP32 é o servidor TCP; o desktop é o cliente).
 *   2. Criar todas as primitivas de sincronização do FreeRTOS.
 *   3. Criar e iniciar as quatro tarefas concorrentes.
 *
 * Primitivas FreeRTOS criadas aqui e utilizadas pelas tarefas:
 *   xQueueSensor   — fila que transporta SensorReading de T1 para T2
 *   xConfigMutex   — mutex que protege a struct Config compartilhada
 *   xStateMutex    — mutex que protege a struct SystemState compartilhada
 *
 * A notificação de tarefa (T2 → T3) é gerenciada pelo handle xTaskActuators,
 * definido aqui e passado para as tarefas que precisam dele.
 *
 * Os dados globais compartilhados vivem aqui para que todas as unidades de
 * tradução possam declará-los com extern.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>

#include "config.h"
#include "types.h"

// ---------------------------------------------------------------------------
// Primitivas de sincronização do FreeRTOS — definidas aqui, extern nos arquivos de tarefa
// ---------------------------------------------------------------------------
QueueHandle_t   xQueueSensor  = NULL;  /* T1 → T2: leituras do sensor            */
SemaphoreHandle_t xConfigMutex = NULL; /* protege g_config (T2 lê, T4 escreve)   */
SemaphoreHandle_t xStateMutex  = NULL; /* protege g_state  (T2 escreve, T3/T4 lêem)*/

// ---------------------------------------------------------------------------
// Handles de tarefa — xTaskActuators é necessário para T2 enviar notificações
// ---------------------------------------------------------------------------
TaskHandle_t xTaskActuators = NULL;

// ---------------------------------------------------------------------------
// Dados globais compartilhados — inicializados com valores seguros antes das tarefas
// ---------------------------------------------------------------------------
Config      g_config = { DEFAULT_TEMP_THRESH, DEFAULT_HUM_THRESH };
SystemState g_state  = { 0.0f, 0.0f, false, false, "Sistema iniciando...", 0 };

// ---------------------------------------------------------------------------
// Declarações antecipadas dos pontos de entrada das tarefas (definidas em seus próprios .cpp)
// ---------------------------------------------------------------------------
void vTaskSensor   (void *pvParameters);
void vTaskDecision (void *pvParameters);
void vTaskActuators(void *pvParameters);
void vTaskComms    (void *pvParameters);

// Declaração antecipada para inicialização do armazenamento
void storageLoadConfig(Config *cfg);

// ---------------------------------------------------------------------------
// setup() — executa uma vez na inicialização, antes do escalonador FreeRTOS
// ---------------------------------------------------------------------------
void setup() {
    Serial.begin(115200);
    Serial.println("[main] Iniciando sistema de prevencao de mofo...");

    // --- Configuração dos GPIOs ---------------------------------------------
    pinMode(LED_HEATING_PIN, OUTPUT);
    pinMode(LED_DEHUM_PIN,   OUTPUT);
    digitalWrite(LED_HEATING_PIN, LOW);
    digitalWrite(LED_DEHUM_PIN,   LOW);

    // --- Carrega limites persistidos do NVS ---------------------------------
    // Sobrescreve os valores padrão de g_config se houver valores salvos anteriormente.
    storageLoadConfig(&g_config);
    Serial.printf("[main] Limiares carregados — temp: %.1f C, hum: %.1f %%\n",
                  g_config.temp_thresh, g_config.hum_thresh);

    // --- Conexão WiFi -------------------------------------------------------
    Serial.printf("[main] Conectando ao WiFi: %s\n", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.printf("\n[main] WiFi conectado — IP: %s\n",
                  WiFi.localIP().toString().c_str());
    Serial.printf("[main] Servidor TCP do ESP32 aguardando na porta %d\n", TCP_PORT);

    // --- Criação das primitivas FreeRTOS ------------------------------------

    // Fila: transporta structs SensorReading de vTaskSensor para vTaskDecision.
    // A fila foi escolhida porque os dados do sensor são um fluxo de eventos discretos;
    // a tarefa de decisão deve processar cada amostra exatamente uma vez e em ordem.
    xQueueSensor = xQueueCreate(SENSOR_QUEUE_SIZE, sizeof(SensorReading));
    configASSERT(xQueueSensor != NULL);

    // Mutex: protege Config. Usado em vez de fila porque Config não é um fluxo — é um único valor autoritativo; exclusão mútua é suficiente.
    xConfigMutex = xSemaphoreCreateMutex();
    configASSERT(xConfigMutex != NULL);

    // Mutex: protege SystemState pelo mesmo motivo que xConfigMutex.
    xStateMutex  = xSemaphoreCreateMutex();
    configASSERT(xStateMutex != NULL);

    // --- Criação das tarefas ------------------------------------------------
    // T3 (vTaskActuators) é criada primeiro para que seu handle esteja disponível  antes de T2 (vTaskDecision) iniciar e possivelmente notificá-la imediatamente.
    xTaskCreatePinnedToCore(
        vTaskActuators, "actuators",
        TASK_ACTUATORS_STACK_SIZE, NULL,
        TASK_ACTUATORS_PRIORITY, &xTaskActuators,
        1  /* core 1 */
    );

    xTaskCreatePinnedToCore(
        vTaskSensor, "sensor",
        TASK_SENSOR_STACK_SIZE, NULL,
        TASK_SENSOR_PRIORITY, NULL,
        1
    );

    xTaskCreatePinnedToCore(
        vTaskDecision, "decision",
        TASK_DECISION_STACK_SIZE, NULL,
        TASK_DECISION_PRIORITY, NULL,
        1
    );

    xTaskCreatePinnedToCore(
        vTaskComms, "comms",
        TASK_COMMS_STACK_SIZE, NULL,
        TASK_COMMS_PRIORITY, NULL,
        0  /* core 0 — dedicado a I/O de rede */
    );

    Serial.println("[main] Todas as tarefas criadas. Escalonador em execucao.");
}

// loop() não é utilizado — toda a lógica vive nas tarefas FreeRTOS.
void loop() {
    vTaskDelay(portMAX_DELAY);
}
