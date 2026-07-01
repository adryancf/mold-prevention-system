"""
gui.py — Main Tkinter window (improved visual design)

Visual improvements over v1:
  - Darker, more refined colour palette
  - Top accent border line on every card (2 px coloured Frame)
  - Canvas-based LED indicators with colour states
  - Status dot (Canvas oval) that pulses green / red
  - Button hover animation via <Enter> / <Leave> bindings
  - Better typography hierarchy and padding
  - Thin separator lines between sections
"""

import queue
import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, Optional

from chart import LiveChart

POLL_MS = 250
DEFAULT_TEMP_THRESH = 27.0
DEFAULT_HUM_THRESH = 60.0


# ─────────────────────────────────────────────────────────────────────────────
# Palette
# ─────────────────────────────────────────────────────────────────────────────
class P:
    BG       = "#0E0E1A"
    SURFACE  = "#17172B"
    CARD     = "#1C1C32"
    BORDER   = "#2A2A45"
    ACCENT   = "#7C3AED"
    ACCENT_H = "#9D5FF5"   # hover
    TEMP     = "#FF6B6B"
    HUM      = "#00D4D4"
    OK       = "#00C896"
    WARN     = "#FFB800"
    ERR      = "#FF4757"
    FG       = "#E8E8F2"
    FG_MID   = "#9898B8"
    FG_DIM   = "#4A4A6A"


# ─────────────────────────────────────────────────────────────────────────────
# Reusable component: Card (surface + optional top accent bar)
# ─────────────────────────────────────────────────────────────────────────────
class Card(tk.Frame):
    """Painel de fundo escuro com uma faixa de acento colorida opcional no topo."""

    def __init__(self, parent, accent_color: Optional[str] = None,
                 padx=16, pady=12, **kwargs):
        super().__init__(parent, bg=P.CARD, **kwargs)

        if accent_color:
            tk.Frame(self, bg=accent_color, height=2).pack(fill=tk.X, side=tk.TOP)

        self._inner = tk.Frame(self, bg=P.CARD, padx=padx, pady=pady)
        self._inner.pack(fill=tk.BOTH, expand=True)

    @property
    def inner(self) -> tk.Frame:
        return self._inner


# ─────────────────────────────────────────────────────────────────────────────
# Reusable component: Canvas-based status dot
# ─────────────────────────────────────────────────────────────────────────────
class StatusDot(tk.Canvas):
    """Circulo pequeno e pulsante que muda de cor conforme o estado da conexao."""

    SIZE = 10

    def __init__(self, parent, **kwargs):
        super().__init__(parent, width=self.SIZE, height=self.SIZE,
                         bg=P.SURFACE, highlightthickness=0, **kwargs)
        self._oval = self.create_oval(1, 1, self.SIZE - 1, self.SIZE - 1,
                                      fill=P.FG_DIM, outline="")
        self._dim  = False
        self._pulse_job = None

    def set_state(self, connected: bool) -> None:
        color = P.OK if connected else P.ERR
        self.itemconfig(self._oval, fill=color)
        if connected:
            self._start_pulse(color)
        else:
            self._stop_pulse()
            self.itemconfig(self._oval, fill=P.ERR)

    def _start_pulse(self, color: str) -> None:
        self._stop_pulse()
        self._pulse_color = color
        self._pulse()

    def _pulse(self) -> None:
        self._dim = not self._dim
        c = P.FG_DIM if self._dim else self._pulse_color
        self.itemconfig(self._oval, fill=c)
        self._pulse_job = self.after(900, self._pulse)

    def _stop_pulse(self) -> None:
        if self._pulse_job:
            self.after_cancel(self._pulse_job)
            self._pulse_job = None


