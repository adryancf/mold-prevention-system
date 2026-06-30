# Sistema Embarcado em Tempo Real para Monitoramento e Controle de Umidade e Temperatura com Prevenção de Mofo

Projeto final da disciplina de **Sistemas Operacionais — UTFPR**.

Sistema embarcado executado em **ESP32 com FreeRTOS** que monitora temperatura e umidade com sensor DHT22, controla atuadores representados por LEDs e se comunica com uma aplicação desktop Python via **sockets TCP**.

---

## Estrutura do repositório

```text
mold-prevention-system/
├── docs/
│   ├── architecture.md   # Arquitetura detalhada: tarefas, primitivas, structs
│   └── protocol.md       # Protocolo JSON sobre TCP com exemplos de mensagens
├── firmware/
│   ├── README.md         # Pinagem, compilação, gravação no ESP32
│   ├── platformio.ini    # Configuração PlatformIO
│   ├── include/
│   │   ├── config.h      # Pinos, credenciais WiFi, constantes
│   │   └── types.h       # Structs: SensorReading, Config, SystemState
│   └── src/
│       ├── main.cpp          # Init WiFi, FreeRTOS primitives, task creation
│       ├── task_sensor.cpp   # T1: leitura DHT22 → xQueueSensor
│       ├── task_decision.cpp # T2: decisão lógica → g_state + notifica T3
│       ├── task_actuators.cpp# T3: aguarda notificação → GPIO dos LEDs
│       ├── task_comms.cpp    # T4: servidor TCP, protocolo JSON, NVS
│       └── storage.cpp       # Wrapper NVS (Preferences.h)
└── desktop/
    ├── README.md         # Instalação, execução, modo simulação
    ├── requirements.txt
    └── src/
        ├── main.py       # Ponto de entrada, argumentos CLI, orquestração
        ├── client.py     # Thread cliente TCP com reconexão automática
        ├── gui.py        # Janela Tkinter: leituras, estado, formulário
        └── chart.py      # Gráfico de histórico em tempo real (Matplotlib)
```

---

## Execução rápida

### Firmware

```bash
# Edite firmware/include/config.h com SSID e senha do WiFi
cd firmware
pip install platformio
pio run --target upload
pio device monitor   # anote o IP exibido
```

### Desktop

```bash
cd desktop
pip install -r requirements.txt

# Com ESP32 real:
python src/main.py --host <IP_DO_ESP32> --port 8080

# Sem hardware (modo simulação):
python src/main.py --simulate
```

---

## Arquitetura resumida

| Componente | Tecnologia |
|---|---|
| Microcontrolador | ESP32 |
| Sistema operacional | FreeRTOS (via Arduino framework) |
| Sensor | DHT22 (temperatura e umidade) |
| Comunicação | TCP socket — ESP32 é servidor, desktop é cliente |
| Protocolo | JSON sobre TCP, newline-delimitado |
| Atuadores | LEDs representando aquecimento e desumidificação |
| Persistência | NVS (Non-Volatile Storage) — biblioteca Preferences |
| Desktop | Python + Tkinter + Matplotlib |

### FreeRTOS — 4 tarefas concorrentes

| Tarefa | Responsabilidade |
|---|---|
| `vTaskSensor` | Leitura periódica do DHT22 → `xQueueSensor` |
| `vTaskDecision` | Consome fila, avalia limiares, atualiza estado global |
| `vTaskActuators` | Aguarda task notification de T2, atualiza GPIOs |
| `vTaskComms` | Servidor TCP, serialização JSON, persistência NVS |

### Primitivas de sincronização

| Primitiva | Protege |
|---|---|
| `xQueueSensor` | Amostras do sensor: T1 → T2 |
| `xConfigMutex` | Limiares compartilhados: T4 escreve, T2 lê |
| `xStateMutex` | Estado global: T2 escreve, T3 e T4 lêem |
| Task Notification | T2 sinaliza T3 após cada atualização de estado |

---

## Atendimento aos requisitos da disciplina

| Requisito | Implementação |
|---|---|
| ESP32 + FreeRTOS | `firmware/src/main.cpp` — 4 tarefas com `xTaskCreatePinnedToCore` |
| Sensor DHT22 | `task_sensor.cpp` — `dht.readTemperature()` / `dht.readHumidity()` |
| ≥ 4 tarefas concorrentes | `vTaskSensor`, `vTaskDecision`, `vTaskActuators`, `vTaskComms` |
| Fila de mensagens | `xQueueSensor` — `QueueHandle_t`, capacidade 5 slots |
| Mutex | `xConfigMutex`, `xStateMutex` — `SemaphoreHandle_t` |
| Semáforo / sinalização | Task Notification (T2 → T3) via `xTaskNotify` / `ulTaskNotifyTake` |
| Comunicação por sockets | `task_comms.cpp` — `WiFiServer` TCP na porta 8080 |
| Persistência NVS | `storage.cpp` — `Preferences.h`, namespace `mold_cfg` |
| Desktop Python | `desktop/src/` — Tkinter + Matplotlib |
| Atuadores LEDs | `task_actuators.cpp` — `digitalWrite` em GPIO 25 e 26 |
| Configuração remota | Mensagem `config` JSON do desktop → ESP32 → NVS |
| Recomendação de ventilação | `task_decision.cpp` — `buildVentRec()` → campo `rec` no JSON |

---

## Documentação

- **Arquitetura detalhada:** [`docs/architecture.md`](docs/architecture.md)
- **Protocolo de comunicação:** [`docs/protocol.md`](docs/protocol.md)
- **Firmware:** [`firmware/README.md`](firmware/README.md)
- **Desktop:** [`desktop/README.md`](desktop/README.md)
