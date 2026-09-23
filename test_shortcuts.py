import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, call
from settings import DEFAULT_SHORTCUTS, parse_shortcut, validate, load_shortcuts, save_shortcuts


class ShortcutTests(unittest.TestCase):
    def test_print_screen_and_modifiers(self):
        self.assertEqual(parse_shortcut('Print Screen'), (0, 0x2C))
        self.assertEqual(parse_shortcut('Ctrl+Shift+F7'), (6, 0x76))
        self.assertIsNone(parse_shortcut('Disabled'))
        with self.assertRaises(ValueError):
            parse_shortcut('A')
        with self.assertRaises(ValueError):
            validate({'1': 'Ctrl+Alt+A', '2': 'Alt+Ctrl+A', '3': 'Disabled'})

    def test_preferences_roundtrip_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            self.assertEqual(load_shortcuts(path), DEFAULT_SHORTCUTS)
            prefs = {'1': 'Shift+Print Screen', '2': 'Disabled', '3': 'Ctrl+F9'}
            save_shortcuts(prefs, path)
            self.assertEqual(load_shortcuts(path), prefs)
            path.write_text('{broken', encoding='utf-8')
            self.assertEqual(load_shortcuts(path), DEFAULT_SHORTCUTS)

    def test_conflict_and_write_failure_restore_previous_bindings(self):
        from app import App
        fake = SimpleNamespace(shortcuts=DEFAULT_SHORTCUTS.copy(), update_shortcut_summary=lambda failed=(): None)
        candidate = dict(DEFAULT_SHORTCUTS, **{'1': 'Ctrl+F8'})
        with patch('app.windows.hotkeys', side_effect=[[1], []]) as register, patch('app.save_shortcuts') as save:
            with self.assertRaises(ValueError):
                App.apply_shortcuts(fake, candidate)
            save.assert_not_called()
            self.assertEqual(register.call_args.kwargs['shortcuts'], DEFAULT_SHORTCUTS)
            self.assertEqual(fake.shortcuts, DEFAULT_SHORTCUTS)
        with patch('app.windows.hotkeys', return_value=[]) as register, patch('app.save_shortcuts', side_effect=OSError('Read only')):
            with self.assertRaises(OSError):
                App.apply_shortcuts(fake, candidate)
            self.assertEqual(register.call_args.kwargs['shortcuts'], DEFAULT_SHORTCUTS)

    def test_registration_releases_old_keys(self):
        import windows
        try:
            with patch.object(windows.user32, 'RegisterHotKey', return_value=1) as register, patch.object(windows.user32, 'UnregisterHotKey', return_value=1) as unregister:
                windows.hotkeys(shortcuts=DEFAULT_SHORTCUTS)
                self.assertIn(call(None, 1, 0x4000, 0x2C), register.call_args_list)
                windows.hotkeys(shortcuts={'1': 'Ctrl+F8', '2': 'Disabled', '3': 'Disabled'})
                self.assertEqual(unregister.call_count, 3)
                windows.hotkeys(False)
                self.assertEqual(unregister.call_count, 4)
        finally:
            windows.hotkeys(False)

    def test_dialog_opens(self):
        from app import App
        import windows
        app = App()
        try:
            app.show_shortcuts()
            app.update()
            self.assertTrue(app.shortcut_dialog.winfo_exists())
        finally:
            windows.hotkeys(False)
            app.destroy()
