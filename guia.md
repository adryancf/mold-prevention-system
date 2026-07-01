Seu ESP32 ainda não está aparecendo como porta serial: o Windows só detectou a `COM1`, e o PlatformIO ainda não está instalado. Primeiro precisamos resolver a conexão USB.

### 1. Faça o ESP32 aparecer no Windows

- Use um cabo USB que transmita dados — muitos cabos servem apenas para carga.
- Tente outra porta USB.
- Abra **Gerenciador de Dispositivos → Portas (COM e LPT)**.
- Procure algo como:
  - `Silicon Labs CP210x (COMx)`
  - `USB-SERIAL CH340 (COMx)`
  - `USB Serial/JTAG (COMx)`

Se aparecer como dispositivo desconhecido, instale o driver CP210x ou CH340 correspondente ao chip USB da placa. Depois, desconecte e reconecte. A porta precisa ser diferente da `COM1`, por exemplo `COM3`.

### 2. Confira a montagem

Para o DHT22:

| DHT22 | ESP32 |
|---|---|
| VCC | 3V3 |
| DATA | GPIO 4 |
| GND | GND |

Use um resistor de aproximadamente `10 kΩ` entre DATA e 3V3 se seu DHT22 não estiver em um módulo que já tenha resistor.

LEDs:

- GPIO 25 → resistor de 220–330 Ω → LED de aquecimento → GND
- GPIO 26 → resistor de 220–330 Ω → LED de desumidificação → GND

### 3. Configure o Wi-Fi

Abra [config.h](C:/Users/eduds/Documents/mold-prevention-system/firmware/include/config.h:14) e preencha:

```cpp
#define WIFI_SSID     "NOME_DA_REDE"
#define WIFI_PASSWORD "SENHA_DA_REDE"
```

O computador e o ESP32 devem estar na mesma rede. Use uma rede de 2,4 GHz; o ESP32 clássico não conecta em Wi-Fi exclusivamente 5 GHz.

### 4. Instale o PlatformIO

No PowerShell:

```powershell
cd C:\Users\eduds\Documents\mold-prevention-system
py -m pip install --user platformio
py -m platformio --version
```

Compile o firmware:

```powershell
cd firmware
py -m platformio run
```

### 5. Grave no ESP32

Substitua `COM3` pela porta observada no Gerenciador de Dispositivos:

```powershell
py -m platformio run --target upload --upload-port COM3
```

Se aparecer `Connecting...` repetidamente:

1. Segure o botão **BOOT**.
2. Inicie novamente o comando.
3. Solte o BOOT quando a gravação começar.

### 6. Confira o monitor serial

```powershell
py -m platformio device monitor --port COM3 --baud 115200
```

Pressione `EN`/`RESET` na placa. A saída esperada inclui:

```text
[main] WiFi conectado — IP: 192.168...
[main] Todas as tarefas criadas
[sensor] temp=... hum=...
```

Anote o IP. Saia do monitor com `Ctrl+C`.

Se aparecer `Falha na leitura do DHT22`, confira alimentação, GPIO 4, resistor e se o sensor realmente é DHT22.

### 7. Rode a interface no Windows

Em outro PowerShell:

```powershell
cd C:\Users\eduds\Documents\mold-prevention-system\desktop
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe src\main.py --host 192.168.1.XXX --port 8080
```

Troque pelo IP mostrado no monitor serial.

Para testar somente a interface, sem o ESP32:

```powershell
.\.venv\Scripts\python.exe src\main.py --simulate
```

Funcionando corretamente, a interface ficará conectada, mostrará novas medições a cada dois segundos e permitirá alterar os limiares. O principal bloqueio agora é fazer a placa aparecer como uma porta `COMx`.