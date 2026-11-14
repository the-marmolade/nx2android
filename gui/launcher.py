# The nx2android launcher: a game library over porter (the design: the "nx2android launcher" wireframes and user flow in the Clairvoyance workspace).
#   Library   the games found in the library folders (porter library: dumps grouped by title ID), as covers with their state and a rating for the chosen device
#   Catalog   every game the tool has a profile for, owned or not
#   Game page one action for the game's state (Locate files / Port / Install / Play / Update / Try experimental port), the port options, the rating and the profile's notes,
#             and for an installed port: drivers, TV mode, save export and import
#   Activity  the porter jobs, one at a time (a port, an install, an update): the bar at the bottom of every screen and its panel with each job's log
#   Devices   the adb devices; the chosen one is the config's device (porter installs and updates there), and the ratings are for its model
# The classic window (gui/app.py) stays: the gear menu opens it, and python -m gui --classic starts with it.
import hashlib, json, os, sys, time
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QScrollArea,
                               QSizePolicy, QSplitter, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from gui.runner import Porter, call_json
from porter import config

BG, PANEL, CARD, LINE, TEXT, MUTED = '#0f1216', '#161a20', '#1d222a', '#2a313b', '#e6eaf0', '#8a94a3'
ACCENT, WARN, ERR, INFO = '#3ddc97', '#f2b84b', '#ef5b5b', '#5aa9ff'
RATING_COLOR = {'Verified': ACCENT, 'Playable': INFO, 'In progress': WARN, 'Untested': MUTED, 'Experimental': WARN, 'Unsupported': ERR}
STATE_BADGE = {'installed': ('Installed', ACCENT), 'update': ('Update available', WARN), 'ported': ('Ported', INFO), 'portable': ('Portable', INFO),
               'experimental': ('Experimental', WARN), 'unsupported': ('Unsupported', ERR), 'shared': ('Needs its own folder', WARN), 'not_owned': ('Not owned', MUTED)}
STATE_ORDER = ['update', 'installed', 'ported', 'portable', 'shared', 'experimental', 'unsupported', 'not_owned']
COVER = QSize(176, 240)

QSS = f"""
* {{ color: {TEXT}; font-size: 10pt; }}
QMainWindow, QDialog, QWidget#page {{ background: {BG}; }}
QFrame#header, QFrame#footer {{ background: {PANEL}; border: none; }}
QFrame#footer {{ border-top: 1px solid {LINE}; }}
QFrame#sidebar {{ background: {PANEL}; border-right: 1px solid {LINE}; }}
QFrame#card {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 8px; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#h1 {{ font-size: 20pt; font-weight: 700; }}
QLabel#h2 {{ font-size: 12pt; font-weight: 700; }}
QLabel#section {{ color: {MUTED}; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }}
QLineEdit, QComboBox, QPlainTextEdit {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 6px; padding: 5px 8px; selection-background-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {LINE}; }}
QPushButton, QToolButton {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover, QToolButton:hover {{ border-color: {MUTED}; }}
QPushButton:disabled {{ color: {MUTED}; }}
QPushButton#primary {{ background: {ACCENT}; color: #06140d; border: none; font-weight: 700; font-size: 12pt; padding: 12px; }}
QPushButton#primary:disabled {{ background: {LINE}; color: {MUTED}; }}
QPushButton#danger {{ background: transparent; color: {ERR}; border: 1px solid {ERR}; font-weight: 700; font-size: 12pt; padding: 12px; }}
QPushButton#nav {{ background: transparent; border: none; border-bottom: 2px solid transparent; border-radius: 0; font-size: 12pt; font-weight: 700; color: {MUTED}; padding: 8px 14px; }}
QPushButton#nav:checked {{ color: {TEXT}; border-bottom-color: {ACCENT}; }}
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget#grid::item {{ border-radius: 8px; padding: 0px; }}
QListWidget#grid::item:selected, QListWidget#grid::item:hover {{ background: {LINE}; }}
QListWidget#plain {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 6px; }}
QProgressBar {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 4px; height: 8px; text-align: center; font-size: 8pt; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QScrollArea {{ border: none; background: transparent; }}
QMenu {{ background: {CARD}; border: 1px solid {LINE}; }}
QMenu::item:selected {{ background: {LINE}; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {MUTED}; border-radius: 3px; background: {CARD}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox::indicator:disabled {{ border-color: {LINE}; background: {PANEL}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
"""


def label(text='', name=None, wrap=False):
    w = QLabel(text)
    if name: w.setObjectName(name)
    if wrap: w.setWordWrap(True)
    return w


def gb(n): return f'{n / 2**30:.1f} GB' if n >= 2**30 else f'{n / 2**20:.0f} MB'


def hms(s):
    s = int(s or 0); return f'{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}' if s >= 3600 else f'{s // 60}:{s % 60:02d}'


# ---- what the launcher knows about the device and each game ----
class Device:
    def __init__(self):
        self.serial, self.model, self.name, self.state = '', '', '', ''
        self.installed, self.updates = set(), {}   # packages; package → porter updates status (current, update, risky, folder, port)

    @property
    def ready(self): return self.state == 'device'


def game_state(g, dev):
    pkg = (g.get('ported') or {}).get('package') or g['package']
    if dev.ready and pkg in dev.installed: return 'update' if dev.updates.get(pkg) in ('update', 'risky') else 'installed'
    if g.get('ported'): return 'ported'
    if not g['owned']: return 'not_owned'
    if not g['profile']: return 'unsupported'
    if not (g.get('scan') or {}).get('port_ready'): return 'shared'
    if not g['android']: return 'experimental'
    return 'portable'


def initials(name):
    words = [w for w in ''.join(c if c.isalnum() or c.isspace() else ' ' for c in name).split() if w.lower() not in ('the', 'of', 'and', 'a')]
    return ''.join(w[0] for w in words[:2]).upper() or '?'


def pill(p, x, y, text, color, right=False):
    f = QFont(); f.setPointSize(7); f.setBold(True); p.setFont(f)
    w = p.fontMetrics().horizontalAdvance(text) + 12; h = 18
    if right: x -= w
    path = QPainterPath(); path.addRoundedRect(QRectF(x, y, w, h), 9, 9)
    p.fillPath(path, QColor(0, 0, 0, 170)); p.setPen(QPen(QColor(color), 1.2)); p.drawPath(path)
    p.setPen(QColor(color)); p.drawText(QRectF(x, y, w, h), Qt.AlignCenter, text)


_ICONS = {}


