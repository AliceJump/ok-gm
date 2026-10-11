"""Qt bridge for progress from the framework's background start controller."""
from PySide6.QtCore import QObject, Signal


class LauncherEvents(QObject):
    progress = Signal(str)
    download = Signal(int, int)
    profiles_changed = Signal()


_events = None


def events():
    global _events
    if _events is None:
        _events = LauncherEvents()
    return _events


def publish_progress(message):
    if _events is not None:
        _events.progress.emit(message)


def publish_download(done, total):
    if _events is not None:
        _events.download.emit(int(done * 100 / total) if total else 100, int(total / 1024 / 1024))
