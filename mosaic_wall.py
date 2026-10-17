#!/usr/bin/env python3
"""
Mosaic Wall - a multi-video wall player built on libmpv (python-mpv) + PySide6.

Every tile is its own embedded mpv instance. Tiles are sized from each clip's
real shape (vertical clips get tall, narrow tiles) with no gaps between them.
Videos, animated GIFs and still images can all be mixed on the wall.

Run:   python mosaic_wall.py [files or folders ...]
Keys:  Space = pause/play all   M = mute/unmute   N = next clips
       R = random seek          F = fullscreen    Esc = leave fullscreen
Mouse: drag a tile onto another tile = swap them
       double-click a tile = focus view, right-click a tile = tile menu
       drop files from your file manager onto a tile = play them in that tile
Env:   MOSAIC_HWDEC (default auto-safe), MOSAIC_THREADS (decoder threads per tile)
"""
import json
import locale
import math
import os
import random
import sys
from pathlib import Path

# --- make libmpv discoverable on Windows (put mpv-2.dll / libmpv-2.dll next to this file)
HERE = os.path.dirname(os.path.abspath(__file__))
if sys.platform == "win32":
    os.environ["PATH"] = HERE + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(HERE)
elif sys.platform.startswith("linux"):
    # Embedding via window id needs X11 (runs through XWayland on Wayland desktops)
    os.environ["QT_QPA_PLATFORM"] = "xcb"
    os.environ.pop("WAYLAND_DISPLAY", None)

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QLabel, QMainWindow, QMenu,
    QPushButton, QSlider, QSpinBox, QToolBar, QWidget,
)

try:
    import mpv
except (ImportError, OSError) as exc:  # OSError = libmpv not found
    sys.exit(
        f"Could not load mpv: {exc}\n"
        "Install python-mpv (pip install python-mpv) and make sure libmpv is available:\n"
        "  Windows: put mpv-2.dll (from an mpv 'libmpv' dev build) next to this script\n"
        "  Linux:   sudo apt install libmpv2     macOS: brew install mpv"
    )

VIDEO_EXT = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".flv", ".ts",
    ".mpg", ".mpeg", ".gif", ".3gp", ".ogv", ".m2ts",
}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".avif", ".jxl"}
MEDIA_EXT = VIDEO_EXT | IMAGE_EXT
MAX_TILES = 200
MODES = ["Loop each clip", "Play next when finished", "Random start, then next"]
FITS = ["Fill (crop)", "Fit (black bars)", "Stretch"]
LAYOUTS = ["Auto mosaic", "Single row", "Single column", "Hero (1 big + rest)"]
VIEWS_FILE = Path.home() / ".config" / "mosaic_wall" / "views.json"
DEFAULT_VIEW = {"fit": None, "ax": 0.0, "ay": 0.0, "zoom": 0.0}


def collect_media(paths):
    out = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            out += sorted(str(f) for f in p.rglob("*") if f.suffix.lower() in MEDIA_EXT)
        elif p.is_file() and p.suffix.lower() in MEDIA_EXT:
            out.append(str(p))
    return out


# ---------------------------------------------------------------- layout math
def pack(aspects, W, H, rows=None):
    """Justified-rows mosaic: tiles keep (about) their video shape, rows span the
    full width and together span the full height. Returns [(x, y, w, h), ...]."""
    return _pack(aspects, W, H, rows)[1]


def pack_auto(aspects, W, H):
    """Try both a row-based and a column-based mosaic; keep the one that
    distorts the video shapes least."""
    c_rows, r_rows = _pack(aspects, W, H)
    c_cols, r_cols = _pack([1 / a for a in aspects], H, W)
    if c_cols < c_rows - 1e-9:
        return [(y, x, h, w) for x, y, w, h in r_cols]  # transpose back
    return r_rows