def icon_of(g):   # the game's own icon (porter library --art: its control data's JPEG), loaded once
    path = g.get('icon')
    if not path: return None
    if path not in _ICONS:
        pm = QPixmap(path); _ICONS[path] = pm if not pm.isNull() else None
    return _ICONS[path]


def avg_color(pm):
    img = pm.scaled(1, 1, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).toImage(); return QColor(img.pixel(0, 0))


def cover(g, state, size=COVER, banner=False):
    """A cover: the game's own icon when porter has read it (a square on top, the name on a band in the icon's colour below; a banner: the icon dimmed and cropped
    to fill), else a generated one (a gradient in the title's colour, its initials, its name); the state and rating pills on top"""
    w, h = size.width(), size.height()
    ic = icon_of(g)
    if ic: return icon_cover(g, state, ic, w, h, banner)
    pm = QPixmap(w, h); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.TextAntialiasing)
    hue = int(hashlib.md5(g['id'].encode()).hexdigest()[:4], 16) % 360
    grad = QLinearGradient(0, 0, w * 0.6, h)
    grad.setColorAt(0, QColor.fromHsv(hue, 150, 150)); grad.setColorAt(1, QColor.fromHsv((hue + 40) % 360, 200, 45))
    path = QPainterPath(); path.addRoundedRect(QRectF(0, 0, w, h), 8, 8); p.fillPath(path, QBrush(grad))
    f = QFont(); f.setPointSize(int(h * (0.22 if banner else 0.2))); f.setBold(True); p.setFont(f)
    p.setPen(QColor(255, 255, 255, 60)); p.drawText(QRectF(0, 0, w, h * (0.8 if banner else 0.62)), Qt.AlignCenter, initials(g['name']))
    band = QRectF(0, h * (0.62 if banner else 0.66), w, h * (0.38 if banner else 0.34))
    shade = QLinearGradient(0, band.top(), 0, h); shade.setColorAt(0, QColor(0, 0, 0, 0)); shade.setColorAt(0.35, QColor(0, 0, 0, 170)); shade.setColorAt(1, QColor(0, 0, 0, 220))
    clip = QPainterPath(); clip.addRoundedRect(QRectF(0, 0, w, h), 8, 8); p.setClipPath(clip); p.fillRect(band, QBrush(shade)); p.setClipping(False)
    f = QFont(); f.setPointSize(16 if banner else 10); f.setBold(True); p.setFont(f); p.setPen(QColor('white'))
    p.drawText(band.adjusted(10, 10, -10, -8), Qt.AlignLeft | Qt.AlignBottom | Qt.TextWordWrap, g['name'])
    if state:
        t, c = STATE_BADGE[state]; pill(p, 8, 8, t, c)
    if not banner and g.get('rating') and not (state and STATE_BADGE[state][0] == g['rating']):
        pill(p, w - 8, 8 + (22 if state else 0) if w < 200 else 8, g['rating'], RATING_COLOR.get(g['rating'], MUTED), right=True)
    p.end()
    return pm


