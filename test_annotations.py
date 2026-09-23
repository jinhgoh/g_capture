import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from app import App


class EditableAnnotationTests(unittest.TestCase):
    def setUp(self):
        self.app = App()
        self.app.set_image(Image.new('RGB', (400, 300), 'white'))
        self.app.zoom.set('100%')
        self.app.update()

    def tearDown(self):
        self.app.destroy()

    def event(self, x, y):
        return SimpleNamespace(x=x+12, y=y+12)

    def add(self, kind, start=(30, 30), end=(100, 100)):
        self.app.tool.set(kind)
        with patch('app.simpledialog.askstring', return_value='Hello'):
            self.app.edit_start(self.event(*start))
            self.app.edit_move(self.event(*end))
            self.app.edit_end(self.event(*end))

    def test_move_resize_and_undo_redo(self):
        for kind in ['Arrow', 'Rectangle', 'Ellipse', 'Pen', 'Highlighter', 'Text', 'Mosaic']:
            with self.subTest(kind=kind):
                self.app.set_image(Image.new('RGB', (400, 300), 'white'))
                self.add(kind)
                original = self.app.image.tobytes()
                bounds = self.app.annotations[0].bounds()
                x, y = (bounds[0]+bounds[2])/2, (bounds[1]+bounds[3])/2
                self.app.edit_start(self.event(x, y))
                self.app.edit_end(self.event(x+20, y+10))
                moved = self.app.annotations[0].bounds()
                self.assertEqual(moved[0], bounds[0]+20)
                self.assertEqual(moved[1], bounds[1]+10)
                self.app.undo()
                self.assertEqual(self.app.image.tobytes(), original)
                self.app.redo()
                self.app.selected = 0
                self.app.edit_start(self.event(moved[2], moved[3]))
                self.app.edit_end(self.event(moved[2]+30, moved[3]+30))
                resized = self.app.annotations[0].bounds()
                self.assertGreater(resized[2]-resized[0], moved[2]-moved[0])

    def test_text_style_delete_and_crop_preserve_editability(self):
        self.add('Text')
        with patch('app.simpledialog.askstring', return_value='Changed'):
            self.app.edit_text()
        self.app.font_size.set(42)
        self.app.apply_style()
        self.assertEqual(self.app.annotations[0].text, 'Changed')
        self.assertEqual(self.app.annotations[0].font_size, 42)
        before_crop = self.app.image.copy()
        self.add('Crop', (10, 10), (300, 200))
        self.assertEqual(self.app.image.tobytes(), before_crop.crop((10, 10, 300, 200)).tobytes())
        self.assertEqual(self.app.annotations[0].points[0], (20, 20))
        self.app.tool.set('Select')
        self.app.selected = 0
        self.app.delete_annotation()
        self.assertEqual(len(self.app.annotations), 0)
        self.app.undo()
        self.assertEqual(self.app.annotations[0].text, 'Changed')
        self.app.undo()
        self.assertEqual(self.app.image.tobytes(), before_crop.tobytes())

    def test_export_uses_composite_without_selection_handles(self):
        self.add('Arrow')
        with patch('app.windows.copy_image') as copy_image:
            self.app.copy()
        self.assertEqual(copy_image.call_args.args[0].tobytes(), self.app.image.tobytes())
        self.assertNotEqual(self.app.image.tobytes(), self.app.base_image.tobytes())


if __name__ == '__main__':
    unittest.main()
