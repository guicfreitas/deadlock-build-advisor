"""Always-on-top translucent overlay drawn over the game (tkinter, stdlib only).

Works with Deadlock in *Borderless Windowed* / *Windowed* mode (exclusive
fullscreen draws over any other window). It is a separate window - nothing is
injected into the game.

Controls: drag with left mouse, double-click to collapse/expand, right-click to hide
(the control panel brings it back).
"""
from __future__ import annotations

import tkinter as tk

from .app import Advisor
from .i18n import t

BG, FG, DIM, ACC, GOOD, BAD = "#11131a", "#e8e6e3", "#8b8f9a", "#e0b25a", "#6fcf7f", "#e06a6a"
SLOT_COLORS = {"weapon": "#e39a3b", "vitality": "#6fbf5a", "spirit": "#a77be0"}


class Overlay:
    def __init__(self, advisor: Advisor, alpha: float = 0.88, master: tk.Misc | None = None):
        self.advisor = advisor
        self.root = tk.Toplevel(master) if master is not None else tk.Tk()
        self.hidden = False
        self.root.title("Deadlock Build Advisor")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", alpha)
        self.root.configure(bg=BG)
        self.root.geometry("+24+140")
        self.collapsed = False
        self.version = -1
        self.body = tk.Frame(self.root, bg=BG, padx=10, pady=8)
        self.body.pack(fill="both", expand=True)
        for w in (self.root, self.body):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._drag)
            w.bind("<Double-Button-1>", self._toggle)
            w.bind("<Button-3>", lambda e: self.hide())
        self._dx = self._dy = 0
        self.root.after(200, self._tick)

    def hide(self):
        self.hidden = True
        self.root.withdraw()

    def show(self):
        self.hidden = False
        self.root.deiconify()
        self.root.attributes("-topmost", True)

    def toggle_visible(self):
        self.show() if self.hidden else self.hide()

    def _start_drag(self, e):
        self._dx, self._dy = e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y()

    def _drag(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _toggle(self, _e=None):
        self.collapsed = not self.collapsed
        self.version = -1

    def _label(self, text, fg=FG, size=10, bold=False, **kw):
        lbl = tk.Label(self.body, text=text, fg=fg, bg=BG, anchor="w", justify="left",
                       font=("Segoe UI", size, "bold" if bold else "normal"), **kw)
        lbl.pack(fill="x")
        for ev, fn in (("<ButtonPress-1>", self._start_drag), ("<B1-Motion>", self._drag),
                       ("<Double-Button-1>", self._toggle)):
            lbl.bind(ev, fn)
        return lbl

    def _items(self, title, items):
        if not items:
            return
        self._label(title, ACC, 9, True)
        for it in items:
            lift = it["lift"]
            sign = f"+{lift}" if lift > 0 else f"{lift}"
            color = SLOT_COLORS.get(it["slot"], FG)
            self._label(f"  ● {it['name']}  ·  {it['cost']}  ·  {it['wr']}% ({sign})", color, 9)

    def _render(self, s: dict):
        for w in self.body.winfo_children():
            w.destroy()
        rec = s.get("recommendation")
        head = "Deadlock Build Advisor"
        if rec:
            head += f" — {rec['hero']['name']}"
        self._label(head + ("  [+]" if self.collapsed else ""), FG, 11, True)
        if self.collapsed:
            return
        if not rec:
            self._label(s.get("message", ""), DIM, 9, wraplength=320)
            return
        for sw in ((s.get("live_items") or {}).get("suggestions") or [])[:2]:
            buy, drop = sw["buy"]["name"], (sw.get("instead_of") or {}).get("name")
            text = t("ov.swap", buy=buy, drop=drop) if drop else t("ov.also", buy=buy)
            self._label(text, ACC, 9, True, wraplength=340)
            self._label(t("ov.against", threat=sw["threat_label"]), DIM, 8, wraplength=340)
        if rec["lane_enemies"]:
            parts = []
            for e in rec["lane_enemies"]:
                mu = e.get("matchup")
                parts.append(f"{e['name']} ({mu['wr']}%)" if mu else e["name"])
            self._label(t("ov.lane_vs", list=", ".join(parts)), DIM, 9)
        self._items(t("ov.lane", min=rec["settings"]["lane_window_min"], cost=rec["lane_cost"]),
                    rec["lane_build"])
        fb = rec["full_build"]
        self._items(t("ov.mid"), fb.get("mid"))
        self._items(t("ov.late"), fb.get("late"))
        order = rec.get("ability_order")
        if order:
            self._label(t("ov.abilities"), ACC, 9, True)
            self._label("  " + " ".join(str(st["slot"]) for st in order["steps"]), FG, 10, True)
        self._label(t("ov.hint"), DIM, 8)

    def _tick(self):
        s = self.advisor.state.snapshot()
        if s["version"] != self.version:
            self.version = s["version"]
            self._render(s)
        self.root.after(1000, self._tick)

    def run(self):
        self.root.mainloop()