def icon_cover(g, state, ic, w, h, banner):
    pm = QPixmap(w, h); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.SmoothPixmapTransform); p.setRenderHint(QPainter.TextAntialiasing)
    clip = QPainterPath(); clip.addRoundedRect(QRectF(0, 0, w, h), 8, 8); p.setClipPath(clip)
    base = avg_color(ic); dark = QColor.fromHsv(base.hsvHue(), min(255, base.hsvSaturation()), max(30, base.value() // 3))
    if banner or w > h:   # landscape: the icon and the name on the page's own background, nothing behind them
        q = h - (40 if banner else 24); x = 0 if banner else (w - q) / 2
        icon_clip = QPainterPath(); icon_clip.addRoundedRect(QRectF(x, (h - q) / 2, q, q), 10, 10); p.setClipPath(icon_clip)
        p.drawPixmap(QRectF(x, (h - q) / 2, q, q), ic, QRectF(ic.rect())); p.setClipPath(clip)
        if banner:
            f = QFont(); f.setPointSize(22); f.setBold(True); p.setFont(f); p.setPen(QColor('white'))
            p.drawText(QRectF(x + q + 24, 0, w - q - 64, h - 24), Qt.AlignLeft | Qt.AlignBottom | Qt.TextWordWrap, g['name'])
    else:   # portrait: the icon square on top, the name below on the icon's own colour
        p.drawPixmap(QRectF(0, 0, w, w), ic, QRectF(ic.rect()))
        band = QRectF(0, w, w, h - w)
        grad = QLinearGradient(0, w, 0, h); grad.setColorAt(0, dark.lighter(130)); grad.setColorAt(1, dark); p.fillRect(band, QBrush(grad))
        f = QFont(); f.setPointSize(9); f.setBold(True); p.setFont(f); p.setPen(QColor('white'))
        p.drawText(band.adjusted(9, 6, -9, -6), Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, g['name'])
    p.setClipping(False)
    if state: t, c = STATE_BADGE[state]; pill(p, 8, 8, t, c)
    if not banner and g.get('rating') and not (state and STATE_BADGE[state][0] == g['rating']):
        pill(p, w - 8, 8 + (22 if state else 0) if w < 200 else 8, g['rating'], RATING_COLOR.get(g['rating'], MUTED), right=True)
    p.end()
    return pm


# ---- the porter jobs ----
class Job:
    def __init__(self, title, args, stream=True, done=None):
        self.title, self.args, self.stream, self.done = title, args, stream, done
        self.status, self.step, self.frac, self.log, self.result, self.t0, self.t1, self.proc = 'queued', '', None, [], None, None, None, None

    def line(self, s): self.log.append(s)


class Jobs(QObject):   # owned by the window, so Qt tears it down before the application (a parentless one crashed the interpreter's exit)
    def __init__(self, parent, on_change):
        super().__init__(parent)
        self.jobs, self.on_change, self.cur = [], on_change, None
        self.porter = Porter(self); self.porter.event.connect(self._event); self.porter.finished.connect(self._finished)

    def add(self, job):
        self.jobs.append(job); self.on_change(); self._next(); return job

    def busy(self): return self.cur is not None

    def _next(self):
        if self.cur: return
        job = next((j for j in self.jobs if j.status == 'queued'), None)
        if not job: return
        self.cur = job; job.status, job.t0 = 'running', time.time()
        job.line('$ porter ' + ' '.join(f'"{a}"' if ' ' in a else a for a in job.args))
        if job.stream: self.porter.start(job.args)
        else:
            def ok(obj, code): self._end(job, code, obj)
            def bad(msg, code): job.line('[RED] ' + msg); self._end(job, code or 1, None)
            job.proc = call_json(self, job.args, ok, failed=bad)
        self.on_change()

    def _event(self, ev):
        job = self.cur
        if not job: return
        e = ev.get('ev')
        if e == 'stage': job.step = f'{ev.get("name", "")}' + (f' · {ev["step"]}' if ev.get('step') else ''); job.frac = None; job.line(f'▶ [{ev.get("k")}/{ev.get("n")}] {ev.get("name")}')
        elif e == 'step': job.step = f'{ev.get("name", "")} · {ev.get("step", "")}'
        elif e == 'progress':
            job.step = ev.get('name', '') + (f' · {ev["step"]}' if ev.get('step') else '') + (f' · ETA {hms(ev["eta"])}' if ev.get('eta') else '')
            job.frac = ev.get('frac')
        elif e == 'stage_end': job.line(('✓ ' if ev.get('ok', True) else '✗ ') + ev.get('name', '') + (f': {ev["summary"]}' if ev.get('summary') else ''))
        elif e == 'say': job.line(ev.get('msg', ''))
        elif e == 'result': job.result = ev
        self.on_change()

    def _finished(self, code):
        if self.cur: self._end(self.cur, code, self.cur.result)

    def _end(self, job, code, obj):
        if job.status == 'cancelled': pass
        else: job.status = 'done' if code == 0 else 'failed'
        if isinstance(obj, dict) and obj.get('error'): job.status = 'failed'; job.line('[RED] ' + obj['error'])
        elif not job.stream and obj is not None: job.line(json.dumps(obj, indent=2, ensure_ascii=False)[:4000])
        job.result = obj if obj is not None else job.result; job.t1 = time.time(); job.proc = None
        self.cur = None
        if job.done:
            try: job.done(job)
            except Exception as e: job.line(f'[RED] {e}')
        self.on_change(); self._next()

    def cancel(self, job):
        if job.status == 'queued': job.status = 'cancelled'; self.on_change(); return
        if job is not self.cur: return
        job.status = 'cancelled'; job.line('[RED] cancelled')
        if job.stream: self.porter.cancel()
        elif job.proc: job.proc.kill()

    def retry(self, job):
        return self.add(Job(job.title, job.args, job.stream, job.done))

    def clear(self):
        self.jobs = [j for j in self.jobs if j.status in ('queued', 'running')]; self.on_change()


class ActivityDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win; self.setWindowTitle('Activity'); self.resize(860, 520)
        v = QVBoxLayout(self)
        top = QHBoxLayout(); top.addWidget(label('Activity', 'h2')); top.addStretch(1)
        clear = QPushButton('Clear finished'); clear.clicked.connect(lambda: win.jobs.clear()); top.addWidget(clear); v.addLayout(top)
        sp = QSplitter(); self.list = QListWidget(); self.list.setObjectName('plain'); self.list.currentRowChanged.connect(lambda _: self.show_log())
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setFont(QFont('Consolas', 9))
        sp.addWidget(self.list); sp.addWidget(self.log); sp.setSizes([300, 560]); v.addWidget(sp, 1)
        row = QHBoxLayout(); row.addStretch(1)
        self.b_cancel = QPushButton('Cancel'); self.b_cancel.clicked.connect(lambda: self.job() and win.jobs.cancel(self.job()))
        self.b_retry = QPushButton('Retry'); self.b_retry.clicked.connect(lambda: self.job() and win.jobs.retry(self.job()))
        self.b_copy = QPushButton('Copy log'); self.b_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.log.toPlainText()))
        for b in (self.b_cancel, self.b_retry, self.b_copy): row.addWidget(b)
        v.addLayout(row); self.refresh()

    def job(self):
        r = self.list.currentRow(); jobs = list(reversed(self.win.jobs.jobs))
        return jobs[r] if 0 <= r < len(jobs) else None

    def refresh(self):
        row = self.list.currentRow(); self.list.blockSignals(True); self.list.clear()
        icon = {'queued': '◷', 'running': '▶', 'done': '✓', 'failed': '✗', 'cancelled': '–'}
        for j in reversed(self.win.jobs.jobs):
            it = QListWidgetItem(f'{icon[j.status]}  {j.title}\n     {j.status}' + (f' · {j.step}' if j.status == 'running' and j.step else '')
                                 + (f' · {hms((j.t1 or time.time()) - j.t0)}' if j.t0 else ''))
            it.setForeground(QColor({'failed': ERR, 'done': ACCENT, 'running': TEXT}.get(j.status, MUTED))); self.list.addItem(it)
        self.list.blockSignals(False)
        if self.list.count(): self.list.setCurrentRow(max(0, min(row, self.list.count() - 1)))
        self.show_log()

    def show_log(self):
        j = self.job()
        self.b_cancel.setEnabled(bool(j) and j.status in ('queued', 'running')); self.b_retry.setEnabled(bool(j) and j.status in ('failed', 'cancelled'))
        text = '\n'.join(l.removeprefix('[RED] ') for l in j.log) if j else ''
        if self.log.toPlainText() != text:
            self.log.setPlainText(text); self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())


class ActivityBar(QFrame):
    def __init__(self, win):
        super().__init__(); self.setObjectName('footer'); self.win = win
        h = QHBoxLayout(self); h.setContentsMargins(14, 8, 14, 8)
        self.text = label('No jobs running', 'muted'); self.prog = QProgressBar(); self.prog.setMaximumWidth(320); self.prog.setTextVisible(False); self.prog.setVisible(False)
        self.more = label('', 'muted'); self.btn = QPushButton('Activity'); self.btn.clicked.connect(win.open_activity)
        h.addWidget(self.text, 1); h.addWidget(self.prog, 1); h.addWidget(self.more); h.addWidget(self.btn)

    def refresh(self):
        jobs = self.win.jobs; cur = jobs.cur
        queued = sum(j.status == 'queued' for j in jobs.jobs); failed = sum(j.status == 'failed' for j in jobs.jobs)
        if cur:
            self.text.setObjectName(''); self.text.setText(f'<b>{cur.title}</b>' + (f' · {cur.step}' if cur.step else '') + f' · {hms(time.time() - cur.t0)}')
            self.prog.setVisible(True)
            if cur.frac is None: self.prog.setRange(0, 0)
            else: self.prog.setRange(0, 1000); self.prog.setValue(int(cur.frac * 1000))
        else:
            last = jobs.jobs[-1] if jobs.jobs else None
            self.text.setText(f'{last.title}: {last.status}' if last and last.status in ('done', 'failed') else 'No jobs running'); self.prog.setVisible(False)
        self.text.style().unpolish(self.text); self.text.style().polish(self.text)
        self.more.setText(' · '.join(x for x in (f'{queued} queued' if queued else '', f'{failed} failed' if failed else '') if x))
        self.btn.setText(f'Activity ({queued + failed + (1 if cur else 0)})' if queued + failed + (1 if cur else 0) else 'Activity')


