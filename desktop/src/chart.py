"""
chart.py — Widget de gráfico ao vivo de temperatura e umidade

Embute uma figura Matplotlib dentro de um Frame do Tkinter.
Mantém um histórico de tamanho fixo (HISTORY_SIZE amostras) e redesenha
a cada chamada de update(temp, hum).

O gráfico usa uma única figura com dois eixos Y:
    - Eixo esquerdo:  temperatura (°C)
    - Eixo direito:   umidade (%)

O Matplotlib é usado em modo não-interativo (plt.switch_backend("Agg") NÃO é
chamado; em vez disso, FigureCanvasTkAgg embute a figura diretamente no Tkinter,
evitando o overhead de uma janela de renderização separada).
"""

from collections import deque
from typing import Optional

import matplotlib
matplotlib.use("TkAgg")  # Deve ser definido antes de importar pyplot

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk

HISTORY_SIZE = 60   # Número de amostras exibidas (≈ 2 min a 2 s/amostra)


class LiveChart(tk.Frame):
    """
    Frame Tkinter contendo um gráfico Matplotlib ao vivo com eixo duplo.
    """

    TEMP_COLOR = "#EF5350"   # Vermelho para temperatura
    HUM_COLOR  = "#42A5F5"   # Azul para umidade
    BG_COLOR   = "#1E1E2E"   # Fundo escuro
    GRID_COLOR = "#3A3A5C"

    def __init__(self, parent: tk.Widget, **kwargs):
        super().__init__(parent, bg=self.BG_COLOR, **kwargs)

        self._temps: deque = deque([None] * HISTORY_SIZE, maxlen=HISTORY_SIZE)
        self._hums:  deque = deque([None] * HISTORY_SIZE, maxlen=HISTORY_SIZE)

        self._build_figure()

    def _build_figure(self) -> None:
        self._fig, self._ax_temp = plt.subplots(figsize=(7, 2.8), dpi=96)
        self._fig.patch.set_facecolor(self.BG_COLOR)

        # Eixo de temperatura (esquerdo)
        self._ax_temp.set_facecolor(self.BG_COLOR)
        self._ax_temp.set_ylabel("Temperatura (°C)", color=self.TEMP_COLOR, fontsize=9)
        self._ax_temp.tick_params(axis="y", labelcolor=self.TEMP_COLOR, labelsize=8)
        self._ax_temp.tick_params(axis="x", labelsize=7, colors="#AAAAAA")
        self._ax_temp.set_xlim(0, HISTORY_SIZE - 1)
        self._ax_temp.set_ylim(0, 50)
        self._ax_temp.grid(color=self.GRID_COLOR, linestyle="--", linewidth=0.5)
        for spine in self._ax_temp.spines.values():
            spine.set_edgecolor(self.GRID_COLOR)

        # Eixo de umidade (direito)
        self._ax_hum = self._ax_temp.twinx()
        self._ax_hum.set_ylabel("Umidade (%)", color=self.HUM_COLOR, fontsize=9)
        self._ax_hum.tick_params(axis="y", labelcolor=self.HUM_COLOR, labelsize=8)
        self._ax_hum.set_ylim(0, 100)
        for spine in self._ax_hum.spines.values():
            spine.set_edgecolor(self.GRID_COLOR)

        # Objetos de linha inicialmente vazios (atualizados in-place por performance)
        x = list(range(HISTORY_SIZE))
        (self._line_temp,) = self._ax_temp.plot(
            x, [None] * HISTORY_SIZE,
            color=self.TEMP_COLOR, linewidth=1.8, label="Temperatura"
        )
        (self._line_hum,) = self._ax_hum.plot(
            x, [None] * HISTORY_SIZE,
            color=self.HUM_COLOR, linewidth=1.8, label="Umidade"
        )

        self._fig.tight_layout(pad=1.2)

        self._canvas = FigureCanvasTkAgg(self._fig, master=self)
        self._canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._canvas.draw()

    def update(self, temp: Optional[float], hum: Optional[float]) -> None:
        """Adiciona novos dados e redesenha o gráfico."""
        self._temps.append(temp)
        self._hums.append(hum)

        self._line_temp.set_ydata(list(self._temps))
        self._line_hum.set_ydata(list(self._hums))

        # Escala automática do eixo de temperatura com algum padding
        valid_temps = [t for t in self._temps if t is not None]
        if valid_temps:
            lo = min(valid_temps) - 3
            hi = max(valid_temps) + 3
            self._ax_temp.set_ylim(max(lo, -10), min(hi, 60))

        self._canvas.draw_idle()
