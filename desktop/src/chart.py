"""
chart.py — Live temperature and humidity chart widget (improved)

Changes over v1:
  - Semi-transparent area fill under each curve
  - Animated dot at the latest data point
  - Cleaner axis / spine styling
  - Tighter layout with title legend embedded in axes
"""

from collections import deque
from typing import Optional

import matplotlib
matplotlib.use("TkAgg")

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk

HISTORY_SIZE = 60


class LiveChart(tk.Frame):
    BG_COLOR   = "#0E0E1A"
    TEMP_COLOR = "#FF6B6B"
    HUM_COLOR  = "#00D4D4"
    GRID_COLOR = "#1E1E34"
    SPINE_CLR  = "#2A2A45"
    LABEL_CLR  = "#5C5C7A"

    def __init__(self, parent: tk.Widget, **kwargs):
        super().__init__(parent, bg=self.BG_COLOR, **kwargs)
        self._temps: deque = deque([None] * HISTORY_SIZE, maxlen=HISTORY_SIZE)
        self._hums:  deque = deque([None] * HISTORY_SIZE, maxlen=HISTORY_SIZE)
        self._build_figure()

    def _build_figure(self) -> None:
        self._fig, self._ax_temp = plt.subplots(figsize=(7, 2.6), dpi=96)
        self._fig.patch.set_facecolor(self.BG_COLOR)
        self._fig.subplots_adjust(left=0.08, right=0.92, top=0.88, bottom=0.14)

        # ── Temperature axis (left) ────────────────────────────────────
        ax = self._ax_temp
        ax.set_facecolor(self.BG_COLOR)
        ax.tick_params(axis="y", labelcolor=self.TEMP_COLOR, labelsize=7.5,
                       length=0, pad=4)
        ax.tick_params(axis="x", labelsize=6.5, colors=self.LABEL_CLR, length=0)
        ax.set_xlim(0, HISTORY_SIZE - 1)
        ax.set_ylim(0, 50)
        ax.yaxis.label.set_color(self.TEMP_COLOR)

        ax.grid(color=self.GRID_COLOR, linestyle="-", linewidth=0.8, alpha=0.9)
        ax.set_axisbelow(True)

        for spine in ax.spines.values():
            spine.set_edgecolor(self.SPINE_CLR)
            spine.set_linewidth(0.8)

        # ── Humidity axis (right) ──────────────────────────────────────
        self._ax_hum = ax.twinx()
        self._ax_hum.set_ylim(0, 100)
        self._ax_hum.tick_params(axis="y", labelcolor=self.HUM_COLOR, labelsize=7.5,
                                  length=0, pad=4)
        for spine in self._ax_hum.spines.values():
            spine.set_edgecolor(self.SPINE_CLR)
            spine.set_linewidth(0.8)

        # ── Line plots ──────────────────────────────────────────────────
        x = list(range(HISTORY_SIZE))
        empty = [None] * HISTORY_SIZE

        (self._line_temp,) = ax.plot(x, empty, color=self.TEMP_COLOR,
                                     linewidth=1.8, solid_capstyle="round",
                                     solid_joinstyle="round", zorder=3)
        (self._line_hum,) = self._ax_hum.plot(x, empty, color=self.HUM_COLOR,
                                               linewidth=1.8, solid_capstyle="round",
                                               solid_joinstyle="round", zorder=3)

        # Objetos de preenchimento (criados uma vez, atualizados no lugar)
        self._fill_temp = ax.fill_between(x, 0, 0, color=self.TEMP_COLOR,
                                          alpha=0.12, zorder=2)
        self._fill_hum  = self._ax_hum.fill_between(x, 0, 0, color=self.HUM_COLOR,
                                                    alpha=0.12, zorder=2)

        # Latest-value dots
        (self._dot_temp,) = ax.plot([], [], "o", color=self.TEMP_COLOR,
                                    markersize=5, zorder=4)
        (self._dot_hum,)  = self._ax_hum.plot([], [], "o", color=self.HUM_COLOR,
                                               markersize=5, zorder=4)

        # ── Compact legend in the axes ─────────────────────────────────
        temp_patch = mpatches.Patch(color=self.TEMP_COLOR, label="Temp (°C)")
        hum_patch  = mpatches.Patch(color=self.HUM_COLOR,  label="Umidade (%)")
        ax.legend(handles=[temp_patch, hum_patch],
                  loc="upper left", fontsize=7,
                  facecolor="#1A1A2E", edgecolor=self.SPINE_CLR,
                  labelcolor=[self.TEMP_COLOR, self.HUM_COLOR],
                  framealpha=0.9, borderpad=0.5, handlelength=0.8)

        self._canvas = FigureCanvasTkAgg(self._fig, master=self)
        self._canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._canvas.draw()

    def update(self, temp: Optional[float], hum: Optional[float]) -> None:
        self._temps.append(temp)
        self._hums.append(hum)

        x = list(range(HISTORY_SIZE))
        t_vals = list(self._temps)
        h_vals = list(self._hums)

        self._line_temp.set_ydata(t_vals)
        self._line_hum.set_ydata(h_vals)

        # Update fill (remove old, add new)
        self._fill_temp.remove()
        self._fill_hum.remove()
        t_safe = [v if v is not None else 0 for v in t_vals]
        h_safe = [v if v is not None else 0 for v in h_vals]
        self._fill_temp = self._ax_temp.fill_between(
            x, 0, t_safe, color=self.TEMP_COLOR, alpha=0.12, zorder=2)
        self._fill_hum = self._ax_hum.fill_between(
            x, 0, h_safe, color=self.HUM_COLOR, alpha=0.12, zorder=2)

        # Update latest-value dots
        valid_t = [(i, v) for i, v in enumerate(t_vals) if v is not None]
        valid_h = [(i, v) for i, v in enumerate(h_vals) if v is not None]
        if valid_t:
            lx, ly = valid_t[-1]
            self._dot_temp.set_data([lx], [ly])
        if valid_h:
            lx, ly = valid_h[-1]
            self._dot_hum.set_data([lx], [ly])

        # Auto-scale temperature
        vt = [v for v in t_vals if v is not None]
        if vt:
            lo, hi = min(vt) - 4, max(vt) + 4
            self._ax_temp.set_ylim(max(lo, -10), min(hi, 60))

        self._canvas.draw_idle()
