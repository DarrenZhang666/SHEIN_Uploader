# -*- coding: utf-8 -*-
"""
开发者模式模块 —— 与业务代码隔离，交付客户时删除此文件及 GUI 中的相关调用即可。

功能：
  1. 发布失败后停留在原界面，不做任何跳转
  2. 点击「停止」按钮后也停留在当前页面，不跳转
"""

import tkinter as tk
from tkinter import simpledialog

_DEV_PASSWORD = "666666"

# ── 全局状态 ─────────────────────────────────────────
_developer_mode = False


def is_dev_mode():
    """外部查询当前是否处于开发者模式。"""
    return _developer_mode


def set_dev_mode(enabled):
    global _developer_mode
    _developer_mode = enabled


# ── GUI 组件 ─────────────────────────────────────────
class DevModeToggle(tk.Frame):
    """
    开发者模式滑动开关组件。
    默认关闭（黑色轨道），开启后变绿色。
    首次开启需要输入密码。
    """

    TRACK_W = 40
    TRACK_H = 20
    KNOB_R  = 8
    PAD     = 2

    def __init__(self, parent, bg="#23263a", **kw):
        super().__init__(parent, bg=bg, **kw)
        self._on = False
        self._authed = False

        tk.Label(self, text="Dev", font=("Segoe UI", 9),
                 fg="#a0a3b1", bg=bg).pack(side="left", padx=(0, 4))

        self._canvas = tk.Canvas(
            self, width=self.TRACK_W, height=self.TRACK_H,
            bg=bg, highlightthickness=0, cursor="hand2")
        self._canvas.pack(side="left")
        self._canvas.bind("<Button-1>", self._on_click)
        self._draw()

    # ── 绘制 ──

    def _draw(self):
        c = self._canvas
        c.delete("all")
        w, h, r, pad = self.TRACK_W, self.TRACK_H, self.KNOB_R, self.PAD
        track_color = "#4cde96" if self._on else "#3a3d55"
        c.create_oval(0, 0, h, h, fill=track_color, outline=track_color)
        c.create_oval(w - h, 0, w, h, fill=track_color, outline=track_color)
        c.create_rectangle(h // 2, 0, w - h // 2, h,
                           fill=track_color, outline=track_color)
        knob_x = (w - r - pad) if self._on else (r + pad)
        knob_y = h // 2
        c.create_oval(knob_x - r, knob_y - r, knob_x + r, knob_y + r,
                      fill="#ffffff", outline="#ffffff")

    # ── 交互 ──

    def _on_click(self, _event=None):
        if self._on:
            self._on = False
            set_dev_mode(False)
            self._draw()
            return

        if not self._authed:
            pwd = simpledialog.askstring(
                "开发者模式", "请输入开发者密码：",
                show="*", parent=self.winfo_toplevel())
            if pwd != _DEV_PASSWORD:
                return
            self._authed = True

        self._on = True
        set_dev_mode(True)
        self._draw()
