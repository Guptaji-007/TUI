from collections import deque

import numpy as np
import sounddevice as sd
from rich import box
from rich.table import Table
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header, Static

SAMPLE_RATE = 44100
CHUNK_SIZE = 1024
BANDS = 12
MAX_BAR = 36
NOISE_GATE_DB = 8.0


class AudioAnalyzer:
    """Capture microphone input and keep smoothed spectrum values ready for rendering."""

    def __init__(self) -> None:
        self.levels = np.zeros(BANDS, dtype=float)
        self.peaks = np.zeros(BANDS, dtype=float)
        self.db_level = 0.0
        self.band_edges = np.geomspace(35, 12000, BANDS + 1)
        self.noise_floor = np.full(BANDS, 0.02, dtype=float)

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            blocksize=CHUNK_SIZE,
            callback=self.audio_callback,
        )

    def audio_callback(self, indata, frames, time, status) -> None:
        audio_data = indata[:, 0]
        rms = float(np.sqrt(np.mean(audio_data ** 2)))
        self.db_level = max(0.0, min(60.0, 20 * np.log10(rms + 1e-8) + 60.0))

        # Fast noise gate to suppress idle-room mic hiss.
        if self.db_level < NOISE_GATE_DB:
            self.levels *= 0.82
            self.peaks = np.maximum(self.levels, self.peaks * 0.9)
            return

        windowed = audio_data * np.hanning(len(audio_data))
        fft_data = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(CHUNK_SIZE, d=1 / SAMPLE_RATE)

        band_levels = []
        for low, high in zip(self.band_edges[:-1], self.band_edges[1:]):
            mask = (freqs >= low) & (freqs < high)
            if np.any(mask):
                band_levels.append(float(np.mean(fft_data[mask])))
            else:
                band_levels.append(0.0)

        band_array = np.array(band_levels, dtype=float)

        # Track and subtract a slowly adapting per-band background floor.
        self.noise_floor = np.minimum(self.noise_floor * 1.002, band_array)
        cleaned = np.maximum(0.0, band_array - (self.noise_floor * 1.15))

        raw = np.log1p(cleaned * np.linspace(1.0, 2.2, BANDS))
        peak_raw = float(np.max(raw))
        if peak_raw < 1e-5:
            self.levels *= 0.9
            self.peaks = np.maximum(self.levels, self.peaks * 0.92)
            return

        normalized = raw / peak_raw
        target = normalized * MAX_BAR

        self.levels = (self.levels * 0.72) + (target * 0.28)
        self.peaks = np.maximum(self.levels, self.peaks * 0.95)

    def start(self) -> None:
        self.stream.start()

    def stop(self) -> None:
        self.stream.stop()