# ---- the game page ----
class GamePage(QWidget):
    def __init__(self, win):
        super().__init__(); self.setObjectName('page'); self.win, self.g = win, None
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); outer.addWidget(scroll); self.scroll = scroll
        body = QWidget(); body.setObjectName('page'); scroll.setWidget(body)
        v = QVBoxLayout(body); v.setContentsMargins(24, 16, 24, 24); v.setSpacing(14)
        top = QHBoxLayout(); back = QPushButton('‹ Back'); back.clicked.connect(win.show_browse); top.addWidget(back); top.addStretch(1); v.addLayout(top)
        self.banner = QLabel(); self.banner.setMinimumHeight(200); self.banner.setMinimumWidth(1); self.banner.setAlignment(Qt.AlignLeft)
        self.banner.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed); v.addWidget(self.banner)
        cols = QHBoxLayout(); cols.setSpacing(20); v.addLayout(cols, 1)
        left = QVBoxLayout(); left.setSpacing(10); cols.addLayout(left, 1)
        self.title = label('', 'h1', wrap=True); self.sub = label('', 'muted', wrap=True); left.addWidget(self.title); left.addWidget(self.sub)
        self.warn = label('', wrap=True); self.warn.setStyleSheet(f'background:{CARD}; border:1px solid {WARN}; border-radius:6px; padding:10px;'); left.addWidget(self.warn)
        left.addWidget(label('ABOUT THIS PORT', 'section'))
        self.about = label('', wrap=True); self.about.setTextFormat(Qt.PlainText); self.about.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.about.setTextInteractionFlags(Qt.TextSelectableByMouse); left.addWidget(self.about)
        self.more_btn = QPushButton('Show all notes'); self.more_btn.clicked.connect(self.toggle_notes); left.addWidget(self.more_btn, 0, Qt.AlignLeft)
        left.addWidget(label('IN YOUR FOLDER', 'section'))
        self.files = QFormLayout(); left.addLayout(self.files)
        self.manage = QFrame(); self.manage.setObjectName('card'); mv = QVBoxLayout(self.manage)
        mv.addWidget(label('ON THE DEVICE', 'section'))
        mrow = QHBoxLayout(); mv.addLayout(mrow)
        for text, fn in (('Drivers…', self.drivers), ('TV mode on', lambda: self.tv(True)), ('TV mode off', lambda: self.tv(False)),
                         ('Export save…', self.export_save), ('Import save…', self.import_save)):
            b = QPushButton(text); b.clicked.connect(fn); mrow.addWidget(b)
        mrow.addStretch(1); left.addWidget(self.manage); left.addStretch(1)
        right = QVBoxLayout(); right.setSpacing(10); cols.addLayout(right)
        self.primary = QPushButton(); self.primary.setObjectName('primary'); self.primary.setMinimumWidth(300); self.primary.clicked.connect(self.act); right.addWidget(self.primary)
        self.hint = label('', 'muted', wrap=True); self.hint.setMaximumWidth(300); right.addWidget(self.hint)
        self.more = QToolButton(); self.more.setText('More ▾'); self.more.setPopupMode(QToolButton.InstantPopup); right.addWidget(self.more)
        self.opts = QFrame(); self.opts.setObjectName('card'); ov = QVBoxLayout(self.opts); ov.addWidget(label('PORT OPTIONS', 'section'))
        self.o_install = QCheckBox('Install on the device when done'); self.o_thor = QCheckBox('AYN Thor preset (prime core, pad hidden)')
        self.o_fps60 = QCheckBox('60 fps (lift the profile\'s cap)'); self.o_tv = QCheckBox('TV mode (external display)'); self.o_touch = QCheckBox('Touch game (pad hidden)')
        for c in (self.o_install, self.o_thor, self.o_fps60, self.o_tv, self.o_touch): ov.addWidget(c)
        right.addWidget(self.opts)
        self.rate = QFrame(); self.rate.setObjectName('card'); rv = QVBoxLayout(self.rate)
        self.rate_head = label('', 'section'); self.rate_val = label('', 'h2'); self.rate_why = label('', 'muted', wrap=True); self.rate_why.setMaximumWidth(290)
        for w in (self.rate_head, self.rate_val, self.rate_why): rv.addWidget(w)
        right.addWidget(self.rate)
        self.det = QFrame(); self.det.setObjectName('card'); self.detf = QFormLayout(self.det); right.addWidget(self.det)
        right.addStretch(1)
        self.full_notes = False

    # ---- show a game ----
    def show_game(self, g):
        self.g = g; self.full_notes = False
        dev = self.win.dev; st = game_state(g, dev); self.state = st
        self.draw_banner(); QTimer.singleShot(0, self.draw_banner); QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(0))
        self.title.setText(g['name']); self.title.setVisible(icon_of(g) is None)   # the icon banner carries the name
        self.sub.setText(f'{g["id"]} · ' + {'playable': 'Playable on Android', 'wip': 'Work in progress', 'boots': 'Boots', 'ios only': 'iOS profile only',
                                           'unsupported': 'No profile'}.get(g['status'], g['status']))
        warn = ''
        if st == 'unsupported': warn = 'nx2android has no profile for this game yet. An experimental port guesses one from the game\'s files: it may not start, or may crash later.'
        elif st == 'experimental': warn = 'This game has an iOS profile but is not tuned for Android yet: an experimental port tries it with that profile.'
        elif st == 'shared': warn = 'This game shares its folder with another game. Porter ports one game per folder: move its files into a folder of their own, then Rescan.'
        elif dev.updates.get(self.pkg()) == 'risky': warn = 'The code rewriter changed since this port was made: an update keeps the old rewrite (it usually works); a port again is the safe way.'
        self.warn.setText(warn); self.warn.setVisible(bool(warn))
        self.set_notes()
        while self.files.rowCount(): self.files.removeRow(0)
        s = g.get('scan')
        if s:
            self.files.addRow(label('Folder', 'muted'), label(s['folders'][0] if s['folders'] else '-', wrap=True))
            self.files.addRow(label('Updates', 'muted'), label(', '.join(f'v{u}' for u in s['updates']) or 'none (base game only)'))
            self.files.addRow(label('DLC', 'muted'), label(str(s['dlc'] or 'none')))
            self.files.addRow(label('Size', 'muted'), label(f'{gb(s["bytes"])} in {s["files"]} files'))
        else: self.files.addRow(label('Not found in your library folders.', 'muted'))
        if g.get('ported'): self.files.addRow(label('Port', 'muted'), label(f'{g["ported"]["display"] or g["ported"]["version"]} · made {g["ported"]["made"]}', wrap=True))
        self.manage.setVisible(st in ('installed', 'update'))
        r = g['rating']; self.rate_head.setText(f'ON YOUR {dev.name.upper()}' if dev.name else 'ON YOUR DEVICE')
        self.rate_val.setText(r); self.rate_val.setStyleSheet(f'color:{RATING_COLOR.get(r, MUTED)}'); self.rate_why.setText(g['why'])
        self.rate.setStyleSheet(f'QFrame#card {{ border-color: {RATING_COLOR.get(r, LINE)}; }}')
        while self.detf.rowCount(): self.detf.removeRow(0)
        for k, v in (('Status', STATE_BADGE[st][0]), ('Profile', g['status']), ('Package', self.pkg()), ('Tested', g['tested'] or '-')):
            self.detf.addRow(label(k, 'muted'), label(v, wrap=True))
        thor = dev.model == 'AYN_Thor'
        self.o_install.setChecked(dev.ready); self.o_install.setEnabled(dev.ready); self.o_thor.setChecked(thor)
        for c in (self.o_fps60, self.o_tv, self.o_touch): c.setChecked(False)
        self.set_action()

    def pkg(self): return (self.g.get('ported') or {}).get('package') or self.g['package']

    def draw_banner(self):
        if self.g: self.banner.setPixmap(cover(self.g, None, QSize(max(400, self.scroll.viewport().width() - 48), 200), banner=True))

    def resizeEvent(self, e):
        super().resizeEvent(e); self.draw_banner()

    def set_notes(self):
        n = self.g['notes'] or ('No notes: this game has no Android profile.' if self.g['profile'] else 'No profile, so no notes.')
        short = len(n) > 700 and not self.full_notes
        self.about.setText(n[:700].rsplit(' ', 1)[0] + '…' if short else n)
        self.more_btn.setVisible(len(n) > 700); self.more_btn.setText('Show less' if self.full_notes else 'Show all notes')

    def toggle_notes(self): self.full_notes = not self.full_notes; self.set_notes()

    def set_action(self):
        st, dev, g = self.state, self.win.dev, self.g
        busy = self.win.jobs.busy()
        name = dev.name or 'the device'
        text, hint, enabled, danger = {
            'not_owned': ('Locate game files…', 'Choose the folder with your dump of this game; it is added to your library.', True, False),
            'unsupported': ('Try experimental port', 'Experimental ports are unsupported and may not start.', True, True),
            'experimental': ('Try experimental port', 'Uses the iOS profile; may not start on Android.', True, True),
            'shared': ('Port', 'Put this game in a folder of its own first.', False, False),
            'portable': ('Port', f'Then install and play on {name}.' if dev.ready else 'No device: the port is made here; install it later.', True, False),
            'ported': (f'Install on {name}', 'The port is in your output folder.' if dev.ready else 'Connect a device to install.', dev.ready, False),
            'installed': (f'Play on {name}', 'Starts the game on the device.', True, False),
            'update': ('Update (saves stay)', 'Brings the engine on the device to this version without the game files.', True, False),
        }[st]
        self.primary.setText(text); self.primary.setEnabled(enabled); self.primary.setObjectName('danger' if danger else 'primary')
        self.primary.style().unpolish(self.primary); self.primary.style().polish(self.primary)
        self.hint.setText(hint + ('  (Another job is running: this one queues after it.)' if busy and st not in ('installed', 'not_owned') else ''))
        self.opts.setVisible(st in ('portable', 'unsupported', 'experimental'))
        m = QMenu(self)
        s = g.get('scan')
        if s and s['folders']: m.addAction('Open game folder', lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(s['folders'][0])))
        if g.get('ported'): m.addAction('Open port folder', lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(g['ported']['data']).parent))))
        if st in ('ported', 'installed', 'update') and s and s.get('port_ready'): m.addAction('Port again', self.port)
        if st in ('installed', 'update') and dev.ready: m.addAction('Reinstall from the port', self.install) if g.get('ported') else None
        m.addAction('Copy title ID', lambda: QApplication.clipboard().setText(g['id']))
        self.more.setMenu(m)

    # ---- the actions ----
    def act(self):
        st = self.state
        if st == 'not_owned': self.win.add_folder()
        elif st in ('portable', 'unsupported', 'experimental'): self.port()
        elif st == 'ported': self.install()
        elif st == 'installed': self.launch()
        elif st == 'update': self.update()

    def port(self):
        g, dev = self.g, self.win.dev
        if not config.load().get('keys'):
            QMessageBox.warning(self, 'prod.keys', 'Set the path of your prod.keys first (⚙ › Setup & tools).'); return
        if self.state in ('unsupported', 'experimental') and QMessageBox.question(
                self, 'Experimental port', f'{g["name"]} has no Android profile. An experimental port may not start or may crash later. Try it?') != QMessageBox.Yes: return
        args = ['port', g['scan']['folders'][0], '--progress', 'json']
        if self.o_install.isChecked() and dev.ready: args += ['--install', '--device', dev.serial]
        if self.o_thor.isChecked(): args += ['--preset', 'thor']
        if self.o_fps60.isChecked(): args.append('--fps60')
        if self.o_tv.isChecked(): args.append('--external-display')
        if self.o_touch.isChecked(): args.append('--touch')
        if not g['android']: args.append('--experimental')
        self.win.run(Job(f'Port · {g["name"]}', args, done=lambda j: self.win.reload()))

    def install(self):
        g, dev = self.g, self.win.dev; p = g['ported']
        self.win.run(Job(f'Install · {g["name"]} on {dev.name}', ['install', p['data'], '--apk', p['apk'], '--device', dev.serial, '--progress', 'json'],
                         done=lambda j: self.win.refresh_device()))

    def update(self):
        g, dev = self.g, self.win.dev; args = ['host', '--package', self.pkg(), '--device', dev.serial, '--json']
        if dev.updates.get(self.pkg()) == 'risky':
            if QMessageBox.question(self, 'Update anyway?', 'The code rewriter changed since this port was made. Updating keeps the game\'s old rewrite; it usually works, and '
                                    'the saves stay either way. Update anyway?') != QMessageBox.Yes: return
            args.append('--force')
        self.win.run(Job(f'Update · {g["name"]} on {dev.name}', args, stream=False, done=lambda j: self.win.refresh_device()))

    def launch(self):
        g, dev = self.g, self.win.dev
        self.win.run(Job(f'Play · {g["name"]}', ['launch', '--package', self.pkg(), '--device', dev.serial, '--json'], stream=False))

    def tv(self, on):
        g, dev = self.g, self.win.dev
        self.win.run(Job(f'TV mode {"on" if on else "off"} · {g["name"]}', ['tv', 'on' if on else 'off', '--package', self.pkg(), '--device', dev.serial, '--json'], stream=False))

    def drivers(self):
        from gui.app import DriversDialog
        DriversDialog(self, {'name': self.g['name'], 'package': self.pkg()}).exec()

    def export_save(self):
        d = QFileDialog.getExistingDirectory(self, 'Export the save to')
        if d: self.win.run(Job(f'Export save · {self.g["name"]}', ['saves', 'export', d, '--package', self.pkg(), '--device', self.win.dev.serial, '--json'], stream=False))

    def import_save(self):
        f, _ = QFileDialog.getOpenFileName(self, 'Import a save (.zip), or cancel to pick a folder', '', 'Save (*.zip)')
        if not f: f = QFileDialog.getExistingDirectory(self, 'Import a save folder')
        if not f: return
        if QMessageBox.question(self, 'Import save', f'Replace {self.g["name"]}\'s save on the device with {Path(f).name}? The current one is exported on the device first.') != QMessageBox.Yes: return
        self.win.run(Job(f'Import save · {self.g["name"]}', ['saves', 'import', f, '--package', self.pkg(), '--device', self.win.dev.serial, '--json'], stream=False))


