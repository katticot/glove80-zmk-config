#!/usr/bin/env python3
"""Record key events from a Glove80 (or any keyboard) on macOS.

Run this program, click the large test area, then press one physical key at a
time.  It deliberately consumes Tab and Escape so they are recorded instead of
moving focus or closing a window.

Events are written to glove80_key_probe.log beside this file, oldest first, under
a header naming the time the probe started.
"""

from __future__ import annotations

import datetime as dt
import tkinter as tk
from pathlib import Path


LOG_PATH = Path(__file__).with_name("glove80_key_probe.log")


class KeyProbe(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        # Fixed at launch: the log header names when the probe started, which is
        # not the time of the most recent keystroke.
        self.started = dt.datetime.now()
        self.title("Glove80 key probe")
        self.minsize(760, 480)
        self.configure(bg="#10151f")

        tk.Label(
            self,
            text="Glove80 firmware key probe",
            font=("Helvetica", 24, "bold"),
            fg="#e8edf6",
            bg="#10151f",
        ).pack(pady=(28, 8))
        tk.Label(
            self,
            text=(
                "Click the panel below. Press one physical key at a time.\n"
                "Events are appended to tools/glove80_key_probe.log, oldest first."
            ),
            font=("Helvetica", 14),
            fg="#aeb9ca",
            bg="#10151f",
            justify="center",
        ).pack(pady=(0, 16))

        self.latest = tk.StringVar(value="Waiting for a key press…")
        self.panel = tk.Label(
            self,
            textvariable=self.latest,
            font=("Menlo", 18),
            fg="#7ee7c4",
            bg="#192333",
            padx=24,
            pady=32,
            relief="flat",
            takefocus=True,
        )
        self.panel.pack(fill="x", padx=36)
        self.panel.bind("<Button-1>", lambda _event: self.panel.focus_set())

        self.history = tk.Text(
            self,
            height=11,
            font=("Menlo", 12),
            fg="#dce5f2",
            bg="#10151f",
            insertbackground="#ffffff",
            state="disabled",
            wrap="none",
        )
        self.history.pack(fill="both", expand=True, padx=36, pady=(18, 28))

        self.bind_all("<KeyPress>", self.record)
        # Tk windows occasionally start behind another app on macOS.  Bring the
        # probe forward and force focus so special keys are measured here.
        self.after(100, self.activate_probe)

    def activate_probe(self) -> None:
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(250, lambda: self.attributes("-topmost", False))
        self.focus_force()
        self.panel.focus_force()

    def record(self, event: tk.Event) -> str:
        timestamp = dt.datetime.now().strftime("%H:%M:%S")
        character = repr(event.char) if event.char else "(none)"
        modifiers = []
        if event.state & 0x0001:
            modifiers.append("Shift")
        if event.state & 0x0004:
            modifiers.append("Ctrl")
        if event.state & 0x0008:
            modifiers.append("Alt")
        if event.state & 0x0010:
            modifiers.append("Cmd")
        chord = "+".join([*modifiers, event.keysym])
        line = (
            f"{timestamp}  result={chord:<18} keysym={event.keysym:<12} "
            f"char={character:<8} keycode={event.keycode} state=0x{event.state:04x}"
        )
        self.latest.set(line)
        self.history.configure(state="normal")
        self.history.insert("end", line + "\n")
        self.history.see("end")
        self.history.configure(state="disabled")
        LOG_PATH.write_text(
            f"# Glove80 key probe — started {self.started.isoformat()}\n"
            + self.history.get("1.0", "end-1c")
            + "\n",
            encoding="utf-8",
        )
        return "break"


if __name__ == "__main__":
    KeyProbe().mainloop()
