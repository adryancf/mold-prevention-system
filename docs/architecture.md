# Arquitetura do Sistema

## Visão geral

O sistema é composto por dois blocos que se comunicam por uma conexão **TCP bidirecional com mensagens JSON**:

```
┌─────────────────────────────────┐          ┌──────────────────────────────────┐
│        ESP32 (servidor TCP)     │          │      Desktop Python (cliente TCP) │
│                                 │  socket  │                                  │
│  FreeRTOS — 4 tarefas           │◄────────►│  Thread GUI (Tkinter)            │
│  concorrentes                   │   JSON   │  Thread SocketClient             │
└─────────────────────────────────┘          └──────────────────────────────────┘
```

**O ESP32 é o servidor TCP** (bind + listen + accept).
**O desktop é o cliente TCP** (connect).

---

## Bloco 1 — Firmware (ESP32 + FreeRTOS)

### Diagrama de tarefas e primitivas

```
DHT22
  │  leitura física
  ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  T1: vTaskSensor                                                           │
│  Prioridade 2 | Core 1                                                     │
│  Lê temperatura e umidade do DHT22 a cada 2 s.                            │
│  Encapsula em SensorReading e envia para xQueueSensor.                    │
└────────────────────────────┬───────────────────────────────────────────────┘
                             │ xQueueSensor (QueueHandle_t)
                             │ FIFO de SensorReading — thread-safe por design
                             ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  T2: vTaskDecision                                                         │
│  Prioridade 2 | Core 1                                                     │
│  Bloqueia em xQueueReceive — acorda quando há amostra disponível.         │
│  Lê g_config (xConfigMutex) para obter os limiares atuais.                │
│  Computa: heat_on, dehum_on, vent_rec.                                     │
│  Escreve g_state (xStateMutex).                                            │
│  Envia task notification a T3 via xTaskNotify().                           │
└───────┬────────────────────────────────────────────────┬───────────────────┘
        │ xTaskNotify(xTaskActuators)                    │ xStateMutex (leitura)
        ▼                                                ▼
┌───────────────────────────┐               ┌───────────────────────────────────┐
│  T3: vTaskActuators       │               │  T4: vTaskComms                   │
│  Prioridade 1 | Core 1    │               │  Prioridade 3 | Core 0            │
│                           │               │                                   │
│  Bloqueia em              │               │  Servidor TCP: aceita conexão     │
│  ulTaskNotifyTake()       │               │  do desktop.                      │
│  (sem CPU enquanto espera)│               │                                   │
│                           │               │  ENVIO: a cada 2,5 s, lê g_state  │
│  Lê g_state               │               │  (xStateMutex) e serializa JSON.  │
│  (xStateMutex)            │               │                                   │
│                           │               │  RECEPÇÃO: parse JSON de config,  │
│  Atualiza GPIOs:          │               │  valida, atualiza g_config        │
│  LED_HEATING_PIN          │               │  (xConfigMutex), salva na NVS.    │
│  LED_DEHUM_PIN            │               │                                   │
└───────────────────────────┘               └───────────────────────────────────┘
```

### Primitivas de sincronização

#### `xQueueSensor` — Fila de mensagens

**Tipo:** `QueueHandle_t`  
**Capacidade:** 5 slots de `SensorReading`  
**Produtores:** T1  
**Consumidores:** T2

**Justificativa:** A fila é a primitiva correta para transportar um fluxo ordenado de amostras entre produtor e consumidor. Garante que cada amostra seja processada exatamente uma vez, em ordem de chegada, sem a necessidade de mutex ou seção crítica explícita no ponto de comunicação.

#### `xConfigMutex` — Mutex de configuração

**Tipo:** `SemaphoreHandle_t` (mutex)  
**Dado protegido:** `g_config` (struct `Config`)  
**Escritores:** T4 (quando recebe nova configuração do desktop)  
**Leitores:** T2 (a cada ciclo de decisão)

**Justificativa:** `Config` não é um fluxo de eventos — é um único valor autoritativo que pode ser sobrescrito várias vezes. Um mutex oferece exclusão mútua suficiente sem a semântica de fila. A escolha de mutex (em vez de semáforo binário) é por dar suporte a priority inheritance no FreeRTOS, evitando inversão de prioridade entre T2 e T4.

#### `xStateMutex` — Mutex de estado

**Tipo:** `SemaphoreHandle_t` (mutex)  
**Dado protegido:** `g_state` (struct `SystemState`)  
**Escritores:** T2  
**Leitores:** T3, T4

**Justificativa:** Mesma razão que `xConfigMutex`. T3 e T4 lêem o estado computado por T2; um mutex evita leituras parcialmente escritas.

#### Task Notification (T2 → T3)

**Mecanismo:** `xTaskNotify()` / `ulTaskNotifyTake()`