def _pack(aspects, W, H, rows=None):
    n = len(aspects)
    if n == 0:
        return 0.0, []
    total = sum(aspects)
    best = None
    for r in ([rows] if rows else range(1, n + 1)):
        groups, acc = [[]], 0.0
        for i, a in enumerate(aspects):
            need = r - len(groups)
            if groups[-1] and need > 0 and (acc + a / 2 > total * len(groups) / r or n - i <= need):
                groups.append([])
            groups[-1].append(i)
            acc += a
        if len(groups) != r:
            continue
        sums = [sum(aspects[i] for i in g) for g in groups]
        k = H / sum(W / s for s in sums)  # vertical squeeze needed to fill the height
        cost = abs(math.log(k))
        if best is None or cost < best[0]:
            best = (cost, groups, sums, k)
    if best is None:
        groups = [list(range(n))]
        sums = [total]
        k = H / (W / total)
        cost = abs(math.log(k))
    else:
        cost, groups, sums, k = best

    rects = [None] * n
    ycum, y0 = 0.0, 0
    for gi, (g, s) in enumerate(zip(groups, sums)):
        h = W / s * k
        ycum += h
        y1 = H if gi == len(groups) - 1 else round(ycum)
        xcum = 0.0
        for i in g:
            x0 = round(W * xcum / s)
            xcum += aspects[i]
            x1 = W if i == g[-1] else round(W * xcum / s)
            rects[i] = (x0, y0, x1 - x0, y1 - y0)
        y0 = y1
    return cost, rects


def layout_rects(aspects, W, H, mode):
    n = len(aspects)
    if n == 0:
        return []
    if n == 1:
        return [(0, 0, W, H)]
    if mode.startswith("Hero"):
        hw = int(min(max(H * aspects[0], 0.35 * W), 0.65 * W))
        rest = pack(aspects[1:], W - hw, H)
        return [(0, 0, hw, H)] + [(x + hw, y, w, h) for x, y, w, h in rest]
    if mode == "Single row":
        return pack(aspects, W, H, rows=1)
    if mode == "Single column":
        return pack(aspects, W, H, rows=n)
    return pack_auto(aspects, W, H)


class Playlist:
    """Shared queue; each tile pulls the next clip so tiles show different media."""

    def __init__(self):
        self.files, self.order, self.i, self.shuffle = [], [], 0, True

    def add(self, paths):
        for f in paths:
            if f not in self.files:
                self.files.append(f)
                self.order.append(f)
        if self.shuffle and self.i == 0:
            random.shuffle(self.order)

    def clear(self):
        self.files, self.order, self.i = [], [], 0

    def next(self):
        if not self.files:
            return None
        if self.i >= len(self.order):
            self.order = list(self.files)
            if self.shuffle:
                random.shuffle(self.order)
            self.i = 0
        f = self.order[self.i]
        self.i += 1
        return f


