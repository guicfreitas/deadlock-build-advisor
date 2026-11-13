"""Small control window: the app's "home" when it runs as an installed .exe (no console).

Shows the status line and has buttons to open the web page, show/hide the overlay, open
the settings and quit. Closing it quits the app; the overlay is a child window of it.
"""
from __future__ import annotations

import tkinter as tk
import webbrowser
from typing import Callable

from .app import Advisor
from .i18n import t

BG, CARD, FG, DIM, ACC, GOOD, BAD = "#0e1016", "#171a23", "#e8e6e3", "#8b8f9a", "#e0b25a", "#6fcf7f", "#e06a6a"
DOT = {"ready": GOOD, "loading": ACC, "error": BAD, "setup": BAD}


class Panel:
    def __init__(self, advisor: Advisor, url: str, overlay: bool, alpha: float,
                 on_quit: Callable[[], None]):
        self.advisor, self.url, self.on_quit = advisor, url, on_quit
        self.root = tk.Tk()
        self.root.title("Deadlock Build Advisor")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.version = -1

        head = tk.Frame(self.root, bg=BG, padx=16, pady=12)
        head.pack(fill="x")
        tk.Label(head, text="Deadlock Build Advisor", fg=ACC, bg=BG,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        row = tk.Frame(head, bg=BG)
        row.pack(fill="x", pady=(6, 0))
        self.dot = tk.Label(row, text="●", fg=DIM, bg=BG, font=("Segoe UI", 11))
        self.dot.pack(side="left")
        self.status = tk.Label(row, text=t("pnl.starting"), fg=FG, bg=BG, font=("Segoe UI", 10),
                               wraplength=330, justify="left", anchor="w")
        self.status.pack(side="left", fill="x", padx=(6, 0))

        btns = tk.Frame(self.root, bg=BG, padx=16, pady=(4))
        btns.pack(fill="x")
        self._button(btns, t("pnl.open"), lambda: webbrowser.open(self.url), primary=True)
        self.ov_btn = self._button(btns, t("pnl.hide_overlay"), self.toggle_overlay)
        self._button(btns, t("pnl.settings"), lambda: webbrowser.open(self.url + "/#settings"))
        self._button(btns, t("pnl.quit"), self.quit)
        tk.Label(self.root, text=t("pnl.page", url=url), fg=DIM, bg=BG,
                 font=("Segoe UI", 8), padx=16, pady=10).pack(anchor="w")

        self.overlay = None
        if overlay:
            from .overlay import Overlay
            self.overlay = Overlay(advisor, alpha, master=self.root)
        else:
            self.ov_btn.configure(state="disabled", text=t("pnl.overlay_off"))
        self.root.after(300, self._tick)

    def _button(self, parent, text, cmd, primary=False):
        b = tk.Button(parent, text=text, command=cmd, relief="flat", cursor="hand2",
                      bg=ACC if primary else CARD, fg="#1a1408" if primary else FG,
                      activebackground=ACC, font=("Segoe UI", 10, "bold" if primary else "normal"),
                      padx=12, pady=6, bd=0)
        b.pack(side="left", padx=(0, 8), pady=4)
        return b

    def toggle_overlay(self):
        if self.overlay:
            self.overlay.toggle_visible()

    def _tick(self):
        s = self.advisor.state.snapshot()
        if s["version"] != self.version:
            self.version = s["version"]
            self.status.configure(text=s.get("message") or s.get("status", ""))
            self.dot.configure(fg=DOT.get(s.get("status"), DIM))
        if self.overlay:
            self.ov_btn.configure(text=t("pnl.show_overlay") if self.overlay.hidden else t("pnl.hide_overlay"))
        self.root.after(1000, self._tick)

    def quit(self):
        self.root.destroy()
        self.on_quit()

    def run(self):
        self.root.mainloop()
