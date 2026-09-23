import queue
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app import App


class TrayTests(unittest.TestCase):
    def test_close_hides_without_destroying_editor(self):
        app = SimpleNamespace(tray=Mock(), busy=False, withdraw=Mock(), destroy=Mock())
        App.close(app)
        app.withdraw.assert_called_once()
        app.destroy.assert_not_called()

    def test_quit_exits_without_scheduling_another_poll(self):
        commands = queue.Queue()
        commands.put('quit')
        app = SimpleNamespace(tray=SimpleNamespace(commands=commands), busy=False,
                              destroy=Mock(), after=Mock())
        App.poll(app)
        app.destroy.assert_called_once()
        app.after.assert_not_called()

    def test_startup_toggle_disables_existing_startup(self):
        commands = queue.Queue()
        commands.put('startup')
        app = SimpleNamespace(tray=SimpleNamespace(commands=commands, icon=Mock()),
                              after=Mock(), poll=Mock())
        with patch('app.startup_enabled', return_value=True), patch('app.set_startup') as change, \
                patch('app.windows.poll_hotkeys', return_value=[]):
            App.poll(app)
        change.assert_called_once_with(False)
        app.tray.icon.update_menu.assert_called_once()
