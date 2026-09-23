"""Windows desktop integration. No capture data leaves this machine."""
import ctypes
from ctypes import wintypes
import io
import queue
import threading
from PIL import ImageGrab
from settings import DEFAULT_SHORTCUTS, parse_shortcut, validate

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE


def set_app_id():
    # Give the taskbar our app identity instead of the Python interpreter's.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('GCapture.Desktop')


def dpi_aware():
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


def desktop_bounds():
    return tuple(user32.GetSystemMetrics(n) for n in (76, 77, 78, 79))


def position_overlay(widget, x, y, width, height):
    # Tk geometry treats negative coordinates as offsets from the right/bottom.
    # Set physical desktop coordinates directly for left/top secondary monitors.
    widget.update_idletasks()
    hwnd = user32.GetAncestor(widget.winfo_id(), 2)
    user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), x, y, width, height, 0x0040)


def grab(box=None):
    return ImageGrab.grab(bbox=box, all_screens=True).convert('RGB')


def target_rect(root_window=True):
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    hwnd = user32.WindowFromPoint(point)
    if root_window:
        hwnd = user32.GetAncestor(hwnd, 2)
    rect = wintypes.RECT()
    if not hwnd or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError('No capturable window under the pointer.')
    x, y, w, h = desktop_bounds()
    box = (max(x, rect.left), max(y, rect.top), min(x+w, rect.right), min(y+h, rect.bottom))
    if box[2] <= box[0] or box[3] <= box[1]:
        raise RuntimeError('The selected window is outside the desktop.')
    return box


def copy_image(image):
    stream = io.BytesIO()
    image.convert('RGB').save(stream, 'BMP')
    data = stream.getvalue()[14:]
    if not user32.OpenClipboard(None):
        raise RuntimeError('Clipboard is busy. Try again.')
    handle = None
    try:
        handle = kernel32.GlobalAlloc(0x42, len(data))
        if not handle:
            raise MemoryError('Cannot allocate clipboard memory.')
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise MemoryError('Cannot lock clipboard memory.')
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.EmptyClipboard() or not user32.SetClipboardData(8, handle):
            raise RuntimeError('Could not write the clipboard.')
        handle = None  # Windows owns the allocation after successful transfer.
    finally:
        if handle:
            kernel32.GlobalFree(handle)
        user32.CloseClipboard()


_keys = queue.Queue()
_stop = threading.Event()
_worker = None


def hotkeys(enable=True, shortcuts=None):
    global _worker
    bindings = validate(DEFAULT_SHORTCUTS if shortcuts is None else shortcuts) if enable else {}
    if _worker:
        _stop.set()
        _worker.join()
        _worker = None
    poll_hotkeys()  # Discard events queued under the previous bindings.
    if not enable:
        return []
    _stop.clear()
    ready = threading.Event()
    failed = []
    def pump():
        registered = []
        for name, shortcut in bindings.items():
            binding = parse_shortcut(shortcut)
            if binding is None:
                continue
            identifier = int(name)
            modifiers, key = binding
            if user32.RegisterHotKey(None, identifier, 0x4000 | modifiers, key):
                registered.append(identifier)
            else:
                failed.append(identifier)
        ready.set()
        message = wintypes.MSG()
        while not _stop.wait(.04):
            while user32.PeekMessageW(ctypes.byref(message), None, 0x312, 0x312, 1):
                _keys.put(message.wParam)
        for identifier in registered:
            user32.UnregisterHotKey(None, identifier)
    _worker = threading.Thread(target=pump, daemon=True)
    _worker.start()
    ready.wait(2)
    return failed


def poll_hotkeys():
    result = []
    while True:
        try:
            result.append(_keys.get_nowait())
        except queue.Empty:
            break
    return result


def scroll_at(box):
    user32.SetCursorPos((box[0]+box[2])//2, (box[1]+box[3])//2)
    user32.mouse_event(0x0800, 0, 0, ctypes.c_ulong(-240).value, 0)


def escape_pressed():
    return bool(user32.GetAsyncKeyState(0x1B) & 0x8000)