# ─────────────────────────────────────────────────────────────────────────────
# Reusable component: Canvas-based LED indicator
# ─────────────────────────────────────────────────────────────────────────────
class LedIndicator(tk.Frame):
    """A coloured circle + label pair that shows ON/OFF actuator state."""

    DOT_SIZE = 12

    def __init__(self, parent, label: str, on_color: str, **kwargs):
        super().__init__(parent, bg=P.CARD, **kwargs)
        self._on_color = on_color

        self._canvas = tk.Canvas(self, width=self.DOT_SIZE, height=self.DOT_SIZE,
                                 bg=P.CARD, highlightthickness=0)
        self._canvas.pack(side=tk.LEFT, padx=(0, 6))
        self._oval = self._canvas.create_oval(
            1, 1, self.DOT_SIZE - 1, self.DOT_SIZE - 1,
            fill=P.FG_DIM, outline="")

        self._name_lbl = tk.Label(self, text=label, bg=P.CARD,
                                  fg=P.FG_MID, font=("Helvetica", 9))
        self._name_lbl.pack(side=tk.LEFT, padx=(0, 4))

        self._state_var = tk.StringVar(value="--")
        self._state_lbl = tk.Label(self, textvariable=self._state_var,
                                   bg=P.CARD, fg=P.FG_DIM,
                                   font=("Helvetica", 9, "bold"))
        self._state_lbl.pack(side=tk.LEFT)

    def set_active(self, active: bool) -> None:
        color = self._on_color if active else P.FG_DIM
        self._canvas.itemconfig(self._oval, fill=color)
        self._state_var.set("ATIVO" if active else "inativo")
        self._state_lbl.configure(fg=self._on_color if active else P.FG_DIM)


