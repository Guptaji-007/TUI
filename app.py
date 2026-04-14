import subprocess
from dataclasses import dataclass
from typing import Iterable

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, Static


@dataclass
class ProcessRow:
    pid: int
    cpu: float
    mem: float
    rss_kb: int
    etime: str
    command: str


class ProcessListApp(App):
    TITLE = "Process Monitor"
    SUB_TITLE = "Live process list"

    CSS = """
    Screen {
        background: #0b1418;
        color: #d9e7ea;
    }

    #main {
        height: 1fr;
        padding: 1 2;
    }

    #toolbar {
        height: 3;
        margin-bottom: 1;
        border: round #2f4f58;
        background: #132229;
        color: #b7d8df;
        padding: 0 1;
    }

    #filter {
        width: 60%;
        margin-right: 1;
        background: #18303a;
        color: #dff4f8;
    }

    #hint {
        width: 1fr;
        content-align: right middle;
        color: #9dc2ca;
    }

    #table {
        height: 1fr;
        min-height: 8;
        border: round #37606c;
        background: #0f1c21;
    }

    #status {
        height: 1;
        margin-top: 1;
        color: #9cc0c8;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh_now", "Refresh"),
        Binding("s", "cycle_sort", "Sort"),
        Binding("f", "focus_filter", "Filter"),
    ]

    sort_mode = "cpu"
    filter_text = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="main"):
            with Horizontal(id="toolbar"):
                yield Input(placeholder="Filter by command, e.g. python", id="filter")
                yield Static("Sort: CPU (press s to cycle)", id="hint")
            yield DataTable(id="table", zebra_stripes=True)
            yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#table", DataTable)
        table.cursor_type = "row"
        table.add_columns("PID", "CPU%", "MEM%", "RSS MB", "ELAPSED", "COMMAND")
        self._refresh_table()
        self.set_interval(2.0, self._refresh_table)

    def _run_ps(self) -> Iterable[ProcessRow]:
        command = ["ps", "-axo", "pid,pcpu,pmem,rss,etime,comm"]
        result = subprocess.run(command, capture_output=True, text=True, check=True)

        rows: list[ProcessRow] = []
        for line in result.stdout.splitlines()[1:]:
            raw = line.strip()
            if not raw:
                continue

            parts = raw.split(None, 5)
            if len(parts) != 6:
                continue

            pid_s, cpu_s, mem_s, rss_s, etime, cmd = parts
            try:
                rows.append(
                    ProcessRow(
                        pid=int(pid_s),
                        cpu=float(cpu_s),
                        mem=float(mem_s),
                        rss_kb=int(rss_s),
                        etime=etime,
                        command=cmd,
                    )
                )
            except ValueError:
                continue

        return rows

    def _sort_rows(self, rows: list[ProcessRow]) -> list[ProcessRow]:
        if self.sort_mode == "cpu":
            return sorted(rows, key=lambda item: item.cpu, reverse=True)
        if self.sort_mode == "mem":
            return sorted(rows, key=lambda item: item.mem, reverse=True)
        if self.sort_mode == "rss":
            return sorted(rows, key=lambda item: item.rss_kb, reverse=True)
        if self.sort_mode == "pid":
            return sorted(rows, key=lambda item: item.pid)
        return sorted(rows, key=lambda item: item.command.lower())

    def _refresh_table(self) -> None:
        try:
            rows = list(self._run_ps())
        except subprocess.CalledProcessError as error:
            self.query_one("#status", Static).update(f"Failed to read process list: {error}")
            return

        if self.filter_text:
            needle = self.filter_text.lower()
            rows = [row for row in rows if needle in row.command.lower()]

        rows = self._sort_rows(rows)

        table = self.query_one("#table", DataTable)
        table.clear()
        for row in rows:
            table.add_row(
                str(row.pid),
                f"{row.cpu:.1f}",
                f"{row.mem:.1f}",
                f"{row.rss_kb / 1024:.1f}",
                row.etime,
                row.command,
            )

        self.query_one("#status", Static).update(
            f"Processes: {len(rows)} | Filter: {self.filter_text or 'none'} | Sort: {self.sort_mode.upper()}"
        )
        self.query_one("#hint", Static).update(
            "Sort: " + self.sort_mode.upper() + " (press s to cycle)"
        )

    def action_refresh_now(self) -> None:
        self._refresh_table()

    def action_cycle_sort(self) -> None:
        order = ["cpu", "mem", "rss", "pid", "command"]
        current_index = order.index(self.sort_mode)
        self.sort_mode = order[(current_index + 1) % len(order)]
        self._refresh_table()

    def action_focus_filter(self) -> None:
        self.query_one("#filter", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "filter":
            return
        self.filter_text = event.value.strip()
        self._refresh_table()


if __name__ == "__main__":
    ProcessListApp().run()
