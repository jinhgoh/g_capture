import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PIL import Image
from app import App


class CaptureFlowTests(unittest.TestCase):
    def fake_app(self):
        return SimpleNamespace(busy=True, dirty=True, deiconify=Mock(), lift=Mock(),
                               set_image=Mock(), status=SimpleNamespace(set=Mock()))

    def test_completed_capture_copies_and_keeps_image(self):
        app = self.fake_app()
        image = Image.new('RGB', (10, 10))
        with patch('app.windows.copy_image') as copy:
            App.capture_done(app, image, None)
        copy.assert_called_once_with(image)
        app.set_image.assert_called_once_with(image, add_history=True)
        self.assertFalse(app.busy)

    def test_cancellation_does_not_change_clipboard_or_image(self):
        app = self.fake_app()
        with patch('app.windows.copy_image') as copy:
            App.capture_done(app, None, None)
        copy.assert_not_called()
        app.set_image.assert_not_called()

    def test_clipboard_failure_keeps_capture_without_dialog(self):
        app = self.fake_app()
        image = Image.new('RGB', (10, 10))
        with patch('app.windows.copy_image', side_effect=RuntimeError('Clipboard busy')), patch('app.messagebox.showerror') as dialog:
            App.capture_done(app, image, None)
        app.set_image.assert_called_once_with(image, add_history=True)
        self.assertIn('automatic copy failed', app.status.set.call_args.args[0])
        dialog.assert_not_called()

    def test_new_capture_and_close_ignore_dirty_state(self):
        app = SimpleNamespace(busy=False, dirty=True, delay=Mock(get=lambda: 0),
                              fixed_w=Mock(get=lambda: 800), fixed_h=Mock(get=lambda: 600),
                              withdraw=Mock(), after=Mock(), destroy=Mock())
        with patch('app.messagebox.askyesno') as prompt:
            App.capture(app, 'Region')
            App.close(app)
        prompt.assert_not_called()
        app.after.assert_called_once()
        app.destroy.assert_called_once()
