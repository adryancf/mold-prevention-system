"""
client.py — Thread cliente de socket TCP

Responsabilidades:
    - Executar em uma thread daemon em segundo plano, mantendo a GUI responsiva.
    - Conectar ao servidor TCP do ESP32 (host:porta); reconectar automaticamente em caso de falha.
    - Receber mensagens JSON delimitadas por nova linha e enviar dicts analisados para data_queue.
    - Expor send_config() para que a thread da GUI possa enfileirar atualizações de limiares.

Thread safety:
    - data_queue  : queue.Queue thread-safe usada para passar dados para a thread da GUI.
    - _send_queue : queue.Queue interna usada para passar mensagens de saída da
                    thread da GUI para a thread do socket sem bloquear a GUI.
    - status_callback é chamada da thread do socket; deve ser segura para chamar
      de uma thread não-principal (o loop de eventos do Tkinter trata isso via after()).
"""

import json
import queue
import socket
import threading
import time
from typing import Callable, Optional


class SocketClient(threading.Thread):
    """
    Thread em segundo plano que gerencia a conexão TCP com o ESP32.

    O ESP32 é o servidor TCP (ele faz bind e escuta).
    Esta classe é o cliente TCP (chama connect()).
    """

    RECONNECT_DELAY_S = 3.0   # Espera entre tentativas de reconexão
    CONNECT_TIMEOUT_S = 5.0   # Timeout para estabelecer a conexão TCP
    RECV_BUFFER_SIZE  = 2048  # Bytes por chamada recv()

    def __init__(
        self,
        host: str,
        port: int,
        data_queue: queue.Queue,
        status_callback: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(daemon=True, name="SocketClientThread")
        self.host = host
        self.port = port
        self.data_queue = data_queue
        self.status_callback = status_callback

        self._sock: Optional[socket.socket] = None
        self._running = True
        self._send_queue: queue.Queue[str] = queue.Queue()

    # ------------------------------------------------------------------
    # API pública (segura para chamar de qualquer thread)
    # ------------------------------------------------------------------

    def send_config(self, temp_thresh: float, hum_thresh: float) -> None:
        """Enfileira uma mensagem 'config' para ser enviada ao ESP32."""
        msg = json.dumps({
            "type": "config",
            "temp_thresh": round(temp_thresh, 1),
            "hum_thresh":  round(hum_thresh,  1),
        }) + "\n"
        self._drop_pending_configs()
        self._send_queue.put(msg)

    def stop(self) -> None:
        """Sinaliza a thread para parar e fecha o socket."""
        self._running = False
        sock = self._sock
        if sock:
            try:
                sock.close()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _set_status(self, msg: str) -> None:
        if self.status_callback:
            self.status_callback(msg)

    def _drop_pending_configs(self) -> None:
        """Mantem apenas o comando de configuracao mais recente."""
        while True:
            try:
                self._send_queue.get_nowait()
            except queue.Empty:
                return

    def _connect(self) -> bool:
        """
        Tenta conectar ao servidor TCP do ESP32.
        Tenta novamente a cada RECONNECT_DELAY_S até conectar ou ser parado.
        Retorna True em sucesso, False se parado antes de conectar.
        """
        while self._running:
            sock: Optional[socket.socket] = None
            try:
                sock = socket.create_connection(
                    (self.host, self.port),
                    timeout=self.CONNECT_TIMEOUT_S,
                )
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self._sock = sock
                self._set_status(f"Conectado a {self.host}:{self.port}")
                return True
            except (ConnectionRefusedError, OSError, socket.timeout) as exc:
                if sock:
                    try:
                        sock.close()
                    except OSError:
                        pass
                self._set_status(f"Desconectado — reconectando em {self.RECONNECT_DELAY_S:.0f}s ({exc})")
                time.sleep(self.RECONNECT_DELAY_S)
        return False

    def _flush_send_queue(self) -> bool:
        """Envia todas as mensagens de saída enfileiradas. Retorna False em erro de socket."""
        if not self._sock:
            return False

        while True:
            try:
                msg: str = self._send_queue.get_nowait()
            except queue.Empty:
                return True

            try:
                self._sock.sendall(msg.encode("utf-8"))
            except OSError:
                self._send_queue.put(msg)
                return False

    # ------------------------------------------------------------------
    # Loop principal da thread
    # ------------------------------------------------------------------

    def run(self) -> None:
        import select

        while self._running:
            if not self._connect():
                break  # _running foi definido como False

            # Muda para não-bloqueante após conectar para que select() controle o I/O.
            self._sock.setblocking(False)
            recv_buffer = ""

            try:
                while self._running:
                    # Verifica se há dados para escrever
                    has_pending_send = not self._send_queue.empty()

                    # select() aguarda: socket legível, ou socket gravável
                    # (apenas quando há algo para enviar), com timeout de 0,5 s
                    # para que o loop também verifique self._running periodicamente.
                    write_fds = [self._sock] if has_pending_send else []
                    try:
                        readable, writable, _ = select.select(
                            [self._sock], write_fds, [], 0.5
                        )
                    except (ValueError, OSError):
                        break  # socket foi fechado

                    # --- Envia mensagens de saída pendentes ---
                    if writable:
                        if not self._flush_send_queue():
                            break

                    # --- Recebe dados chegando ---
                    if readable:
                        try:
                            chunk = self._sock.recv(self.RECV_BUFFER_SIZE)
                        except BlockingIOError:
                            chunk = b""
                        if not chunk:
                            break  # servidor fechou a conexão
                        recv_buffer += chunk.decode("utf-8", errors="replace")

                    # Analisa todas as mensagens completas terminadas em nova linha no buffer
                    while "\n" in recv_buffer:
                        line, recv_buffer = recv_buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            self.data_queue.put(data)
                        except json.JSONDecodeError as exc:
                            print(f"[client] Erro ao parsear JSON: {exc} — linha: {line!r}")

            except OSError as exc:
                self._set_status(f"Erro de socket: {exc}")
            finally:
                if self._sock:
                    try:
                        self._sock.close()
                    except OSError:
                        pass
                    self._sock = None

            if self._running:
                self._set_status(f"Conexão perdida. Reconectando em {self.RECONNECT_DELAY_S:.0f}s...")
                time.sleep(self.RECONNECT_DELAY_S)

        self._set_status("Cliente encerrado.")