class Cell(QFrame):
    # Emitted from mpv's thread; Qt queues them onto the GUI thread.
    sig_eof = Signal()
    sig_loaded = Signal()
    sig_key = Signal(str)
    sig_aspect = Signal(float)

    def __init__(self, wall):
        super().__init__(wall)
        self.wall = wall
        self.path = None
        self.aspect = 16 / 9
        self._paused = None
        self.setAttribute(Qt.WA_NativeWindow)
        self.setStyleSheet("background:#000;")

        many = max(wall.target, len(wall.cells) + 1)
        threads = int(os.environ.get("MOSAIC_THREADS", 1 if many > 16 else 2))
        cache = "4MiB" if many > 24 else "16MiB"
        secs = wall.image_secs

        p = self.player = mpv.MPV(
            wid=str(int(self.winId())),
            vo="gpu",
            gpu_context="x11egl" if sys.platform.startswith("linux") else "auto",
            hwdec=os.environ.get("MOSAIC_HWDEC", "auto-safe"),
            profile="fast",
            vd_lavc_threads=threads,
            keep_open="yes",
            osc=False,
            input_default_bindings=False,
            input_vo_keyboard=True,
            input_cursor=False,  # mouse is handled by the wall's overlay window
            audio_display="no",
            mute=True,
            volume=wall.volume,
            image_display_duration="inf" if secs <= 0 else secs,
            demuxer_max_bytes=cache,
            demuxer_max_back_bytes="4MiB" if many > 24 else "8MiB",
        )
        p.loop_file = "inf" if wall.mode == 0 else "no"
        self.apply_view()

        @p.property_observer("eof-reached")
        def _eof(_name, value):
            if value:
                self.sig_eof.emit()

        @p.property_observer("video-params")
        def _params(_name, value):
            try:
                if value and value.get("dw") and value.get("dh"):
                    self.sig_aspect.emit(float(value["dw"]) / float(value["dh"]))
            except Exception:
                pass

        @p.event_callback("file-loaded")
        def _loaded(_event):
            self.sig_loaded.emit()

        def bind(key, fn):
            @p.key_binding(key)
            def _cb(state, name, char):
                if state and state[0] in "dp":
                    fn()

        # keyboard fallback in case mpv's own window ever has focus
        for key, name in [("SPACE", "pause"), ("m", "mute"), ("n", "next"),
                          ("r", "random"), ("f", "fullscreen"), ("ESC", "escape")]:
            bind(key, lambda n=name: self.sig_key.emit(n))

        self.sig_eof.connect(self.on_eof)
        self.sig_loaded.connect(self.on_loaded)
        self.sig_aspect.connect(self.on_aspect)
        self.sig_key.connect(wall.handle_key)

    # ---- playback -------------------------------------------------------
    def set_paused(self, want):
        if self._paused != want:
            self._paused = want
            self.player.pause = want

    def load(self, path):
        if not path:
            return
        self.path = path
        self.apply_view()
        self.player.loadfile(path)
        self.set_paused(self.wall.paused)

    def on_eof(self):
        if self.wall.mode != 0:
            self.load(self.wall.playlist.next())

    def on_loaded(self):
        self.apply_view()
        if self.path:
            self.player.show_text(Path(self.path).name, 1500)
        if self.wall.mode == 2:
            self.random_seek()

    def on_aspect(self, a):
        self.aspect = min(max(a, 0.25), 4.0)
        self.wall.schedule_layout()

    def random_seek(self):
        try:
            dur = self.player.duration
            if dur and math.isfinite(dur) and dur > 10:
                self.player.seek(random.uniform(0, dur * 0.8), "absolute")
        except Exception:
            pass

    def next_clip(self):
        self.load(self.wall.playlist.next())

    def set_image_secs(self, secs):
        self.player["image-display-duration"] = "inf" if secs <= 0 else secs

    # ---- per-file view (fit / crop position / zoom) ---------------------
    def apply_view(self):
        p, v = self.player, self.wall.get_view(self.path)
        fit = self.wall.fit if v["fit"] is None else v["fit"]
        p["keepaspect"] = "no" if fit == 2 else "yes"
        p["panscan"] = 1.0 if fit == 0 else 0.0
        p["video-align-x"] = float(v["ax"])
        p["video-align-y"] = float(v["ay"])
        p["video-zoom"] = float(v["zoom"])

    def set_view(self, **kw):
        if self.path:
            self.wall.update_view(self.path, **kw)
            self.apply_view()

    def reset_view(self):
        if self.path:
            self.wall.reset_view(self.path)
            self.apply_view()

    # ---- menu -----------------------------------------------------------
    def show_menu(self):
        p = self.player
        win = self.wall.window
        m = QMenu(win)
        title = m.addAction(Path(self.path).name if self.path else "(empty)")
        title.setEnabled(False)
        m.addSeparator()

        m.addAction("Open file in this tile...", self.open_file_dialog)
        lib = m.addMenu("Pick from library")
        files = self.wall.playlist.files
        if not files:
            lib.setEnabled(False)
        for f in files[:60]:
            a = lib.addAction(Path(f).name)
            a.setCheckable(True)
            a.setChecked(f == self.path)
            a.triggered.connect(lambda _c=False, f=f: self.load(f))
        if len(files) > 60:
            more = lib.addAction(f"(+{len(files) - 60} more - use \"Open file in this tile...\")")
            more.setEnabled(False)
        m.addAction("Next clip", self.next_clip)
        m.addSeparator()

        m.addAction("Play / Pause", lambda: setattr(p, "pause", not p.pause))
        m.addAction("Unmute" if p.mute else "Mute", lambda: setattr(p, "mute", not p.mute))
        m.addAction("Solo audio (mute others)", lambda: self.wall.solo(self))
        m.addAction("Set A point", self.set_a)
        m.addAction("Set B point (start A-B loop)", self.set_b)
        m.addAction("Clear A-B loop", self.clear_ab)
        speed = m.addMenu("Speed")
        for s in (0.5, 0.75, 1.0, 1.5, 2.0):
            speed.addAction(f"{s}x", lambda _c=False, s=s: setattr(p, "speed", s))
        m.addAction("Random seek", self.random_seek)
        m.addSeparator()

        v = self.wall.get_view(self.path)
        vm = m.addMenu("Fit / crop (this file)")
        for label, val in [("Use default", None), ("Fill (crop)", 0),
                           ("Fit (black bars)", 1), ("Stretch", 2)]:
            a = vm.addAction(label)
            a.setCheckable(True)
            a.setChecked(v["fit"] == val)
            a.triggered.connect(lambda _c=False, val=val: self.set_view(fit=val))
        pos = vm.addMenu("Crop position")
        for label, ax, ay in [("Center", 0, 0), ("Left", -1, 0), ("Right", 1, 0),
                              ("Top", 0, -1), ("Bottom", 0, 1)]:
            pos.addAction(label, lambda _c=False, ax=ax, ay=ay: self.set_view(ax=float(ax), ay=float(ay)))
        vm.addAction("Zoom in", lambda: self.set_view(zoom=min(2.0, v["zoom"] + 0.15)))
        vm.addAction("Zoom out", lambda: self.set_view(zoom=max(-1.0, v["zoom"] - 0.15)))
        vm.addAction("Reset this file's view", self.reset_view)
        m.addSeparator()

        m.addAction("Focus view (toggle)", lambda: self.wall.toggle_focus(self))
        m.addAction("Exit fullscreen" if win.isFullScreen() else "Fullscreen", win.toggle_fullscreen)
        m.addAction("Remove this tile", lambda: self.wall.remove_cell(self))
        m.exec(QCursor.pos())

    def open_file_dialog(self):
        exts = " ".join(f"*{e}" for e in sorted(MEDIA_EXT))
        f, _ = QFileDialog.getOpenFileName(
            self.wall.window, "Open in this tile", "", f"Videos and images ({exts});;All files (*)")
        if f:
            self.wall.playlist.add([f])
            self.load(f)

    def set_a(self):
        t = self.player.time_pos
        if t is not None:
            self.player["ab-loop-a"] = t
            self.player.show_text(f"A = {t:.1f}s", 1000)

    def set_b(self):
        t = self.player.time_pos
        if t is not None:
            self.player["ab-loop-b"] = t
            self.player.show_text(f"B = {t:.1f}s  (looping)", 1000)

    def clear_ab(self):
        self.player["ab-loop-a"] = "no"
        self.player["ab-loop-b"] = "no"
        self.player.show_text("A-B loop cleared", 1000)

    def shutdown(self):
        try:
            self.player.terminate()
        except Exception:
            pass


