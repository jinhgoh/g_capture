import unittest
from types import SimpleNamespace
import numpy as np
from PIL import Image
from imaging import mosaic, stitch


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.source = Image.fromarray(np.random.default_rng(7).integers(0, 256, (1100, 240, 3), dtype=np.uint8))

    def test_stitch_multiple_frames(self):
        first = self.source.crop((0, 0, 240, 400))
        combined, added = stitch(first, self.source.crop((0, 170, 240, 570)))
        self.assertEqual(added, 170)
        combined, added = stitch(combined, self.source.crop((0, 340, 240, 740)))
        self.assertEqual(added, 170)
        self.assertEqual(combined.tobytes(), self.source.crop((0, 0, 240, 740)).tobytes())

    def test_scroll_bottom(self):
        self.assertEqual(stitch(self.source, self.source.crop((0, 700, 240, 1100)))[1], 0)

    def test_unrelated_frames_rejected(self):
        with self.assertRaises(ValueError):
            stitch(self.source.crop((0, 0, 240, 400)), Image.new('RGB', (240, 400), 'white'))

    def test_mosaic_only_changes_selection(self):
        result = mosaic(self.source, (20, 30, 100, 120))
        self.assertEqual(result.crop((100, 0, 240, 1100)).tobytes(), self.source.crop((100, 0, 240, 1100)).tobytes())
        self.assertNotEqual(result.tobytes(), self.source.tobytes())


class DesktopTests(unittest.TestCase):
    def test_editor_and_desktop(self):
        import windows
        from app import App
        windows.dpi_aware()
        app = App()
        try:
            app.update()
            shot = windows.grab()
            self.assertGreater(shot.width, 0)
            app.set_image(Image.new('RGB', (320, 240), 'white'), True)
            app.update()
            for tool in ['Pen', 'Highlighter', 'Arrow', 'Rectangle', 'Ellipse', 'Mosaic', 'Crop']:
                app.tool.set(tool)
                before = app.image.copy()
                app.edit_start(SimpleNamespace(x=35, y=35))
                app.edit_move(SimpleNamespace(x=150, y=120))
                app.edit_end(SimpleNamespace(x=150, y=120))
                self.assertTrue(app.undo_stack)
                after = app.image.copy()
                app.undo()
                self.assertEqual(app.image.tobytes(), before.tobytes())
                app.redo()
                self.assertEqual(app.image.tobytes(), after.tobytes())
                app.undo()
            self.assertEqual(len(app.history), 1)
            app.clear_history()
            self.assertEqual(len(app.history), 0)
        finally:
            windows.hotkeys(False)
            app.destroy()


if __name__ == '__main__':
    unittest.main()