# ─────────────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────────────
class MainWindow(tk.Tk):
    def __init__(
        self,
        data_queue: queue.Queue,
        send_config_fn: Optional[Callable[[float, float], None]] = None,
        simulate: bool = False,
    ):
        super().__init__()
        self.data_queue = data_queue
        self._send_config_fn = send_config_fn
        self.simulate = simulate

        self._temp_thresh = tk.DoubleVar(value=DEFAULT_TEMP_THRESH)
        self._hum_thresh  = tk.DoubleVar(value=DEFAULT_HUM_THRESH)

        self._setup_window()
        self._build_header()
        self._build_readings()
        self._build_state_panel()
        self._build_chart()
        self._build_config_panel()

        self.after(POLL_MS, self._poll_queue)

    def set_send_config_fn(self, send_config_fn: Callable[[float, float], None]) -> None:
        self._send_config_fn = send_config_fn
        if hasattr(self, "_btn"):
            self._btn.configure(state=tk.NORMAL)

    def send_config(self, temp_thresh: float, hum_thresh: float) -> None:
        if self._send_config_fn is None:
            raise RuntimeError("Cliente ainda nao esta pronto")
        self._send_config_fn(temp_thresh, hum_thresh)

    # ── Window ────────────────────────────────────────────────────────
    def _setup_window(self) -> None:
        title = "Sistema de Prevenção de Mofo"
        if self.simulate:
            title += " — Simulação"
        self.title(title)
        self.configure(bg=P.BG)
        self.minsize(780, 660)

        self._f_title  = tkfont.Font(family="Helvetica", size=14, weight="bold")
        self._f_value  = tkfont.Font(family="Helvetica", size=34, weight="bold")
        self._f_unit   = tkfont.Font(family="Helvetica", size=13)
        self._f_label  = tkfont.Font(family="Helvetica", size=9)
        self._f_small  = tkfont.Font(family="Helvetica", size=8)
        self._f_btn    = tkfont.Font(family="Helvetica", size=10, weight="bold")

    # ── Header ────────────────────────────────────────────────────────
    def _build_header(self) -> None:
        hdr = tk.Frame(self, bg=P.SURFACE)
        hdr.pack(fill=tk.X)
        # accent stripe
        tk.Frame(hdr, bg=P.ACCENT, height=3).pack(fill=tk.X, side=tk.TOP)

        inner = tk.Frame(hdr, bg=P.SURFACE, pady=10, padx=16)
        inner.pack(fill=tk.X)

        sim = "  ·  simulação" if self.simulate else ""
        tk.Label(inner, text=f"🍃  Sistema de Prevenção de Mofo{sim}",
                 font=self._f_title, fg=P.FG, bg=P.SURFACE).pack(side=tk.LEFT)

        right = tk.Frame(inner, bg=P.SURFACE)
        right.pack(side=tk.RIGHT)

        self._dot = StatusDot(right)
        self._dot.pack(side=tk.LEFT, padx=(0, 6))

        self._status_var = tk.StringVar(value="Conectando…")
        tk.Label(right, textvariable=self._status_var,
                 font=self._f_small, fg=P.FG_MID, bg=P.SURFACE).pack(side=tk.LEFT)

    # ── Readings: temperature + humidity cards ─────────────────────────
    def _build_readings(self) -> None:
        row = tk.Frame(self, bg=P.BG)
        row.pack(fill=tk.X, padx=12, pady=(10, 6))
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=1)

        # Temperature card
        tc = Card(row, accent_color=P.TEMP)
        tc.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        tk.Label(tc.inner, text="TEMPERATURA", font=self._f_small,
                 fg=P.FG_DIM, bg=P.CARD).pack(anchor=tk.W)
        val_row = tk.Frame(tc.inner, bg=P.CARD)
        val_row.pack(anchor=tk.W, pady=(2, 0))
        self._temp_val = tk.Label(val_row, text="--", font=self._f_value,
                                  fg=P.TEMP, bg=P.CARD)
        self._temp_val.pack(side=tk.LEFT)
        tk.Label(val_row, text=" °C", font=self._f_unit,
                 fg=P.TEMP, bg=P.CARD).pack(side=tk.LEFT, anchor=tk.S, pady=(0, 8))

        # Humidity card
        hc = Card(row, accent_color=P.HUM)
        hc.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        tk.Label(hc.inner, text="UMIDADE RELATIVA", font=self._f_small,
                 fg=P.FG_DIM, bg=P.CARD).pack(anchor=tk.W)
        val_row2 = tk.Frame(hc.inner, bg=P.CARD)
        val_row2.pack(anchor=tk.W, pady=(2, 0))
        self._hum_val = tk.Label(val_row2, text="--", font=self._f_value,
                                  fg=P.HUM, bg=P.CARD)
        self._hum_val.pack(side=tk.LEFT)
        tk.Label(val_row2, text=" %", font=self._f_unit,
                 fg=P.HUM, bg=P.CARD).pack(side=tk.LEFT, anchor=tk.S, pady=(0, 8))

    # ── State panel ───────────────────────────────────────────────────
    def _build_state_panel(self) -> None:
        card = Card(self, accent_color=P.ACCENT, pady=10)
        card.pack(fill=tk.X, padx=12, pady=(0, 6))

        # LED indicators row
        leds = tk.Frame(card.inner, bg=P.CARD)
        leds.pack(anchor=tk.W)

        self._led_heat  = LedIndicator(leds, "Aquecimento",     P.WARN)
        self._led_heat.pack(side=tk.LEFT, padx=(0, 28))

        self._led_dehum = LedIndicator(leds, "Desumidificação", P.HUM)
        self._led_dehum.pack(side=tk.LEFT)

        # Separator
        tk.Frame(card.inner, bg=P.BORDER, height=1).pack(fill=tk.X, pady=(10, 8))

        # Ventilation recommendation
        rec_row = tk.Frame(card.inner, bg=P.CARD)
        rec_row.pack(anchor=tk.W, fill=tk.X)

        tk.Label(rec_row, text="💬", bg=P.CARD, fg=P.FG,
                 font=self._f_label).pack(side=tk.LEFT, padx=(0, 6))

        self._rec_var = tk.StringVar(value="Aguardando dados…")
        tk.Label(rec_row, textvariable=self._rec_var,
                 font=self._f_label, fg=P.OK, bg=P.CARD,
                 wraplength=680, justify=tk.LEFT).pack(side=tk.LEFT)

    # ── Chart ─────────────────────────────────────────────────────────
    def _build_chart(self) -> None:
        card = Card(self, accent_color=None, padx=0, pady=0)
        card.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 6))
        self._chart = LiveChart(card.inner)
        self._chart.pack(fill=tk.BOTH, expand=True)

    # ── Config panel ──────────────────────────────────────────────────
    def _build_config_panel(self) -> None:
        card = Card(self, accent_color=P.BORDER, pady=10)
        card.pack(fill=tk.X, padx=12, pady=(0, 12))

        tk.Label(card.inner, text="LIMIARES DE OPERAÇÃO", font=self._f_small,
                 fg=P.FG_DIM, bg=P.CARD).grid(row=0, column=0, columnspan=6,
                 sticky=tk.W, pady=(0, 8))

        entry_cfg = dict(width=7, font=self._f_label, bg="#252540",
                         fg=P.FG, insertbackground=P.FG,
                         relief=tk.FLAT, highlightthickness=1,
                         highlightbackground=P.BORDER,
                         highlightcolor=P.ACCENT)

        # Temperature
        tk.Label(card.inner, text="Temperatura (°C)", font=self._f_label,
                 fg=P.FG_MID, bg=P.CARD).grid(row=1, column=0, sticky=tk.W,
                 padx=(0, 6))
        self._entry_temp = tk.Entry(card.inner, textvariable=self._temp_thresh,
                                    **entry_cfg)
        self._entry_temp.grid(row=1, column=1, padx=(0, 20))

        # Humidity
        tk.Label(card.inner, text="Umidade (%)", font=self._f_label,
                 fg=P.FG_MID, bg=P.CARD).grid(row=1, column=2, sticky=tk.W,
                 padx=(0, 6))
        self._entry_hum = tk.Entry(card.inner, textvariable=self._hum_thresh,
                                   **entry_cfg)
        self._entry_hum.grid(row=1, column=3, padx=(0, 20))

        # Send button with hover
        self._btn = tk.Button(
            card.inner, text="Enviar", font=self._f_btn,
            bg=P.ACCENT, fg="white", relief=tk.FLAT,
            activebackground=P.ACCENT_H, activeforeground="white",
            padx=18, pady=5, cursor="hand2",
            state=(tk.NORMAL if self._send_config_fn else tk.DISABLED),
            command=self._on_send_config
        )
        self._btn.grid(row=1, column=4, padx=(0, 0))
        self._btn.bind("<Enter>",  lambda e: self._btn.configure(bg=P.ACCENT_H))
        self._btn.bind("<Leave>",  lambda e: self._btn.configure(bg=P.ACCENT))

        # Feedback
        self._feedback_var = tk.StringVar(value="")
        self._feedback_lbl = tk.Label(card.inner, textvariable=self._feedback_var,
                                      font=self._f_small, fg=P.OK, bg=P.CARD)
        self._feedback_lbl.grid(row=2, column=0, columnspan=6, sticky=tk.W,
                                 pady=(7, 0))

    # ── Send config ───────────────────────────────────────────────────
    def _on_send_config(self) -> None:
        try:
            temp = float(self._temp_thresh.get())
            hum  = float(self._hum_thresh.get())
            if not (-10 <= temp <= 50) or not (0 <= hum <= 100):
                raise ValueError("Fora do intervalo permitido")
            self.send_config(temp, hum)
            self._set_feedback("Configuração enviada. Aguardando confirmação…", P.FG_MID)
        except (RuntimeError, ValueError, tk.TclError) as exc:
            self._set_feedback(f"Erro: {exc}", P.ERR)

    def _set_feedback(self, msg: str, color: str) -> None:
        self._feedback_var.set(msg)
        self._feedback_lbl.configure(fg=color)

    # ── Queue polling ─────────────────────────────────────────────────
    def _poll_queue(self) -> None:
        try:
            while True:
                self._handle_message(self.data_queue.get_nowait())
        except queue.Empty:
            pass
        finally:
            self.after(POLL_MS, self._poll_queue)

    def _handle_message(self, data: dict) -> None:
        msg_type = data.get("type", "")

        if msg_type == "reading":
            temp  = self._as_float(data.get("temp"))
            hum   = self._as_float(data.get("hum"))
            heat  = data.get("heat", False)
            dehum = data.get("dehum", False)
            rec   = str(data.get("rec", ""))

            if temp is not None:
                self._temp_val.configure(text=f"{temp:.1f}")
            if hum is not None:
                self._hum_val.configure(text=f"{hum:.1f}")

            self._led_heat.set_active(heat)
            self._led_dehum.set_active(dehum)
            self._rec_var.set(rec or "—")
            self._chart.update(temp, hum)
            self._sync_threshold(data.get("temp_thresh"), self._temp_thresh, self._entry_temp)
            self._sync_threshold(data.get("hum_thresh"), self._hum_thresh, self._entry_hum)

        elif msg_type == "ack":
            ok = data.get("status") == "ok"
            msg = data.get("msg", "")
            if ok:
                self._set_feedback("✔  Configuração aceita pelo ESP32.", P.OK)
            else:
                self._set_feedback(f"✘  Erro do ESP32: {msg}", P.ERR)

    @staticmethod
    def _as_float(value) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _sync_threshold(self, value, var: tk.DoubleVar, entry: tk.Entry) -> None:
        parsed = self._as_float(value)
        if parsed is None or self.focus_get() is entry:
            return
        var.set(round(parsed, 1))

    # ── Status bar (thread-safe) ──────────────────────────────────────
    def set_connection_status(self, msg: str) -> None:
        connected = msg.lower().startswith("conectado")
        self.after(0, lambda: (
            self._status_var.set(msg),
            self._dot.set_state(connected)
        ))