class Wall(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.playlist = Playlist()
        self.cells = []
        self.target = 0
        self.focused = None
        self.paused = False
        self.muted = True
        self.volume = 70
        self.mode = 0
        self.fit = 0
        self.image_secs = 5
        self.layout_mode = LAYOUTS[0]
        self.views = self._load_views()
        self._layout_pending = False
        self._growing = False
        self.setStyleSheet("background:#000;")

    # ---- per-file view settings (saved between runs) --------------------
    def _load_views(self):
        try:
            return json.loads(VIEWS_FILE.read_text())
        except Exception:
            return {}

    def _save_views(self):
        try:
            VIEWS_FILE.parent.mkdir(parents=True, exist_ok=True)
            VIEWS_FILE.write_text(json.dumps(self.views))
        except Exception:
            pass

    def get_view(self, path):
        v = dict(DEFAULT_VIEW)
        v.update(self.views.get(path, {}))
        return v

    def update_view(self, path, **kw):
        self.views.setdefault(path, {}).update(kw)
        self._save_views()

    def reset_view(self, path):
        self.views.pop(path, None)
        self._save_views()

    # ---- cells ----------------------------------------------------------
    def set_cell_count(self, n):
        self.target = n
        while len(self.cells) > n:
            self._drop(self.cells.pop())
        self.relayout()
        if len(self.cells) < n and not self._growing:
            self._growing = True
            self._grow_step()

    def _grow_step(self):
        # Create tiles a couple at a time so the window stays responsive.
        made = 0
        while len(self.cells) < self.target and made < 2:
            c = Cell(self)
            self.cells.append(c)
            c.load(self.playlist.next())
            made += 1
        self.relayout()
        if len(self.cells) < self.target:
            QTimer.singleShot(30, self._grow_step)
        else:
            self._growing = False

    def _drop(self, c):
        if c is self.focused:
            self.focused = None
        c.shutdown()
        c.setParent(None)
        c.deleteLater()

    def remove_cell(self, c):
        if c not in self.cells or len(self.cells) <= 1:
            return
        self.cells.remove(c)
        self._drop(c)
        self.target = len(self.cells)
        sp = self.window.spin
        sp.blockSignals(True)
        sp.setValue(self.target)
        sp.blockSignals(False)
        self.relayout()

    def swap(self, a, b):
        if a in self.cells and b in self.cells and a is not b:
            i, j = self.cells.index(a), self.cells.index(b)
            self.cells[i], self.cells[j] = b, a
            self.layout_cells()

    def visible_cells(self):
        return [c for c in self.cells if c.isVisible()]

    def schedule_layout(self):
        if not self._layout_pending:
            self._layout_pending = True
            QTimer.singleShot(0, self._do_scheduled_layout)

    def _do_scheduled_layout(self):
        self._layout_pending = False
        self.layout_cells()

    def layout_cells(self):
        show = [self.focused] if self.focused in self.cells else self.cells
        rects = layout_rects([c.aspect for c in show], self.width(), self.height(), self.layout_mode)
        for c, (x, y, w, h) in zip(show, rects):
            c.setGeometry(x, y, max(w, 1), max(h, 1))

    def relayout(self):
        show = [self.focused] if self.focused in self.cells else self.cells
        for c in self.cells:
            vis = c in show
            c.setVisible(vis)
            c.set_paused(self.paused or not vis)
        self.layout_cells()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.layout_cells()

    # ---- library --------------------------------------------------------
    def add_paths(self, paths):
        files = collect_media(paths)
        if not files:
            return 0
        self.playlist.add(files)
        for c in self.cells:
            if not c.path:
                c.load(self.playlist.next())
        return len(files)

    def clear_library(self):
        self.playlist.clear()
        for c in self.cells:
            c.player.command("stop")
            c.path = None

    # ---- global controls ------------------------------------------------
    def set_mode(self, idx):
        self.mode = idx
        for c in self.cells:
            c.player.loop_file = "inf" if idx == 0 else "no"

    def set_image_secs(self, secs):
        self.image_secs = secs
        for c in self.cells:
            c.set_image_secs(secs)

    def set_fit(self, idx):
        """Default fit for every file that has no setting of its own."""
        self.fit = idx
        for c in self.cells:
            c.apply_view()

    def set_layout(self, name):
        self.layout_mode = name
        self.layout_cells()

    def toggle_pause(self):
        self.paused = not self.paused
        for c in self.cells:
            c.set_paused(self.paused or not c.isVisible())

    def set_muted(self, muted):
        self.muted = muted
        for c in self.cells:
            c.player.mute = muted

    def set_volume(self, v):
        self.volume = v
        for c in self.cells:
            c.player.volume = v

    def solo(self, cell):
        self.muted = False
        self.window.mute_action.setChecked(False)
        for c in self.cells:
            c.player.mute = c is not cell
            c.player.volume = self.volume

    def next_all(self):
        for c in self.cells:
            c.next_clip()

    def random_all(self):
        for c in self.cells:
            c.random_seek()

    def toggle_focus(self, cell):
        self.focused = None if self.focused is cell else cell
        if self.focused:
            self.solo(cell)
        else:
            self.set_muted(self.muted)
        self.relayout()

    def handle_key(self, name):
        w = self.window
        {
            "pause": self.toggle_pause,
            "mute": lambda: w.mute_action.toggle(),
            "next": self.next_all,
            "random": self.random_all,
            "fullscreen": w.toggle_fullscreen,
            "escape": w.leave_fullscreen,
        }[name]()

    def shutdown(self):
        for c in self.cells:
            c.shutdown()


class Overlay(QWidget):
    """Invisible window laid over the wall. mpv's native windows swallow mouse input,
    so this catches clicks, right-click menus, tile dragging and file drops."""

    def __init__(self, wall):
        super().__init__(wall.window, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.wall = wall
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.press = None
        self.src = None
        self.dst = None
        self.dragging = False
        self.cursor_pos = QPoint()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sync)
        self.timer.start(40)

    def sync(self):
        mw = self.wall.window
        if not mw.isVisible() or (mw.windowState() & Qt.WindowMinimized):
            self.hide()
            return
        r = QRect(self.wall.mapToGlobal(QPoint(0, 0)), self.wall.size())
        if self.geometry() != r:
            self.setGeometry(r)
        if not self.isVisible():
            self.show()
            self.raise_()

    def cell_at(self, pos):
        for c in self.wall.visible_cells():
            if c.geometry().contains(pos):
                return c
        return None

    def _reset(self):
        self.press = self.src = self.dst = None
        self.dragging = False
        self.unsetCursor()
        self.update()

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        c = self.cell_at(pos)
        if e.button() == Qt.RightButton and c:
            QTimer.singleShot(0, c.show_menu)
        elif e.button() == Qt.LeftButton:
            self.press, self.src, self.dst, self.dragging = pos, c, None, False

    def mouseMoveEvent(self, e):
        if self.press is None or self.src is None:
            return
        pos = e.position().toPoint()
        if not self.dragging and (pos - self.press).manhattanLength() > 10 and self.wall.focused is None:
            self.dragging = True
            self.setCursor(Qt.ClosedHandCursor)
        if self.dragging:
            self.dst = self.cell_at(pos)
            self.cursor_pos = pos
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self.dragging and self.src and self.dst and self.dst is not self.src:
            self.wall.swap(self.src, self.dst)
        self._reset()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            c = self.cell_at(e.position().toPoint())
            self._reset()
            if c:
                self.wall.toggle_focus(c)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))  # almost invisible, but still catches the mouse
        if not self.dragging or not self.src:
            return
        p.fillRect(self.src.geometry(), QColor(0, 0, 0, 120))
        if self.dst and self.dst is not self.src:
            r = self.dst.geometry()
            p.fillRect(r, QColor(0, 150, 255, 80))
            p.setPen(QPen(QColor(0, 170, 255), 4))
            p.drawRect(r.adjusted(2, 2, -2, -2))
        name = Path(self.src.path).name if self.src.path else "(empty)"
        fm = p.fontMetrics()
        box = QRect(self.cursor_pos.x() + 14, self.cursor_pos.y() + 14,
                    fm.horizontalAdvance(name) + 16, fm.height() + 8)
        p.fillRect(box, QColor(20, 20, 20, 220))
        p.setPen(Qt.white)
        p.drawText(box, Qt.AlignCenter, name)

    # files dragged in from a file manager: drop on a tile to play them there
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        self.wall.window.drop_paths(paths, self.cell_at(e.position().toPoint()))
        e.acceptProposedAction()