**Fluxo:**
1. T2 escreve o novo estado em `g_state` (dentro de `xStateMutex`).
2. T2 chama `xTaskNotify(xTaskActuators, 0, eNoAction)`.
3. T3 retorna de `ulTaskNotifyTake(pdTRUE, portMAX_DELAY)`.
4. T3 toma `xStateMutex`, lê `g_state`, libera o mutex.
5. T3 escreve nos GPIOs.

**Justificativa:** Task Notification é a escolha mais leve do FreeRTOS para sinalização de um único produtor para um único consumidor — não requer alocação de objeto separado (ao contrário do semáforo binário) e é diretamente suportada por Priority Inheritance via o scheduler.

---

### Estruturas de dados

#### `SensorReading`
Produzida por T1, consumida por T2. Transportada pela `xQueueSensor`.

```c
typedef struct {
    float    temp;       // Temperatura em °C
    float    hum;        // Umidade relativa em %
    uint32_t timestamp;  // millis() no momento da leitura
    bool     valid;      // false se o DHT22 retornou erro
} SensorReading;
```

#### `Config`
Configuração operacional do sistema. Protegida por `xConfigMutex`. Persistida na NVS.

```c
typedef struct {
    float temp_thresh;   // Abaixo deste valor (°C): aquecimento ativo
    float hum_thresh;    // Acima deste valor (%): desumidificação ativa
} Config;
```

#### `SystemState`
Saída computada do sistema. Protegida por `xStateMutex`.

```c
typedef struct {
    float    temp;           // Última leitura de temperatura
    float    hum;            // Última leitura de umidade
    bool     heat_on;        // true → LED de aquecimento deve estar ligado
    bool     dehum_on;       // true → LED de desumidificação deve estar ligado
    char     vent_rec[128];  // Recomendação de ventilação (string)
    uint32_t seq;            // Contador de atualizações (incrementado por T2)
} SystemState;
```

O campo `seq` permite a T4 detectar se o estado mudou desde o último envio, evitando transmissões redundantes.

---

### Mapeamento de GPIO

| Componente | Pino | Descrição |
|---|---|---|
| DHT22 (dados) | GPIO 4 | Sensor de temperatura e umidade |
| LED Aquecimento | GPIO 25 | Representa o atuador de aquecimento |
| LED Desumidificação | GPIO 26 | Representa o atuador de desumidificação |

---

## Bloco 2 — Desktop (Python)

### Arquitetura de threads

```
Processo Python
  ├── Thread principal (Tkinter event loop)
  │     - Roda gui.mainloop()
  │     - Lê data_queue via after() a cada 250 ms
  │     - Atualiza widgets na tela
  │     - Chama client.send_config() no submit do formulário
  │
  └── Thread SocketClient (daemon)
        - Conecta ao ESP32 (TCP client → ESP32 server)
        - Recebe JSON e faz push para data_queue
        - Monitora _send_queue interna para mensagens de saída
        - Reconecta automaticamente em caso de queda
```

**Comunicação inter-thread:**
- `data_queue` (`queue.Queue`) — SocketClient produz, Tkinter consome via `after()`
- `_send_queue` interna ao SocketClient — Tkinter produz via `send_config()`, SocketClient consome

Nenhuma chamada direta ao Tkinter é feita a partir da thread do socket. O método `set_connection_status()` usa `after(0, ...)` para garantir execução no thread principal.

---

## Persistência de configuração

Os limiares são armazenados na partição NVS do ESP32 usando a biblioteca `Preferences`:

| Namespace | Chave | Tipo | Significado |
|---|---|---|---|
| `mold_cfg` | `temp_thr` | `float` | Limiar de temperatura (°C) |
| `mold_cfg` | `hum_thr` | `float` | Limiar de umidade (%) |

Na inicialização, `storageLoadConfig()` é chamado antes da criação das tarefas FreeRTOS. Se a NVS estiver vazia (primeiro boot), os valores padrão de `config.h` são mantidos.

---

## Atendimento aos requisitos da disciplina

| Requisito | Como é atendido |
|---|---|
| FreeRTOS com ≥ 4 tarefas | `vTaskSensor`, `vTaskDecision`, `vTaskActuators`, `vTaskComms` |
| Comunicação por sockets | Servidor TCP no ESP32, cliente TCP no desktop |
| Fila de mensagens | `xQueueSensor` transporta `SensorReading` de T1 para T2 |
| Mutex | `xConfigMutex` e `xStateMutex` protegem dados compartilhados |
| Semáforo / sinalização | Task Notification de T2 para T3 |
| Persistência (NVS) | `storage.cpp` via `Preferences.h` |
| Aplicação desktop | Python + Tkinter + Matplotlib |
| Protocolo de comunicação | JSON sobre TCP (documentado em `docs/protocol.md`) |
