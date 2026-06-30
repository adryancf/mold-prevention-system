"""
main.py — Ponto de entrada da aplicação desktop do Sistema de Prevenção de Mofo

Uso:
    python main.py [--host HOST] [--port PORT] [--simulate]

Argumentos:
    --host      Endereço IP do ESP32 (padrão: 192.168.1.100)
    --port      Porta TCP do servidor ESP32 (padrão: 8080)
    --simulate  Executa em modo simulação (sem hardware real necessário)

Arquitetura:
    Duas threads compartilham uma única queue.Queue:
    ┌─────────────────────────────────────────────────────┐
    │  Thread principal (Tkinter)                         │
    │    - Executa o loop de eventos da GUI               │
    │    - Verifica data_queue via after() a cada 250 ms  │
    │    - Chama client.send_config() ao submeter o form  │
    └──────────────────┬──────────────────────────────────┘
                       │  data_queue (queue.Queue)
    ┌──────────────────▼──────────────────────────────────┐
    │  Thread SocketClient (daemon)                       │
    │    - Conecta ao servidor TCP do ESP32               │
    │    - Recebe JSON, analisa e envia para data_queue   │
    │    - Envia mensagens de config de _send_queue       │
    └─────────────────────────────────────────────────────┘

Em modo simulação, uma SimulatorThread substitui o SocketClient.
Ela gera dados sintéticos plausíveis do sensor e os envia para o mesmo
data_queue, de forma que o código da GUI é exercitado sem hardware.
"""

import argparse
import math
import queue
import random
import threading
import time

from client import SocketClient
from gui    import MainWindow

DEFAULT_HOST = "192.168.1.100"
DEFAULT_PORT = 8080


# ──────────────────────────────────────────────────────────────────────────────
# Thread de simulação (substitui o SocketClient quando --simulate é passado)
# ──────────────────────────────────────────────────────────────────────────────

class SimulatorThread(threading.Thread):
    """
    Gera leituras simuladas do sensor e as envia para data_queue.
    Imita o mesmo formato de dict das mensagens reais analisadas pelo SocketClient.
    """

    def __init__(self, data_queue: queue.Queue):
        super().__init__(daemon=True, name="SimulatorThread")
        self.data_queue = data_queue
        self._running   = True
        self._seq       = 0
        self._temp_thresh = 20.0
        self._hum_thresh  = 60.0

    def send_config(self, temp_thresh: float, hum_thresh: float) -> None:
        """Aceita atualizações de config da GUI (ack simulado)."""
        self._temp_thresh = temp_thresh
        self._hum_thresh  = hum_thresh
        self.data_queue.put({"type": "ack", "status": "ok"})

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        t = 0.0
        while self._running:
            # Temperatura e umidade oscilando lentamente
            temp = 22.0 + 6.0 * math.sin(t / 30.0) + random.uniform(-0.3, 0.3)
            hum  = 65.0 + 15.0 * math.sin(t / 45.0 + 1.0) + random.uniform(-0.5, 0.5)

            heat  = temp < self._temp_thresh
            dehum = hum  > self._hum_thresh

            if not dehum and not heat:
                rec = "Condicoes adequadas. Ventilacao opcional."
            elif heat and dehum:
                rec = "Frio e umido. Ventilar brevemente (5-10 min) e depois fechar."
            elif not heat and dehum:
                rec = "Ambiente quente e umido. Ventilar por 15-30 min."
            else:
                rec = "Temperatura baixa. Evite ventilacao prolongada."

            self._seq += 1
            self.data_queue.put({
                "type": "reading",
                "seq":   self._seq,
                "temp":  round(temp, 1),
                "hum":   round(hum,  1),
                "heat":  heat,
                "dehum": dehum,
                "rec":   rec,
            })
            t += 2.0
            time.sleep(2.0)


# ──────────────────────────────────────────────────────────────────────────────
# Ponto de entrada
# ──────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mold Prevention System — Desktop Application"
    )
    parser.add_argument("--host",     default=DEFAULT_HOST,
                        help=f"ESP32 IP address (default: {DEFAULT_HOST})")
    parser.add_argument("--port",     default=DEFAULT_PORT, type=int,
                        help=f"ESP32 TCP port (default: {DEFAULT_PORT})")
    parser.add_argument("--simulate", action="store_true",
                        help="Run without real hardware (simulation mode)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    data_queue: queue.Queue = queue.Queue()

    if args.simulate:
        print("[main] Simulation mode enabled — no hardware required")
        worker = SimulatorThread(data_queue)
        send_config_fn = worker.send_config
    else:
        print(f"[main] Connecting to ESP32 at {args.host}:{args.port}")
        worker = None  # criado após a janela para que status_callback esteja disponível

    # Constrói a janela GUI primeiro para passar seu callback de status ao cliente
    window = MainWindow(
        data_queue    = data_queue,
        send_config_fn= (send_config_fn if args.simulate else None),  # corrigido abaixo
        simulate      = args.simulate,
    )

    if not args.simulate:
        client = SocketClient(
            host            = args.host,
            port            = args.port,
            data_queue      = data_queue,
            status_callback = window.set_connection_status,
        )
        window.send_config = client.send_config
        worker = client

    worker.start()

    try:
        window.mainloop()
    finally:
        worker.stop()


if __name__ == "__main__":
    main()