class ExitFullscreenButton(QPushButton):
    """Small always-on-top window (a normal child widget would be hidden behind mpv's native windows)."""

    def __init__(self, main):
        super().__init__("\u2715  Exit fullscreen")
        self.main = main
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QPushButton{background:rgba(20,20,20,230);color:white;border:1px solid #777;"
            "border-radius:6px;padding:8px 14px;font-size:14px;}"
            "QPushButton:hover{background:#c0392b;}"
        )
        self.clicked.connect(main.toggle_fullscreen)

    def place(self):
        self.adjustSize()
        g = self.main.geometry()
        self.move(g.right() - self.width() - 16, g.top() + 16)
        self.show()
        self.raise_()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mosaic Wall (mpv)")
        self.resize(1280, 720)
        self.wall = Wall(self)
        self.setCentralWidget(self.wall)
        self.setAcceptDrops(True)

        tb = self.toolbar = QToolBar("Controls")
        tb.setMovable(False)
        self.addToolBar(tb)

        tb.addAction("Add files", self.add_files)
        tb.addAction("Add folder", self.add_folder)
        tb.addAction("Clear", self.wall.clear_library)
        tb.addSeparator()

        tb.addWidget(QLabel(" Tiles "))
        self.spin = QSpinBox()
        self.spin.setRange(1, MAX_TILES)
        self.spin.setValue(4)
        self.spin.setKeyboardTracking(False)  # typing "40" shouldn't build 4 tiles first
        self.spin.valueChanged.connect(self.wall.set_cell_count)
        tb.addWidget(self.spin)

        tb.addWidget(QLabel("  Layout "))
        lay = QComboBox()
        lay.addItems(LAYOUTS)
        lay.currentTextChanged.connect(self.wall.set_layout)
        tb.addWidget(lay)

        tb.addWidget(QLabel("  Default fit "))
        fit = QComboBox()
        fit.addItems(FITS)
        fit.currentIndexChanged.connect(self.wall.set_fit)
        tb.addWidget(fit)

        tb.addWidget(QLabel("  Mode "))
        mode = QComboBox()
        mode.addItems(MODES)
        mode.currentIndexChanged.connect(self.wall.set_mode)
        tb.addWidget(mode)

        tb.addWidget(QLabel("  Image secs "))
        img = QSpinBox()
        img.setRange(0, 300)
        img.setValue(self.wall.image_secs)
        img.setSpecialValueText("\u221e")  # 0 = show forever
        img.setKeyboardTracking(False)
        img.valueChanged.connect(self.wall.set_image_secs)
        tb.addWidget(img)
        tb.addSeparator()

        pause = QAction("Pause/Play", self)
        pause.setShortcut(QKeySequence(Qt.Key_Space))
        pause.setShortcutContext(Qt.ApplicationShortcut)
        pause.triggered.connect(self.wall.toggle_pause)
        tb.addAction(pause)
        self.addAction(pause)

        self.mute_action = QAction("Muted", self)
        self.mute_action.setCheckable(True)
        self.mute_action.setChecked(True)
        self.mute_action.setShortcut("M")
        self.mute_action.setShortcutContext(Qt.ApplicationShortcut)
        self.mute_action.toggled.connect(self.wall.set_muted)
        tb.addAction(self.mute_action)
        self.addAction(self.mute_action)

        tb.addWidget(QLabel(" Vol "))
        vol = QSlider(Qt.Horizontal)
        vol.setRange(0, 100)
        vol.setValue(70)
        vol.setFixedWidth(100)
        vol.valueChanged.connect(self.wall.set_volume)
        tb.addWidget(vol)

        shuf = QAction("Shuffle", self)
        shuf.setCheckable(True)
        shuf.setChecked(True)
        shuf.toggled.connect(lambda v: setattr(self.wall.playlist, "shuffle", v))
        tb.addAction(shuf)

        for text, key, fn in [("Next clips", "N", self.wall.next_all),
                              ("Random seek", "R", self.wall.random_all),
                              ("Fullscreen", "F", self.toggle_fullscreen)]:
            a = QAction(text, self)
            a.setShortcut(key)
            a.setShortcutContext(Qt.ApplicationShortcut)
            a.triggered.connect(fn)
            tb.addAction(a)
            self.addAction(a)

        esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc.setContext(Qt.ApplicationShortcut)
        esc.activated.connect(self.leave_fullscreen)
        self.exit_btn = ExitFullscreenButton(self)
        self.overlay = Overlay(self.wall)

        self.statusBar().showMessage(
            "Add videos/images to begin.  Drag a tile onto another to swap  |  "
            "double-click = focus  |  right-click = tile menu"
        )
        self.wall.set_cell_count(4)

    def add_files(self):
        exts = " ".join(f"*{e}" for e in sorted(MEDIA_EXT))
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add videos / images", "", f"Videos and images ({exts});;All files (*)")
        self.add_paths(files)

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Add folder")
        if d:
            self.add_paths([d])

    def add_paths(self, paths):
        n = self.wall.add_paths(paths)
        self.statusBar().showMessage(f"Library: {len(self.wall.playlist.files)} files (+{n} added)")

    def drop_paths(self, paths, cell=None):
        """Files dropped on the wall. Dropped on a tile: the first one plays there."""
        files = collect_media(paths)
        if not files:
            return
        self.wall.playlist.add(files)
        if cell:
            cell.load(files[0])
        self.wall.add_paths([])  # fill any empty tiles
        self.statusBar().showMessage(f"Library: {len(self.wall.playlist.files)} files")

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.leave_fullscreen()
        else:
            self.toolbar.hide()
            self.statusBar().hide()
            self.showFullScreen()
            QTimer.singleShot(400, self._show_exit_button)

    def _show_exit_button(self):
        if self.isFullScreen():
            self.exit_btn.place()

    def leave_fullscreen(self):
        if self.isFullScreen():
            self.exit_btn.hide()
            self.showNormal()
            self.toolbar.show()
            self.statusBar().show()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.leave_fullscreen()
        super().keyPressEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.drop_paths([u.toLocalFile() for u in e.mimeData().urls()])

    def closeEvent(self, e):
        self.overlay.timer.stop()
        self.overlay.close()
        self.exit_btn.close()
        self.wall.shutdown()
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    locale.setlocale(locale.LC_NUMERIC, "C")  # required by libmpv
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1:
        win.add_paths(sys.argv[1:])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
