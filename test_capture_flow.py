import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PIL import Image
from app import App


class CaptureFlowTests(unittest.TestCase):
    def fake_app(self):
        return SimpleNamespace(busy=True, dirty=True, capture_show_editor=True, deiconify=Mock(), lift=Mock(),
                               set_image=Mock(), status=SimpleNamespace(set=Mock()))

    def test_completed_capture_copies_and_keeps_image(self):
        app = self.fake_app()
        image = Image.new('RGB', (10, 10))
        with patch('app.windows.copy_image') as copy:
            App.capture_done(app, image, None)
        copy.assert_called_once_with(image)
        app.set_image.assert_called_once_with(image, add_history=True)
        app.deiconify.assert_called_once()
        app.lift.assert_called_once()
        self.assertFalse(app.busy)

    def test_cancellation_keeps_window_hidden_and_preserves_clipboard_and_image(self):
        app = self.fake_app()
        with patch('app.windows.copy_image') as copy:
            App.capture_done(app, None, None)
        copy.assert_not_called()
        app.set_image.assert_not_called()
        app.deiconify.assert_not_called()
        app.lift.assert_not_called()
        self.assertFalse(app.busy)

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
                              state=Mock(return_value='normal'), open_editor_from_tray=False,
                              fixed_w=Mock(get=lambda: 800), fixed_h=Mock(get=lambda: 600),
                              withdraw=Mock(), after=Mock(), destroy=Mock())
        with patch('app.messagebox.askyesno') as prompt:
            App.capture(app, 'Region')
            App.close(app)
        prompt.assert_not_called()
        app.after.assert_called_once()
        app.destroy.assert_called_once()

    def test_capture_respects_initial_window_state_and_preference(self):
        for state in ('withdrawn', 'normal', 'iconic', 'zoomed'):
            for preference in (False, True):
                with self.subTest(state=state, preference=preference):
                    app = self.fake_app()
                    app.busy = False
                    app.state = Mock(return_value=state)
                    app.open_editor_from_tray = preference
                    app.delay = Mock(get=lambda: 0)
                    app.fixed_w = Mock(get=lambda: 800)
                    app.fixed_h = Mock(get=lambda: 600)
                    app.withdraw = Mock()
                    app.after = Mock()
                    App.capture(app, 'Region')
                    image = Image.new('RGB', (10, 10))
                    with patch('app.windows.copy_image') as copy:
                        App.capture_done(app, image, None)
                    copy.assert_called_once_with(image)
                    app.set_image.assert_called_once_with(image, add_history=True)
                    expected = state != 'withdrawn' or preference
                    self.assertEqual(app.deiconify.called, expected)
                    self.assertEqual(app.lift.called, expected)
