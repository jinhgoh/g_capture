import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from app import App
import ocr
from settings import DEFAULT_SHORTCUTS, load_shortcuts, load_ocr, save_ocr, save_shortcuts


class OCRTests(unittest.TestCase):
    def test_settings_preserve_other_preferences_and_migrate_shortcuts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            old = {'1': 'Ctrl+F7', '2': 'Disabled', '3': 'Alt+Ctrl+O'}
            path.write_text(json.dumps({'shortcuts': old}), encoding='utf-8')
            self.assertEqual(load_shortcuts(path), dict(old, **{'4': 'Disabled'}))
            self.assertEqual(load_ocr(path), ocr.DEFAULT_OCR)
            options = {'languages': 'eng+jpn', 'executable': 'C:/OCR/tesseract.exe'}
            save_ocr(options, path)
            self.assertEqual(load_shortcuts(path)['1'], 'Ctrl+F7')
            save_shortcuts(DEFAULT_SHORTCUTS, path, open_editor_from_tray=True)
            self.assertEqual(load_ocr(path), options)
            with self.assertRaises(ValueError):
                save_ocr({'languages': '../bad'}, path)
            self.assertEqual(load_ocr(path), options)

    def test_recognition_uses_both_languages_and_preserves_unicode(self):
        with patch('ocr.find_executable', return_value='tesseract'), patch('ocr.run',
                   side_effect=['List of available languages (2):\neng\nkor\n', 'Hello 한글 123\n']) as run:
            result = ocr.recognize(Image.new('RGB', (20, 20)), ocr.DEFAULT_OCR)
        self.assertEqual(result, 'Hello 한글 123')
        self.assertIn('eng+kor', run.call_args.args[0])
        self.assertTrue(run.call_args.args[1].startswith(b'\x89PNG'))

    def test_missing_language_does_not_silently_fall_back(self):
        with patch('ocr.find_executable', return_value='tesseract'), patch('ocr.run', return_value='eng\n') as run:
            with self.assertRaisesRegex(RuntimeError, 'kor'):
                ocr.recognize(Image.new('RGB', (20, 20)), ocr.DEFAULT_OCR)
            self.assertEqual(run.call_count, 1)

    def test_success_empty_and_error_clipboard_behavior(self):
        for text, error in [('Hello 한글 123', None), ('', None), (None, RuntimeError('missing pack'))]:
            app = SimpleNamespace(busy=True, status=Mock(), capture_show_editor=True)
            with patch('app.windows.copy_text') as copy, patch('app.messagebox.showinfo'), patch('app.messagebox.showerror'):
                App.ocr_done(app, text, error)
                if text:
                    copy.assert_called_once_with(text)
                else:
                    copy.assert_not_called()
            self.assertFalse(app.busy)

    def test_cancel_restores_editor_without_recognition(self):
        app = SimpleNamespace(busy=True, capture_show_editor=True, deiconify=Mock(), lift=Mock(), status=Mock())
        with patch('ocr.recognize') as recognize:
            App.ocr_selected(app, None, None)
            recognize.assert_not_called()
        self.assertFalse(app.busy)
        app.deiconify.assert_called_once()

    def test_unicode_clipboard_encoding(self):
        import windows
        with patch('windows._copy_data') as copy:
            windows.copy_text('한글 123\nEnglish')
        copy.assert_called_once_with('한글 123\r\nEnglish\0'.encode('utf-16-le'), 13)

    def test_worker_delivers_result_through_ui_callback(self):
        app = SimpleNamespace(capture_show_editor=False, status=Mock(),
                              ocr_options=ocr.DEFAULT_OCR.copy(), after=Mock(), ocr_done=Mock())
        with patch('app.threading.Thread') as thread, patch('ocr.recognize', return_value='한글 123'):
            App.ocr_selected(app, Image.new('RGB', (20, 20)), None)
            app.ocr_done.assert_not_called()
            thread.call_args.kwargs['target']()
            app.after.call_args.args[1]()
        app.ocr_done.assert_called_once_with('한글 123', None)

    def test_hotkey_routes_to_ocr(self):
        app = SimpleNamespace(tray=None, busy=False, shortcut_dialog=None,
                              capture=Mock(), after=Mock(), poll=Mock())
        with patch('app.windows.poll_hotkeys', return_value=[4]):
            App.poll(app)
        app.capture.assert_called_once_with('OCR')

    def test_timeout_is_actionable(self):
        import subprocess
        with patch('ocr.subprocess.run', side_effect=subprocess.TimeoutExpired('tesseract', 60)):
            with self.assertRaisesRegex(RuntimeError, 'smaller selection'):
                ocr.run(['tesseract'])
