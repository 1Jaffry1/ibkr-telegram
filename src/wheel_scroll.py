"""Mouse wheel + macOS trackpad scrolling for Tk 9 / Tk 8."""

from __future__ import annotations

import platform
import tkinter as tk

_WHEEL_WINDOWS: set[int] = set()


def _point_in_widget(widget, x_root, y_root):
    try:
        x0 = widget.winfo_rootx()
        y0 = widget.winfo_rooty()
        w, h = widget.winfo_width(), widget.winfo_height()
        return w > 1 and h > 1 and x0 <= x_root < x0 + w and y0 <= y_root < y0 + h
    except tk.TclError:
        return False


def _event_root_xy(event):
    x_root = getattr(event, "x_root", None)
    y_root = getattr(event, "y_root", None)
    if x_root is not None and y_root is not None:
        return x_root, y_root
    try:
        return event.widget.winfo_pointerxy()
    except tk.TclError:
        return None, None


def _precise_deltas(event):
    """Tk 9 trackpad: two-finger scroll uses <TouchpadScroll>, not <MouseWheel>."""
    try:
        result = event.widget.tk.call("tk::PreciseScrollDeltas", event.delta)
        if len(result) >= 2:
            return int(result[0]), int(result[1])
    except tk.TclError:
        pass
    return 0, 0


def _mousewheel_units(event):
    delta = getattr(event, "delta", 0) or 0
    if delta:
        if platform.system() == "Darwin":
            return 0, -int(delta)
        if abs(delta) >= 120:
            return 0, -int(delta / 120)
        return 0, -1 if delta > 0 else 1
    num = getattr(event, "num", None)
    if num == 4:
        return 0, -1
    if num == 5:
        return 0, 1
    return 0, 0


def _canvas_can_scroll_y(canvas):
    try:
        top, bottom = canvas.yview()
        return (bottom - top) < 0.999
    except tk.TclError:
        return False


def _apply_scroll(target, dx, dy):
    try:
        if isinstance(target, tk.Canvas):
            if dy and _canvas_can_scroll_y(target):
                target.yview("scroll", dy, "units")
            if dx:
                left, right = target.xview()
                if (right - left) < 0.999:
                    target.xview("scroll", dx, "units")
        elif dy:
            target.yview_scroll(dy, "units")
    except tk.TclError:
        pass


def _scroll_blocks_widget(widget):
    try:
        import customtkinter as ctk
        blocked = (ctk.CTkTextbox, ctk.CTkScrollbar, ctk.CTkSlider)
    except ImportError:
        blocked = ()
    current = widget
    while current is not None:
        if isinstance(current, (tk.Text, tk.Scrollbar) + blocked):
            return True
        current = getattr(current, "master", None)
    return False


def _pick_registration(window, event):
    registrations = getattr(window, "_ibkr_wheel_scroll", ())
    if not registrations:
        return None

    if _scroll_blocks_widget(event.widget):
        return None

    x_root, y_root = _event_root_xy(event)
    if x_root is None:
        return None

    for widget in getattr(window, "_ibkr_scroll_block_widgets", ()):
        if _point_in_widget(widget, x_root, y_root):
            return None

    for reg in reversed(registrations):
        target = reg["target"]
        areas = reg["areas"]
        if isinstance(event.widget, tk.Text) and event.widget is not target:
            continue
        if any(_point_in_widget(area, x_root, y_root) for area in areas):
            return reg
        if reg.get("full_window") and _point_in_widget(window, x_root, y_root):
            return reg
    return None


def _window_scroll(event, dx, dy):
    if not dx and not dy:
        return
    try:
        window = event.widget.winfo_toplevel()
    except tk.TclError:
        return

    reg = _pick_registration(window, event)
    if reg is None:
        return

    refresh = reg.get("refresh")
    if refresh:
        refresh()
    _apply_scroll(reg["target"], dx, dy)
    return "break"


def _window_mousewheel(event):
    dx, dy = _mousewheel_units(event)
    return _window_scroll(event, dx, dy)


def _window_touchpad(event):
    tdx, tdy = _precise_deltas(event)
    return _window_scroll(event, -tdx if tdx else 0, -tdy if tdy else 0)


def _ensure_window_wheel(window):
    wid = id(window)
    if wid in _WHEEL_WINDOWS:
        return
    _WHEEL_WINDOWS.add(wid)

    for sequence, handler in (
        ("<MouseWheel>", _window_mousewheel),
        ("<Button-4>", _window_mousewheel),
        ("<Button-5>", _window_mousewheel),
        ("<TouchpadScroll>", _window_touchpad),
    ):
        window.bind(sequence, handler, add="+")
        window.bind_all(sequence, handler, add="+")


def bind_mousewheel(window, scroll_target, *hover_roots, block_widgets=None, full_window=False):
    """
    Scroll a Canvas or Text via the parent window.

    Handles:
    - <MouseWheel> / Button-4 / Button-5 (mouse wheel)
    - <TouchpadScroll> (Tk 9 macOS two-finger gesture — required on your setup)
    """
    areas = list(hover_roots) if hover_roots else [scroll_target]
    registrations = getattr(window, "_ibkr_wheel_scroll", None)
    if registrations is None:
        window._ibkr_wheel_scroll = []
        registrations = window._ibkr_wheel_scroll
        _ensure_window_wheel(window)

    if block_widgets:
        existing = getattr(window, "_ibkr_scroll_block_widgets", None)
        if existing is None:
            window._ibkr_scroll_block_widgets = list(block_widgets)
        else:
            for widget in block_widgets:
                if widget not in existing:
                    existing.append(widget)

    def refresh(_event=None):
        if not isinstance(scroll_target, tk.Canvas):
            return
        try:
            scroll_target.update_idletasks()
            bbox = scroll_target.bbox("all")
            if bbox is not None:
                scroll_target.configure(scrollregion=bbox)
        except tk.TclError:
            pass

    entry = {"target": scroll_target, "areas": areas, "refresh": refresh, "full_window": full_window}
    if entry not in registrations:
        registrations.append(entry)

    if isinstance(scroll_target, tk.Canvas):
        scroll_target._ibkr_refresh_scroll = refresh
        for area in areas:
            if hasattr(area, "bind"):
                area.bind("<Configure>", refresh, add="+")
        window.after_idle(refresh)
