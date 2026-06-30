"""
gui.py — Janela principal Tkinter da aplicação desktop do Sistema de Prevenção de Mofo

Layout:
    ┌─────────────────────────────────────────────────┐
    │  Cabeçalho: título + status de conexão           │
    ├──────────────────┬──────────────────────────────┤
    │  Valores atuais  │  Estado do sistema + rec. vent│
    │  (temp, umidade) │                              │
    ├──────────────────┴──────────────────────────────┤
    │  Gráfico ao vivo (histórico de temp. e umidade)  │
    ├─────────────────────────────────────────────────┤
    │  Formulário de configuração de limiares          │
    └─────────────────────────────────────────────────┘

Thread safety:
    Todas as operações Tkinter rodam na thread principal.
    A GUI verifica data_queue via mecanismo after() do Tkinter a cada
    POLL_MS milissegundos. Isso evita chamadas Tkinter diretas entre threads.
"""

import queue
import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, Optional

from chart import LiveChart

POLL_MS = 250   # Com que frequência a GUI verifica a fila de dados (ms)


class MainWindow(tk.Tk):
    """
    Janela principal da aplicação.

    Parâmetros
    ----------
    data_queue : queue.Queue
        Preenchida pela thread SocketClient com dicts analisados do JSON.
    send_config_fn : Callable
        Chamada com (temp_thresh: float, hum_thresh: float) quando o usuário
        submete novos limiares. Executa na thread principal; o SocketClient
        cuida do envio real pela rede.
    simulate : bool
        Se True, o cabeçalho exibe um indicador de simulação.
    """

    # ── Paleta de cores ─────────────────────────────────────────────────
    BG        = "#1E1E2E"
    SURFACE   = "#2A2A3E"
    ACCENT    = "#7C3AED"         # Roxo
    TEMP_CLR  = "#EF5350"         # Vermelho
    HUM_CLR   = "#42A5F5"         # Azul
    OK_CLR    = "#66BB6A"         # Verde
    WARN_CLR  = "#FFA726"         # Laranja
    ERR_CLR   = "#EF5350"
    FG        = "#E2E2E2"
    FG_DIM    = "#888AAA"

    def __init__(
        self,
        data_queue: queue.Queue,
        send_config_fn: Callable[[float, float], None],
        simulate: bool = False,
    ):
        super().__init__()
        self.data_queue    = data_queue
        self.send_config   = send_config_fn
        self.simulate      = simulate

        # Valores atuais dos limiares (atualizados quando ack chega)
        self._temp_thresh  = tk.DoubleVar(value=20.0)
        self._hum_thresh   = tk.DoubleVar(value=60.0)

        self._build_window()
        self._build_header()
        self._build_readings_panel()
        self._build_state_panel()
        self._build_chart()
        self._build_config_panel()

        # Inicia a verificação da fila de dados
        self.after(POLL_MS, self._poll_queue)

    # ──────────────────────────────────────────────────────────────────
    # Configuração da janela
    # ──────────────────────────────────────────────────────────────────

    def _build_window(self) -> None:
        self.title("Sistema de Prevenção de Mofo")
        self.configure(bg=self.BG)
        self.resizable(True, True)
        self.minsize(760, 640)

        # Fontes customizadas
        self._font_title   = tkfont.Font(family="Helvetica", size=16, weight="bold")
        self._font_value   = tkfont.Font(family="Helvetica", size=32, weight="bold")
        self._font_label   = tkfont.Font(family="Helvetica", size=10)
        self._font_small   = tkfont.Font(family="Helvetica", size=9)
        self._font_mono    = tkfont.Font(family="Courier",   size=9)

    # ──────────────────────────────────────────────────────────────────
    # Cabeçalho
    # ──────────────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        hdr = tk.Frame(self, bg=self.SURFACE, pady=10)
        hdr.pack(fill=tk.X, padx=0, pady=(0, 2))

        sim_suffix = "  [SIMULAÇÃO]" if self.simulate else ""
        tk.Label(
            hdr, text=f"🍃 Sistema de Prevenção de Mofo{sim_suffix}",
            font=self._font_title, fg=self.FG, bg=self.SURFACE
        ).pack(side=tk.LEFT, padx=16)

        self._status_var = tk.StringVar(value="Conectando...")
        self._status_lbl = tk.Label(
            hdr, textvariable=self._status_var,
            font=self._font_small, fg=self.FG_DIM, bg=self.SURFACE
        )
        self._status_lbl.pack(side=tk.RIGHT, padx=16)

    # ──────────────────────────────────────────────────────────────────
    # Painel de leituras atuais
    # ──────────────────────────────────────────────────────────────────

    def _build_readings_panel(self) -> None:
        frame = tk.Frame(self, bg=self.BG)
        frame.pack(fill=tk.X, padx=16, pady=(8, 4))

        # Card de temperatura
        self._temp_card = self._make_card(frame, "Temperatura", "-- °C", self.TEMP_CLR)
        self._temp_card.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=(0, 6))

        # Card de umidade
        self._hum_card = self._make_card(frame, "Umidade", "-- %", self.HUM_CLR)
        self._hum_card.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=(6, 0))

    def _make_card(self, parent: tk.Widget, label: str, value: str,
                   color: str) -> tk.Frame:
        card = tk.Frame(parent, bg=self.SURFACE, padx=16, pady=14,
                        relief=tk.FLAT, bd=0)
        tk.Label(card, text=label, font=self._font_label,
                 fg=self.FG_DIM, bg=self.SURFACE).pack(anchor=tk.W)
        val_lbl = tk.Label(card, text=value, font=self._font_value,
                            fg=color, bg=self.SURFACE)
        val_lbl.pack(anchor=tk.W)
        # Armazena referência para poder atualizar depois
        card._value_label = val_lbl
        return card

    # ──────────────────────────────────────────────────────────────────
    # Painel de estado do sistema
    # ──────────────────────────────────────────────────────────────────

    def _build_state_panel(self) -> None:
        frame = tk.Frame(self, bg=self.SURFACE, padx=16, pady=12)
        frame.pack(fill=tk.X, padx=16, pady=4)

        tk.Label(frame, text="Estado do Sistema", font=self._font_label,
                 fg=self.FG_DIM, bg=self.SURFACE).pack(anchor=tk.W)

        indicators = tk.Frame(frame, bg=self.SURFACE)
        indicators.pack(anchor=tk.W, pady=(4, 0))

        self._heat_var  = tk.StringVar(value="⚫ Aquecimento: --")
        self._dehum_var = tk.StringVar(value="⚫ Desumidificação: --")

        tk.Label(indicators, textvariable=self._heat_var,
                 font=self._font_label, fg=self.FG, bg=self.SURFACE,
                 width=28, anchor=tk.W).pack(side=tk.LEFT, padx=(0, 16))

        tk.Label(indicators, textvariable=self._dehum_var,
                 font=self._font_label, fg=self.FG, bg=self.SURFACE,
                 width=28, anchor=tk.W).pack(side=tk.LEFT)

        tk.Label(frame, text="Recomendação de Ventilação", font=self._font_label,
                 fg=self.FG_DIM, bg=self.SURFACE).pack(anchor=tk.W, pady=(10, 2))

        self._rec_var = tk.StringVar(value="Aguardando dados...")
        tk.Label(frame, textvariable=self._rec_var,
                 font=self._font_label, fg=self.OK_CLR, bg=self.SURFACE,
                 wraplength=700, justify=tk.LEFT).pack(anchor=tk.W)

    # ──────────────────────────────────────────────────────────────────
    # Gráfico
    # ──────────────────────────────────────────────────────────────────

    def _build_chart(self) -> None:
        frame = tk.Frame(self, bg=self.BG)
        frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=4)

        self._chart = LiveChart(frame)
        self._chart.pack(fill=tk.BOTH, expand=True)

    # ──────────────────────────────────────────────────────────────────
    # Formulário de configuração
    # ──────────────────────────────────────────────────────────────────

    def _build_config_panel(self) -> None:
        frame = tk.Frame(self, bg=self.SURFACE, padx=16, pady=12)
        frame.pack(fill=tk.X, padx=16, pady=(4, 12))

        tk.Label(frame, text="Configuração de Limiares", font=self._font_label,
                 fg=self.FG_DIM, bg=self.SURFACE).grid(row=0, column=0,
                 columnspan=5, sticky=tk.W, pady=(0, 8))

        # Limiar de temperatura
        tk.Label(frame, text="Limiar temperatura (°C):", font=self._font_label,
                 fg=self.FG, bg=self.SURFACE).grid(row=1, column=0, sticky=tk.W,
                 padx=(0, 8))
        self._entry_temp = tk.Entry(frame, textvariable=self._temp_thresh,
                                    width=8, font=self._font_label,
                                    bg="#3A3A5C", fg=self.FG, insertbackground=self.FG,
                                    relief=tk.FLAT)
        self._entry_temp.grid(row=1, column=1, padx=(0, 24))

        # Limiar de umidade
        tk.Label(frame, text="Limiar umidade (%):", font=self._font_label,
                 fg=self.FG, bg=self.SURFACE).grid(row=1, column=2, sticky=tk.W,
                 padx=(0, 8))
        self._entry_hum = tk.Entry(frame, textvariable=self._hum_thresh,
                                   width=8, font=self._font_label,
                                   bg="#3A3A5C", fg=self.FG, insertbackground=self.FG,
                                   relief=tk.FLAT)
        self._entry_hum.grid(row=1, column=3, padx=(0, 24))

        # Botão de envio
        self._btn_send = tk.Button(
            frame, text="Enviar", font=self._font_label,
            bg=self.ACCENT, fg="white", relief=tk.FLAT,
            activebackground="#6D28D9", activeforeground="white",
            padx=14, pady=4, cursor="hand2",
            command=self._on_send_config
        )
        self._btn_send.grid(row=1, column=4)

        # Label de feedback
        self._feedback_var = tk.StringVar(value="")
        self._feedback_lbl = tk.Label(frame, textvariable=self._feedback_var,
                                      font=self._font_small, fg=self.OK_CLR,
                                      bg=self.SURFACE)
        self._feedback_lbl.grid(row=2, column=0, columnspan=5, sticky=tk.W,
                                pady=(6, 0))

    def _on_send_config(self) -> None:
        try:
            temp = float(self._temp_thresh.get())
            hum  = float(self._hum_thresh.get())
            if not (-10 <= temp <= 50) or not (0 <= hum <= 100):
                raise ValueError("Fora do intervalo permitido")
            self.send_config(temp, hum)
            self._set_feedback("Configuração enviada. Aguardando confirmação...", self.FG_DIM)
        except (ValueError, tk.TclError) as exc:
            self._set_feedback(f"Erro: {exc}", self.ERR_CLR)

    def _set_feedback(self, msg: str, color: str) -> None:
        self._feedback_var.set(msg)
        self._feedback_lbl.configure(fg=color)

    # ──────────────────────────────────────────────────────────────────
    # Verificação da fila — roda na thread principal via after()
    # ──────────────────────────────────────────────────────────────────

    def _poll_queue(self) -> None:
        try:
            while True:
                data = self.data_queue.get_nowait()
                self._handle_message(data)
        except queue.Empty:
            pass
        finally:
            self.after(POLL_MS, self._poll_queue)

    def _handle_message(self, data: dict) -> None:
        msg_type = data.get("type", "")

        if msg_type == "reading":
            temp  = data.get("temp")
            hum   = data.get("hum")
            heat  = data.get("heat", False)
            dehum = data.get("dehum", False)
            rec   = data.get("rec", "")

            if temp is not None:
                self._temp_card._value_label.configure(text=f"{temp:.1f} °C")
            if hum is not None:
                self._hum_card._value_label.configure(text=f"{hum:.1f} %")

            self._heat_var.set(
                f"{'🟠' if heat  else '⚫'} Aquecimento: {'ATIVO' if heat  else 'inativo'}"
            )
            self._dehum_var.set(
                f"{'🔵' if dehum else '⚫'} Desumidificação: {'ATIVA' if dehum else 'inativa'}"
            )
            self._rec_var.set(rec or "—")
            self._chart.update(temp, hum)

        elif msg_type == "ack":
            status = data.get("status", "")
            msg    = data.get("msg", "")
            if status == "ok":
                self._set_feedback("✔ Configuração aceita pelo ESP32.", self.OK_CLR)
            else:
                self._set_feedback(f"✘ Erro do ESP32: {msg}", self.ERR_CLR)

    # ──────────────────────────────────────────────────────────────────
    # Barra de status (chamada da thread SocketClient via status_callback)
    # ──────────────────────────────────────────────────────────────────

    def set_connection_status(self, msg: str) -> None:
        """Thread-safe: agenda atualização de status na thread principal."""
        self.after(0, lambda: self._status_var.set(msg))