# ---- setup ----
class SetupDialog(QDialog):
    """First run (and ⚙ › Setup & tools): the classic Setup tab (requirements, tool downloads, prod.keys and paths), then the game folders"""
    def __init__(self, win, first=False):
        super().__init__(win); self.win = win
        self.setWindowTitle('Welcome to nx2android' if first else 'Setup & tools'); self.resize(820, 640)
        v = QVBoxLayout(self)
        if first:
            v.addWidget(label('Welcome to nx2android', 'h1'))
            v.addWidget(label('Three things before your first port: your prod.keys (from your own Switch), the tools a port needs, and the folder with your games.', 'muted', wrap=True))
        from gui.app import SetupTab
        self.ready = False
        self.setup = SetupTab(self); v.addWidget(self.setup, 1)
        row = QHBoxLayout(); add = QPushButton('Add game folder…'); add.clicked.connect(win.add_folder); row.addWidget(add)
        row.addWidget(label(f'Library: {"; ".join(win.folders) or "no folders yet"}', 'muted', wrap=True), 1)
        done = QPushButton('Done'); done.setObjectName('primary'); done.clicked.connect(self.accept); row.addWidget(done); v.addLayout(row)

    def set_ready(self, ok): self.ready = ok   # SetupTab's check (gui/app.py) reports here


