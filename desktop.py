"""Windows sign-in shortcut and system tray integration."""
import ctypes
from pathlib import Path
import queue
import subprocess
import sys

from PIL import Image
import pystray

ROOT = Path(__file__).resolve().parent


def startup_path():
    buffer = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 7, None, 0, buffer):
        raise OSError('Could not locate the Windows Startup folder.')
    return Path(buffer.value) / 'G Capture.lnk'


def startup_enabled():
    return startup_path().is_file()


def set_startup(enabled):
    path = startup_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    if not pythonw.is_file():
        raise FileNotFoundError('Cannot find pythonw.exe next to Python.')
    def quoted(value):
        return "'" + str(value).replace("'", "''") + "'"
    script = (
        "$ErrorActionPreference = 'Stop'; "
        f"$link = (New-Object -ComObject WScript.Shell).CreateShortcut({quoted(path)}); "
        f"$link.TargetPath = {quoted(pythonw)}; "
        f"$link.Arguments = {quoted(chr(34) + str(ROOT / 'app.py') + chr(34) + ' --tray')}; "
        f"$link.WorkingDirectory = {quoted(ROOT)}; "
        f"$link.IconLocation = {quoted(ROOT / 'assets' / 'capture-studio.ico')}; "
        "$link.Save()"
    )
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                   check=True, capture_output=True, text=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)


class Tray:
    def __init__(self):
        self.commands = queue.Queue()
        def send(command):
            return lambda icon, item: self.commands.put(command)
        def startup_checked(item):
            try:
                return startup_enabled()
            except OSError:
                # Keep the tray usable even if this folder is inaccessible.
                return None
        with Image.open(ROOT / 'assets' / 'capture-studio.ico') as source:
            image = source.copy()
        self.icon = pystray.Icon('GCapture', image, 'G Capture', pystray.Menu(
            pystray.MenuItem('Open G Capture', send('open'), default=True),
            pystray.MenuItem('Capture region', send('capture')),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Run at startup', send('startup'),
                             checked=startup_checked),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', send('quit')),
        ))
        self.icon.run_detached()

    def stop(self):
        self.icon.stop()
