"""Editable annotations, rendered in insertion order over the source image."""
from dataclasses import dataclass
from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFont
from imaging import mosaic


@dataclass
class Annotation:
    kind: str
    points: list
    color: str = '#ff535f'
    width: int = 3
    text: str = ''
    font_size: int = 24

    def font(self):
        path = Path('C:/Windows/Fonts/malgun.ttf')
        return ImageFont.truetype(str(path), self.font_size) if path.exists() else ImageFont.load_default(size=self.font_size)

    def bounds(self):
        xs, ys = zip(*self.points)
        if self.kind == 'Text':
            box = self.font().getbbox(self.text)
            x, y = self.points[0]
            return x, y, x + max(1, box[2]), y + max(1, box[3])
        return min(xs), min(ys), max(xs), max(ys)

    def move(self, dx, dy):
        self.points = [(x + dx, y + dy) for x, y in self.points]

    def resize(self, box):
        x0, y0, x1, y1 = self.bounds()
        a, b, c, d = box
        sx, sy = (c-a)/max(1, x1-x0), (d-b)/max(1, y1-y0)
        self.points = [(a+(x-x0)*sx, b+(y-y0)*sy) for x, y in self.points]
        if self.kind == 'Text':
            self.font_size = max(6, min(300, round(self.font_size * min(sx, sy))))

    def draw(self, image):
        if self.kind == 'Mosaic':
            box = self.bounds()
            box = (max(0, round(box[0])), max(0, round(box[1])),
                   min(image.width, round(box[2])), min(image.height, round(box[3])))
            return mosaic(image, box) if box[2] > box[0] and box[3] > box[1] else image
        overlay = Image.new('RGBA', image.size)
        draw = ImageDraw.Draw(overlay)
        start, end = self.points[0], self.points[-1]
        if self.kind in ('Pen', 'Highlighter'):
            draw.line(self.points, fill=self.color + ('60' if self.kind == 'Highlighter' else 'ff'),
                      width=max(12, self.width*5) if self.kind == 'Highlighter' else self.width, joint='curve')
        elif self.kind in ('Rectangle', 'Ellipse'):
            getattr(draw, self.kind.lower())(self.bounds(), outline=self.color, width=self.width)
        elif self.kind == 'Arrow':
            draw.line([start, end], fill=self.color, width=self.width)
            angle = math.atan2(end[1]-start[1], end[0]-start[0])
            length = max(14, self.width*4)
            draw.polygon([end] + [(end[0]-length*math.cos(angle+a), end[1]-length*math.sin(angle+a))
                                  for a in (-.5, .5)], fill=self.color)
        elif self.kind == 'Text':
            draw.text(start, self.text, fill=self.color, font=self.font())
        return Image.alpha_composite(image.convert('RGBA'), overlay)


def composite(base, annotations):
    image = base.copy()
    for annotation in annotations:
        image = annotation.draw(image)
    return image