# ---- the window ----
class Launcher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('nx2android'); self.resize(1280, 860)
        self.games, self.folders, self.mode, self.dev, self.devices = [], [], 'library', Device(), []
        self.activity = None; self.classic = None; self.art_tried = False
        self.jobs = Jobs(self, self.jobs_changed)
        root = QWidget(); self.setCentralWidget(root); v = QVBoxLayout(root); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)
        # header: name, nav, search, device, gear
        head = QFrame(); head.setObjectName('header'); h = QHBoxLayout(head); h.setContentsMargins(16, 6, 16, 0)
        logo = label('nx2android', 'h2'); logo.setStyleSheet(f'color:{ACCENT}; padding-right: 18px;'); h.addWidget(logo)
        self.nav = QButtonGroup(self)
        for i, name in enumerate(('Library', 'Catalog')):
            b = QPushButton(name); b.setObjectName('nav'); b.setCheckable(True); b.setChecked(i == 0); self.nav.addButton(b, i); h.addWidget(b)
        self.nav.idClicked.connect(lambda i: self.set_mode('library' if i == 0 else 'catalog'))
        h.addStretch(1)
        self.search = QLineEdit(); self.search.setPlaceholderText('Search games'); self.search.setFixedWidth(280); self.search.textChanged.connect(lambda _: self.fill()); h.addWidget(self.search)
        self.dev_btn = QToolButton(); self.dev_btn.setPopupMode(QToolButton.InstantPopup); self.dev_btn.setText('No device'); h.addWidget(self.dev_btn)
        gear = QToolButton(); gear.setText('⚙'); gear.setPopupMode(QToolButton.InstantPopup); gm = QMenu(self)
        gm.addAction('Setup & tools…', lambda: SetupDialog(self).exec()); gm.addAction('Rescan library', self.reload)
        gm.addAction('Classic view…', self.open_classic); gear.setMenu(gm); h.addWidget(gear)
        v.addWidget(head)
        self.stack = QStackedWidget(); v.addWidget(self.stack, 1)
        # browse: sidebar + grid
        browse = QWidget(); browse.setObjectName('page'); bh = QHBoxLayout(browse); bh.setContentsMargins(0, 0, 0, 0); bh.setSpacing(0)
        side = QFrame(); side.setObjectName('sidebar'); side.setFixedWidth(240); sv = QVBoxLayout(side); sv.setContentsMargins(14, 14, 14, 14); sv.setSpacing(6)
        self.lib_box = QWidget(); lv = QVBoxLayout(self.lib_box); lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(label('FOLDERS', 'section')); self.folder_list = QListWidget(); self.folder_list.setObjectName('plain'); self.folder_list.setMaximumHeight(110); lv.addWidget(self.folder_list)
        fr = QHBoxLayout(); add = QPushButton('+ Add'); add.clicked.connect(self.add_folder); rem = QPushButton('Remove'); rem.clicked.connect(self.remove_folder)
        resc = QPushButton('Rescan'); resc.clicked.connect(self.reload); fr.addWidget(add); fr.addWidget(rem); fr.addWidget(resc); lv.addLayout(fr)
        sv.addWidget(self.lib_box)
        sv.addWidget(label('SHOW', 'section'))
        self.show_checks = {}
        for st in STATE_ORDER:
            c = QCheckBox(STATE_BADGE[st][0]); c.setChecked(True); c.toggled.connect(lambda _: self.fill()); self.show_checks[st] = c; sv.addWidget(c)
        sv.addWidget(label('ON THIS DEVICE', 'section'))
        self.verified_only = QCheckBox('Verified or Playable only'); self.verified_only.toggled.connect(lambda _: self.fill()); sv.addWidget(self.verified_only)
        sv.addWidget(label('SORT', 'section'))
        self.sort = QComboBox(); self.sort.addItems(['Status', 'Name', 'Rating']); self.sort.currentIndexChanged.connect(lambda _: self.fill()); sv.addWidget(self.sort)
        sv.addStretch(1); self.count = label('', 'muted', wrap=True); sv.addWidget(self.count)
        bh.addWidget(side)
        self.content = QStackedWidget(); bh.addWidget(self.content, 1)
        gw = QWidget(); gv = QVBoxLayout(gw); gv.setContentsMargins(18, 14, 8, 8)
        self.grid_title = label('', 'h2'); gv.addWidget(self.grid_title)
        self.grid = QListWidget(); self.grid.setObjectName('grid'); self.grid.setViewMode(QListWidget.IconMode); self.grid.setMovement(QListWidget.Static)
        self.grid.setResizeMode(QListWidget.Adjust); self.grid.setUniformItemSizes(True); self.grid.setIconSize(COVER); self.grid.setSpacing(10)
        self.grid.setGridSize(QSize(COVER.width() + 16, COVER.height() + 16)); self.grid.itemClicked.connect(self.open_item); gv.addWidget(self.grid, 1)
        self.content.addWidget(gw)
        empty = QWidget(); ev = QVBoxLayout(empty); ev.addStretch(1)
        self.empty_title = label('', 'h1'); self.empty_title.setAlignment(Qt.AlignCenter); self.empty_text = label('', 'muted', wrap=True); self.empty_text.setAlignment(Qt.AlignCenter)
        er = QHBoxLayout(); er.addStretch(1); e1 = QPushButton('Add game folder…'); e1.setObjectName('primary'); e1.clicked.connect(self.add_folder)
        e2 = QPushButton('Browse the Catalog'); e2.clicked.connect(lambda: (self.nav.button(1).setChecked(True), self.set_mode('catalog'))); er.addWidget(e1); er.addWidget(e2); er.addStretch(1)
        ev.addWidget(self.empty_title); ev.addWidget(self.empty_text); ev.addLayout(er); ev.addStretch(2)
        self.content.addWidget(empty)
        self.stack.addWidget(browse)
        self.page = GamePage(self); self.stack.addWidget(self.page)
        self.bar = ActivityBar(self); v.addWidget(self.bar)
        self.tick = QTimer(self); self.tick.timeout.connect(lambda: self.jobs.cur and self.bar.refresh()); self.tick.start(1000)
        self.setStyleSheet(QSS)
        QTimer.singleShot(0, self.start)

    # ---- start-up ----
    def start(self):
        self.refresh_devices(then=self.reload)
        def got(rows, code):
            if isinstance(rows, list) and any(r.get('required') and not r.get('ok') for r in rows) or not config.load().get('library'):
                SetupDialog(self, first=True).exec(); self.reload()
        call_json(self, ['doctor', '--json'], got, failed=lambda m, c: None)

    def refresh_devices(self, then=None):
        def got(rows, code):
            self.devices = rows if isinstance(rows, list) else []
            want = config.load().get('device')
            ready = [r for r in self.devices if r.get('state') == 'device']
            pick = next((r for r in self.devices if r['serial'] == want), None) or (ready[0] if ready else None)
            self.set_device(pick, save=False)
            if then: then()
        call_json(self, ['devices', '--json'], got, failed=lambda m, c: (self.set_device(None, save=False), then and then()))

    def set_device(self, row, save=True):
        d = Device()
        if row:
            d.serial, d.state = row['serial'], row.get('state', '')
            info = dict(kv.split(':', 1) for kv in (row.get('info') or '').split() if ':' in kv)
            d.model = info.get('model', ''); from porter.library import device_name; d.name = device_name(d.model) or d.serial
        changed = d.model != self.dev.model
        self.dev = d
        if save: config.set_value('device', d.serial)
        self.dev_btn.setText(f'● {d.name} · {"ready" if d.ready else d.state}' if row else '○ No device')
        self.dev_btn.setStyleSheet(f'color: {ACCENT if d.ready else WARN if row else MUTED};')
        m = QMenu(self)
        for r in self.devices:
            info = dict(kv.split(':', 1) for kv in (r.get('info') or '').split() if ':' in kv)
            from porter.library import device_name
            a = m.addAction(f'{device_name(info.get("model", "")) or r["serial"]}  ·  {r["state"]}  ({r["serial"]})', lambda r=r: self.choose_device(r))
            a.setCheckable(True); a.setChecked(r['serial'] == d.serial)
        if not self.devices: m.addAction('No devices: connect one with USB debugging on').setEnabled(False)
        m.addSeparator(); m.addAction('No device (port only)', lambda: self.choose_device(None)); m.addAction('Refresh', lambda: self.refresh_devices(then=self.reload))
        self.dev_btn.setMenu(m)
        if d.ready: self.refresh_device()
        return changed

    def choose_device(self, row):
        self.set_device(row); self.reload()

    def refresh_device(self):
        if not self.dev.ready: return
        serial = self.dev.serial
        def apps(rows, code):
            if serial != self.dev.serial: return
            self.dev.installed = set(rows) if isinstance(rows, list) else set(); self.fill(); self.page_refresh()
            call_json(self, ['updates', '--json', '--device', serial], ups, failed=lambda m, c: None)
        def ups(res, code):
            if serial != self.dev.serial or not isinstance(res, dict): return
            self.dev.updates = {g['package']: g.get('status') for g in res.get('games', [])}; self.fill(); self.page_refresh()
        call_json(self, ['saves', 'apps', '--json', '--device', serial], apps, failed=lambda m, c: None)

    def reload(self):
        self.count.setText('Scanning…')
        def got(res, code):
            if not isinstance(res, dict) or 'games' not in res:
                self.count.setText('Could not read the library: ' + (res or {}).get('error', 'porter failed') if isinstance(res, dict) else 'Could not read the library'); return
            self.games, self.folders = res['games'], res['folders']
            self.folder_list.clear(); self.folder_list.addItems(self.folders)
            self.fill(); self.page_refresh()
            if res.get('art_missing') and not self.art_tried and config.load().get('keys'): self.fetch_art()
        call_json(self, ['library', '--json', '--model', self.dev.model], got, failed=lambda m, c: self.count.setText('Could not read the library:\n' + m))

    def fetch_art(self):   # the games' icons and names from their control data, in the background; once a session (a failure is not retried in a loop)
        self.art_tried = True; self.count.setText('Reading game icons…')
        def got(res, code):
            if isinstance(res, dict) and 'games' in res: self.games = res['games']; self.fill(); self.page_refresh()
            elif isinstance(res, dict) and res.get('error'): self.count.setText(res['error'])
        call_json(self, ['library', '--art', '--json', '--model', self.dev.model], got, failed=lambda m, c: self.count.setText('Game icons: ' + m.splitlines()[0]))

    def page_refresh(self):
        if self.stack.currentWidget() is self.page and self.page.g:
            g = next((x for x in self.games if x['id'] == self.page.g['id']), self.page.g); self.page.show_game(g)

    # ---- library folders ----
    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, 'A folder with your Switch games (NSP, XCI, NSZ, XCZ; subfolders are scanned too)')
        if not d: return
        self.count.setText('Scanning…')
        call_json(self, ['library', '--add', d, '--json', '--model', self.dev.model], lambda res, code: self.reload(), failed=lambda m, c: QMessageBox.warning(self, 'Library', m))

    def remove_folder(self):
        it = self.folder_list.currentItem()
        if not it: return
        call_json(self, ['library', '--remove', it.text(), '--json'], lambda res, code: self.reload(), failed=lambda m, c: QMessageBox.warning(self, 'Library', m))

    # ---- the grid ----
    def set_mode(self, mode):
        self.mode = mode; self.lib_box.setVisible(mode == 'library'); self.show_browse(); self.fill(); self.grid.scrollToTop()

    def visible_games(self):
        q = self.search.text().strip().lower()
        out = []
        for g in self.games:
            st = game_state(g, self.dev)
            if self.mode == 'library' and not (g['owned'] or st in ('installed', 'update', 'ported')): continue
            if self.mode == 'catalog' and not g['profile']: continue
            if not self.show_checks[st].isChecked(): continue
            if self.verified_only.isChecked() and g['rating'] not in ('Verified', 'Playable'): continue
            if q and q not in g['name'].lower() and q not in g['id'].lower(): continue
            out.append((g, st))
        key = self.sort.currentText()
        rank = ['Verified', 'Playable', 'In progress', 'Untested', 'Experimental', 'Unsupported']
        if key == 'Status': out.sort(key=lambda x: (STATE_ORDER.index(x[1]), x[0]['name'].lower()))
        elif key == 'Rating': out.sort(key=lambda x: (rank.index(x[0]['rating']) if x[0]['rating'] in rank else 9, x[0]['name'].lower()))
        else: out.sort(key=lambda x: x[0]['name'].lower())
        return out

    def fill(self):
        games = self.visible_games()
        self.grid.setUpdatesEnabled(False); self.grid.clear()
        for g, st in games:
            it = QListWidgetItem(QIcon(cover(g, st)), ''); it.setData(Qt.UserRole, g['id']); it.setToolTip(f'{g["name"]}\n{STATE_BADGE[st][0]} · {g["rating"]}: {g["why"]}')
            it.setSizeHint(QSize(COVER.width() + 8, COVER.height() + 8)); self.grid.addItem(it)
        self.grid.setUpdatesEnabled(True)
        owned = sum(g['owned'] for g in self.games)
        if self.mode == 'library':
            self.grid_title.setText(f'Your games · {len(games)}')
            if not self.folders:
                self.empty_title.setText('Add the folder with your Switch games')
                self.empty_text.setText('nx2android looks for NSP, XCI, NSZ and XCZ dumps in it and the folders below, groups each game with its updates and DLC, and shows which ones can be ported.')
            else:
                self.empty_title.setText('No games here' if not owned else 'Nothing matches')
                self.empty_text.setText(f'No Switch games found in {"; ".join(self.folders)}.' if not owned else 'Change the search or the filters on the left.')
            self.content.setCurrentIndex(0 if games else 1)
        else:
            self.grid_title.setText(f'Catalog · {len(games)} of {sum(g["profile"] for g in self.games)} games nx2android has a profile for')
            self.empty_title.setText('Nothing matches'); self.empty_text.setText('Change the search or the filters on the left.')
            self.content.setCurrentIndex(0 if games else 1)
        self.count.setText(f'{owned} owned · {sum(g["profile"] for g in self.games)} in the catalog' + (f'\nRatings for {self.dev.name}' if self.dev.name else '\nNo device: ratings are general'))

    def open_item(self, it):
        g = next((x for x in self.games if x['id'] == it.data(Qt.UserRole)), None)
        if g: self.page.show_game(g); self.stack.setCurrentWidget(self.page)

    def show_browse(self): self.stack.setCurrentIndex(0)

    # ---- jobs ----
    def run(self, job):
        self.jobs.add(job)
        if self.page.g: self.page.set_action()

    def jobs_changed(self):
        self.bar.refresh()
        if self.activity and self.activity.isVisible(): self.activity.refresh()

    def open_activity(self):
        if not self.activity: self.activity = ActivityDialog(self)
        self.activity.refresh(); self.activity.show(); self.activity.raise_()

    def open_classic(self):
        from gui.app import Window
        if not self.classic: self.classic = Window()
        self.classic.show(); self.classic.raise_()

    def closeEvent(self, e):
        if self.jobs.busy() and QMessageBox.question(self, 'Quit', 'A job is still running. Quit and stop it?') != QMessageBox.Yes: e.ignore(); return
        if self.jobs.cur: self.jobs.cancel(self.jobs.cur)
        e.accept()


def main(argv):
    import faulthandler
    from porter.paths import user_dir
    try:   # a native crash (Qt) leaves its Python stack here: <user dir>/logs/launcher-crash.log
        (user_dir() / 'logs').mkdir(parents=True, exist_ok=True); crash = open(user_dir() / 'logs' / 'launcher-crash.log', 'w', encoding='utf-8'); faulthandler.enable(crash)
    except OSError: pass
    app = QApplication(argv); app.setApplicationName('nx2android'); app.setStyle('Fusion')
    app.setWindowIcon(QIcon(str(Path(__file__).parent / 'icon.png')))
    w = Launcher(); w.show()
    code = app.exec()
    w.deleteLater(); del w   # the window and its jobs go before the application
    return code