class Histogram(Static):
    MODES = ("solid", "stacked", "spark")
    MODE_LABELS = {
        "solid": "Solid Bars",
        "stacked": "Stacked Heat",
        "spark": "Spark Trails",
    }
    BAND_NAMES = [
        "Sub",
        "Bass",
        "Warm",
        "Body",
        "Mid",
        "Edge",
        "Clarity",
        "Presence",
        "Shine",
        "Air",
        "Air+",
        "Ultra",
    ]

    def _solid_bar(self, level: float, peak: float, color: str) -> str:
        fill = int(max(0, min(MAX_BAR, level)))
        peak_pos = int(max(0, min(MAX_BAR - 1, peak)))
        bar = ["░"] * MAX_BAR
        for i in range(fill):
            bar[i] = "█"
        bar[peak_pos] = "│"
        return f"[{color}]{''.join(bar)}[/{color}]"

    def _stacked_bar(self, level: float) -> str:
        fill = int(max(0, min(MAX_BAR, level)))
        segments = []
        for i in range(fill):
            if i < 10:
                segments.append("[#22c55e]▇[/#22c55e]")
            elif i < 22:
                segments.append("[#f59e0b]▇[/#f59e0b]")
            else:
                segments.append("[#ef4444]▇[/#ef4444]")
        if fill < MAX_BAR:
            segments.append("[dim]" + "·" * (MAX_BAR - fill) + "[/dim]")
        return "".join(segments)

    def _spark_bar(self, history: list[float], level: float) -> str:
        spark_chars = "▁▂▃▄▅▆▇█"
        points = history[-20:]
        if not points:
            return ""

        spark = []
        for point in points:
            idx = int((max(0.0, min(MAX_BAR, point)) / MAX_BAR) * (len(spark_chars) - 1))
            spark.append(spark_chars[idx])

        current = int(max(0, min(MAX_BAR, level)))
        return f"[#60a5fa]{''.join(spark)}[/#60a5fa] [bold #22d3ee]{'█' * max(1, current // 4)}[/bold #22d3ee]"

    def update_data(
        self,
        levels: np.ndarray,
        peaks: np.ndarray,
        mode: str,
        db_level: float,
        band_edges: np.ndarray,
        history: list[np.ndarray],
    ) -> None:
        table = Table(
            title=f"[b]Live Microphone Histogram[/b] • [#7dd3fc]{self.MODE_LABELS[mode]}[/#7dd3fc]",
            box=box.ROUNDED,
            border_style="#0ea5e9",
            expand=True,
        )
        table.add_column("Band", justify="left", style="bold #fcd34d", width=10)
        table.add_column("Range", justify="right", style="#93c5fd", width=13)
        table.add_column("dB", justify="right", style="#86efac", width=6)
        table.add_column("Histogram", justify="left")

        band_colors = [
            "#0ea5e9",
            "#06b6d4",
            "#14b8a6",
            "#22c55e",
            "#84cc16",
            "#eab308",
            "#f59e0b",
            "#f97316",
            "#ef4444",
            "#ec4899",
            "#d946ef",
            "#8b5cf6",
        ]

        history_by_band = list(zip(*history)) if history else [tuple() for _ in range(BANDS)]

        for idx, level in enumerate(levels):
            peak = peaks[idx]
            low = int(band_edges[idx])
            high = int(band_edges[idx + 1])
            band_db = (level / MAX_BAR) * 60

            if mode == "solid":
                visual = self._solid_bar(level, peak, band_colors[idx])
            elif mode == "stacked":
                visual = self._stacked_bar(level)
            else:
                visual = self._spark_bar(list(history_by_band[idx]), level)

            table.add_row(
                self.BAND_NAMES[idx],
                f"{low:>5}-{high:<5}",
                f"{band_db:>4.1f}",
                visual,
            )

        dominant_band = int(np.argmax(levels))
        table.caption = (
            f"Input Level: [bold #38bdf8]{db_level:0.1f} dB[/bold #38bdf8]"
            f"   Dominant: [bold #f59e0b]{self.BAND_NAMES[dominant_band]}[/bold #f59e0b]"
        )
        self.update(table)


class LiveApp(App):
    CSS = """
    Screen {
        background: #050a12;
        color: #dbeafe;
    }

    #layout {
        width: 100%;
        height: 1fr;
        padding: 1 2;
    }

    #hero {
        height: 3;
        border: round #155e75;
        background: #062433;
        color: #bae6fd;
        content-align: center middle;
        margin-bottom: 1;
    }

    Histogram {
        width: 1fr;
        height: 1fr;
        border: round #0ea5e9;
        background: #081b29;
        padding: 0 1;
        margin-bottom: 1;
    }

    #tips {
        height: 2;
        border: round #1d4ed8;
        background: #0b1630;
        color: #bfdbfe;
        content-align: center middle;
    }
    """

    BINDINGS = [
        Binding("v", "cycle_mode", "Visual Mode"),
        Binding("r", "reset_peaks", "Reset Peaks"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="layout"):
            yield Static("AUDIO SPECTRUM LAB", id="hero")
            self.hist = Histogram()
            yield self.hist
            yield Static("V: cycle visual mode | R: reset peaks | Q: quit", id="tips")
        yield Footer()

    def on_mount(self) -> None:
        self.audio = AudioAnalyzer()
        self.audio.start()
        self.mode_index = 0
        self.level_history = deque(maxlen=28)
        self.set_interval(0.033, self.refresh_data)

    def refresh_data(self) -> None:
        levels = self.audio.levels.copy()
        peaks = self.audio.peaks.copy()
        self.level_history.append(levels.copy())

        self.hist.update_data(
            levels,
            peaks,
            Histogram.MODES[self.mode_index],
            self.audio.db_level,
            self.audio.band_edges,
            list(self.level_history),
        )

    def action_cycle_mode(self) -> None:
        self.mode_index = (self.mode_index + 1) % len(Histogram.MODES)

    def action_reset_peaks(self) -> None:
        self.audio.peaks = self.audio.levels.copy()

    def on_unmount(self) -> None:
        self.audio.stop()


if __name__ == "__main__":
    LiveApp().run()
