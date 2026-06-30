#pragma once

#include <stdint.h>
#include <stdbool.h>

/* =============================================================================
 * types.h — Estruturas de dados compartilhadas para o sistema de tarefas FreeRTOS
 *
 * Três structs definem o fluxo completo de dados da aplicação embarcada:
 *
 *   SensorReading   → produzida por T1 (vTaskSensor), consumida por T2 (vTaskDecision)
 *                     transportada por xQueueSensor (fila FreeRTOS)
 *
 *   Config          → escrita por T4 (vTaskComms) quando novos limiares chegam,
 *                     lida por T2 (vTaskDecision) a cada ciclo de decisão
 *                     protegida por xConfigMutex (mutex FreeRTOS)
 *                     persistida no NVS entre ciclos de energia
 *
 *   SystemState     → escrita por T2 (vTaskDecision) após cada decisão,
 *                     lida por T3 (vTaskActuators) e T4 (vTaskComms)
 *                     protegida por xStateMutex (mutex FreeRTOS)
 *                     T2 envia uma notificação de tarefa para T3 após cada escrita
 * ============================================================================= */

/**
 * SensorReading — dados brutos do DHT22, encapsulados por T1.
 *
 * valid = false sinaliza uma leitura falha (erro de CRC ou timeout do sensor).
 * T2 deve descartar leituras inválidas sem atualizar o estado.
 */
typedef struct {
    float    temp;       /* Temperatura em graus Celsius                   */
    float    hum;        /* Umidade relativa em porcentagem                */
    uint32_t timestamp;  /* millis() no momento da leitura                 */
    bool     valid;      /* false se o DHT22 retornou um erro              */
} SensorReading;

/**
 * Config — limiares de operação que guiam a lógica de decisão.
 *
 * Compartilhado entre:
 *   - T2  (leitor): compara valores do sensor com os limiares
 *   - T4  (escritor): recebe novos valores do desktop via socket
 *
 * Mutex: xConfigMutex
 * Escolhido em vez de uma fila porque Config não é um fluxo de eventos, mas um único
 * valor autoritativo que pode ser sobrescrito repetidamente; um mutex protege
 * a seção crítica sem exigir que um consumidor esvazie itens.
 */
typedef struct {
    float temp_thresh;   /* Abaixo desta temperatura (°C), ativa o LED de aquecimento  */
    float hum_thresh;    /* Acima desta umidade (%),       ativa o LED de desumidificação */
} Config;

/**
 * SystemState — saída calculada pela tarefa de decisão.
 *
 * Compartilhado entre:
 *   - T2  (escritor): atualiza após cada leitura bem-sucedida do sensor
 *   - T3  (leitor): lê para controlar as saídas físicas GPIO (LEDs)
 *   - T4  (leitor): lê para serializar e enviar ao desktop
 *
 * Mutex: xStateMutex
 * Escolhido pelo mesmo motivo que xConfigMutex: múltiplos leitores, um escritor,
 * sem necessidade de ordem FIFO — exclusão mútua é suficiente.
 *
 * Sinalização: após T2 escrever um novo SystemState, envia uma notificação de tarefa
 * (xTaskNotify) para o handle de T3. T3 bloqueia em ulTaskNotifyTake() e acorda
 * apenas quando sinalizado explicitamente, evitando busy-waiting ou polling.
 *
 * vent_rec: recomendação textual de ventilação, terminada em null, máx. 127 chars.
 * seq:      contador monotonicamente crescente; incrementado a cada atualização.
 *           Permite que T4 detecte se o estado mudou desde o último envio.
 */
typedef struct {
    float    temp;
    float    hum;
    bool     heat_on;        /* true → LED de aquecimento deve estar LIGADO    */
    bool     dehum_on;       /* true → LED de desumidificação deve estar LIGADO */
    char     vent_rec[128];  /* String de recomendação de ventilação            */
    uint32_t seq;            /* Contador de sequência de atualização            */
} SystemState;
