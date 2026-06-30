# Firmware — ESP32 com FreeRTOS

## Visão geral

O firmware é construído com **PlatformIO** usando o framework **Arduino para ESP32**, que fornece o stack TCP/IP lwIP, as primitivas FreeRTOS nativas e o módulo `Preferences` (abstração da NVS).

O **ESP32 atua como servidor TCP**. O desktop conecta-se a ele como cliente.

---

## Estrutura dos arquivos

```text
firmware/
├── platformio.ini          # Configuração da plataforma e bibliotecas
├── include/
│   ├── config.h            # Pinos GPIO, credenciais WiFi, porta TCP, constantes
│   └── types.h             # Structs: SensorReading, Config, SystemState
└── src/
    ├── main.cpp            # Inicialização, criação de primitivas e tarefas
    ├── task_sensor.cpp     # T1: leitura do DHT22 → xQueueSensor
    ├── task_decision.cpp   # T2: decisão lógica → g_state + notifica T3
    ├── task_actuators.cpp  # T3: aguarda notificação → atualiza GPIOs
    ├── task_comms.cpp      # T4: servidor TCP, protocolo JSON, persistência
    └── storage.cpp         # Wrapper NVS (storageLoadConfig / storageSaveConfig)
```

---

## Pinagem

| Componente | Pino GPIO |
|---|---|
| DHT22 (dados) | 4 |
| LED Aquecimento | 25 |
| LED Desumidificação | 26 |

Ajuste as constantes em `include/config.h` se usar outra configuração de hardware.

---

## Configuração inicial

1. Edite `include/config.h` com as credenciais da sua rede WiFi:
   ```c
   #define WIFI_SSID     "SUA_REDE"
   #define WIFI_PASSWORD "SUA_SENHA"
   ```

2. Conecte o ESP32 via USB.

3. Compile e grave com PlatformIO:
   ```bash
   # Instale a CLI do PlatformIO (se necessário):
   pip install platformio

   # Dentro do diretório firmware/:
   pio run --target upload

   # Monitor serial:
   pio device monitor
   ```

4. Após a gravação, o monitor serial exibirá o IP do ESP32:
   ```
   [main] WiFi connected — IP: 192.168.1.XXX
   [main] ESP32 TCP server will listen on port 8080
   ```
   Use esse IP no cliente desktop.

---

## Arquitetura FreeRTOS

### Quatro tarefas concorrentes

| Tarefa | Prioridade | Core | Responsabilidade |
|---|---|---|---|
| `vTaskSensor` | 2 | 1 | Leitura periódica do DHT22 |
| `vTaskDecision` | 2 | 1 | Lógica de decisão e cálculo de estado |
| `vTaskActuators` | 1 | 1 | Controle dos LEDs via GPIO |
| `vTaskComms` | 3 | 0 | Servidor TCP e protocolo JSON |

### Primitivas de sincronização

| Primitiva | Tipo | Protege / Transporta |
|---|---|---|
| `xQueueSensor` | Fila (`QueueHandle_t`) | `SensorReading` de T1 para T2 |
| `xConfigMutex` | Mutex | `g_config` (T4 escreve, T2 lê) |
| `xStateMutex` | Mutex | `g_state` (T2 escreve, T3/T4 lêem) |
| Task Notification | Notificação de tarefa | T2 acorda T3 após atualizar o estado |

### Fluxo de task notification (T2 → T3)

```
T2 chama xTaskNotify(xTaskActuators, 0, eNoAction)
         │
         ▼
T3 retorna de ulTaskNotifyTake(pdTRUE, portMAX_DELAY)
         │
         ▼
T3 toma xStateMutex → lê g_state → atualiza GPIOs → libera mutex
```

T3 fica bloqueada sem consumir CPU enquanto não há notificação. A escolha de Task Notification em vez de semáforo binário é justificada por ser mais leve (sem alocação de objeto) quando há exatamente um produtor e um consumidor.

---

## Persistência (NVS)

Os limiares são persistidos no namespace `mold_cfg` usando a biblioteca `Preferences`:

```
temp_thr → float (limiar de temperatura)
hum_thr  → float (limiar de umidade)
```

Na inicialização, `storageLoadConfig()` é chamado antes da criação das tarefas. Se a NVS estiver vazia (primeiro boot), os valores padrão de `config.h` são mantidos.

---

## Dependências (PlatformIO)

```ini
lib_deps =
    adafruit/DHT sensor library @ ^1.4.6
    adafruit/Adafruit Unified Sensor @ ^1.1.14
    bblanchon/ArduinoJson @ ^6.21.5
```

## Validação em hardware real

Os seguintes aspectos **exigem hardware físico** para validação completa:

- Leitura real do sensor DHT22 (timing de 1-wire)
- Controle real dos LEDs via GPIO
- Conectividade WiFi (SSID/senha reais)
- Persistência na NVS (testável via reinício do ESP32)
