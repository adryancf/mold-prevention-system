# Desktop — Aplicação Python

## Visão geral

A aplicação desktop conecta-se ao **servidor TCP do ESP32** e exibe temperatura, umidade, estado do sistema e histórico em tempo real. Também permite enviar novos limiares de operação ao ESP32.

**O desktop é o cliente TCP. O ESP32 é o servidor TCP.**

---

## Estrutura dos arquivos

```text
desktop/
├── README.md
├── requirements.txt
├── run.sh          # Script de execução recomendado (Linux/macOS)
└── src/
    ├── main.py     # Ponto de entrada, argumentos, orquestração de threads
    ├── client.py   # Thread socket TCP (cliente) com reconexão automática
    ├── gui.py      # Janela principal Tkinter
    └── chart.py    # Widget de gráfico em tempo real (Matplotlib + Tkinter)
```

---

## Requisitos

- Python 3.9 ou superior
- `tkinter` (incluído na instalação padrão do Python)
- `matplotlib` e `pillow` (dependências externas)

> **Importante:** use um `venv` para garantir que o Pillow instalado pelo pip tenha suporte a `ImageTk`, necessário para o backend TkAgg do matplotlib. Pacotes Pillow do sistema (via dnf/apt) podem não incluir esse módulo.

### Instalação

```bash
# No diretório desktop/
python3 -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

pip install -r requirements.txt
```

Se `tkinter` não estiver disponível no seu sistema:

```bash
# Fedora / RHEL
sudo dnf install python3-tkinter

# Ubuntu / Debian
sudo apt install python3-tk
```

---

## Execução

### Método recomendado — `run.sh` (Linux / macOS)

Use o `run.sh` em qualquer PC. Ele cria o `venv`, instala as dependências e inicia a aplicação automaticamente:

```bash
# No diretório desktop/

# Modo simulação (sem ESP32, para testes e apresentações)
./run.sh --simulate

# Modo normal (com ESP32 real — substitua pelo IP do monitor serial)
./run.sh --host 192.168.1.XXX --port 8080
```

Na **primeira execução** o script pode demorar alguns segundos para instalar as dependências. Nas execuções seguintes é imediato.

---

### Windows

O `run.sh` não roda no Windows. Execute manualmente:

```cmd
:: No diretório desktop\
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

:: Modo simulação
.venv\Scripts\python src\main.py --simulate

:: Modo normal
.venv\Scripts\python src\main.py --host 192.168.1.XXX --port 8080
```

---

### Por que não usar `python3 src/main.py` diretamente?

Em algumas distribuições Linux (Fedora, RHEL), o Pillow instalado pelo gerenciador de pacotes do sistema não inclui o módulo `ImageTk`, necessário para o gráfico embutido. O `run.sh` usa um `venv` isolado com o Pillow completo instalado via `pip`, evitando esse problema em qualquer máquina.

O modo simulação gera leituras sintéticas e exercita toda a interface gráfica sem necessidade de ESP32.

---

## Interface gráfica

| Área | Conteúdo |
|---|---|
| Header | Título + status de conexão em tempo real |
| Painel de leituras | Temperatura e umidade atuais (grandes, coloridos) |
| Painel de estado | LEDs de aquecimento e desumidificação + recomendação de ventilação |
| Gráfico | Histórico das últimas 60 leituras (≈ 2 min) — temperatura e umidade |
| Formulário | Edição e envio de limiares ao ESP32 + confirmação de sucesso/erro |

---

## Arquitetura de threads

```
Thread principal (Tkinter)
  └── Roda o event loop da GUI
  └── Lê data_queue via after() a cada 250 ms
  └── Chama client.send_config() no submit do formulário

Thread SocketClient (daemon)
  └── Conecta ao ESP32 via TCP
  └── Recebe JSON → push para data_queue
  └── Envia mensagens de config da _send_queue interna
```

Não há acesso ao Tkinter a partir da thread do socket — toda comunicação passa pela `data_queue` e pelo método `set_connection_status()` (que usa `after(0, ...)`).

---

## Protocolo

Ver [`docs/protocol.md`](../docs/protocol.md) para a especificação completa das mensagens JSON.
