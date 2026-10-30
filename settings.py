"""Validated, portable shortcut preferences."""
import json
from pathlib import Path

SETTINGS_PATH = Path(__file__).with_name('settings.json')
DEFAULT_SHORTCUTS = {'1': 'Print Screen', '2': 'Ctrl+Alt+2', '3': 'Ctrl+Alt+3', '4': 'Ctrl+Alt+O'}
KEYS = ['Print Screen'] + [f'F{i}' for i in range(1, 12)] + list('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
MODIFIERS = {'Ctrl': 2, 'Alt': 1, 'Shift': 4}


def parse_shortcut(value):
    if value == 'Disabled':
        return None
    if not isinstance(value, str):
        raise ValueError('Invalid shortcut.')
    parts = value.split('+')
    key = parts[-1]
    modifiers = parts[:-1]
    if key not in KEYS or len(set(modifiers)) != len(modifiers) or any(m not in MODIFIERS for m in modifiers):
        raise ValueError('Choose a supported key and modifiers.')
    if len(key) == 1 and not modifiers:
        raise ValueError('Letters and numbers need at least one modifier.')
    vk = 0x2C if key == 'Print Screen' else (0x6F + int(key[1:]) if key.startswith('F') and len(key) > 1 else ord(key))
    return sum(MODIFIERS[m] for m in modifiers), vk


def validate(shortcuts):
    if not isinstance(shortcuts, dict) or set(shortcuts) != set(DEFAULT_SHORTCUTS):
        raise ValueError('Invalid shortcut settings.')
    bindings = [parse_shortcut(value) for value in shortcuts.values()]
    active = [binding for binding in bindings if binding is not None]
    if len(active) != len(set(active)):
        raise ValueError('Each capture mode must use a different shortcut.')
    return dict(shortcuts)


def load_shortcuts(path=SETTINGS_PATH):
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))['shortcuts']
        if isinstance(saved, dict) and set(saved) == {'1', '2', '3'}:
            binding = parse_shortcut(DEFAULT_SHORTCUTS['4'])
            saved['4'] = 'Disabled' if binding in [parse_shortcut(v) for v in saved.values()] else DEFAULT_SHORTCUTS['4']
        return validate(saved)
    except (OSError, ValueError, KeyError, TypeError):
        return DEFAULT_SHORTCUTS.copy()


def load_open_editor_from_tray(path=SETTINGS_PATH):
    try:
        return json.loads(path.read_text(encoding='utf-8')).get('open_editor_from_tray') is True
    except (OSError, ValueError, AttributeError):
        return False


def save_shortcuts(shortcuts, path=SETTINGS_PATH, *, open_editor_from_tray=None):
    if open_editor_from_tray is None:
        open_editor_from_tray = load_open_editor_from_tray(path)
    content = json.dumps(dict(_read_settings(path), shortcuts=validate(shortcuts),
                              open_editor_from_tray=bool(open_editor_from_tray)), indent=2)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(content + '\n', encoding='utf-8')
    temporary.replace(path)


def _read_settings(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def load_ocr(path=SETTINGS_PATH):
    from ocr import DEFAULT_OCR, validate_options
    try:
        return validate_options(_read_settings(path).get('ocr', DEFAULT_OCR))
    except ValueError:
        return DEFAULT_OCR.copy()


def save_ocr(options, path=SETTINGS_PATH):
    from ocr import validate_options
    content = dict(_read_settings(path), ocr=validate_options(options))
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(content, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)
