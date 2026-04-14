from textual.app import App, ComposeResult
from textual.widgets import Static, Header, Footer
from rich.table import Table
from rich import box
from collections import Counter
import random
import math


class Histogram(Static):
    def update_data(self, data):
        counts = Counter(data)
        max_count = max(counts.values()) if counts else 1

        # 1. Enhance the Rich Table styling
        table = Table(
            title="[b]Live Waveform Distribution[/b]",
            box=box.MINIMAL_DOUBLE_HEAD,  # Cleaner borders
            border_style="cyan",
            expand=True  # Fills the widget space nicely
        )
        table.add_column("Value", justify="center",
                         style="bold magenta", width=8)
        table.add_column("Count", justify="center",
                         style="bold green", width=8)
        table.add_column("Bar", justify="left")

        # 2. Define a color palette for the histogram bars
        colors = [
            "#3b82f6", "#06b6d4", "#10b981", "#84cc16", "#eab308",
            "#f59e0b", "#f97316", "#ef4444", "#ec4899", "#d946ef", "#8b5cf6"
        ]

        # 3. Iterate over a fixed range (0-10) to stop the table from jumping around
        for key in range(11):
            count = counts.get(key, 0)
            bar_len = int((count / max_count) * 40)

            # Apply the color to the bar string using Rich markup
            color = colors[key]
            bar = f"[{color}]{'█' * bar_len}[/{color}]" if bar_len > 0 else ""

            table.add_row(str(key), str(count), bar)

        self.update(table)


class LiveApp(App):
    # 4. Add Textual CSS for layout, borders, and spacing
    CSS = """
    Screen {
        align: center middle;
    }
    Histogram {
        width: 70%;
        height: auto;
        border: round cyan;
        padding: 1 2;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        # Add a Header and Footer for a "full app" feel
        yield Header(show_clock=True)
        self.hist = Histogram()
        yield self.hist
        yield Footer()

    def on_mount(self):
        self.t = 0
        # Reduced interval slightly for a smoother animation frame rate
        self.set_interval(0.2, self.refresh_data)

    def generate_data(self):
        data = []

        for _ in range(200):
            # Smooth wave + randomness
            val = int(
                5
                + 3 * math.sin(self.t)
                + 2 * math.sin(self.t * 0.5)
                + random.uniform(-1, 1)
            )
            val = max(0, min(10, val))  # clamp between 0–10
            data.append(val)

        self.t += 0.15
        return data

    def refresh_data(self):
        data = self.generate_data()
        self.hist.update_data(data)


if __name__ == "__main__":
    LiveApp().run()
