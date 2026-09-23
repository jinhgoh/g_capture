"""Pure image operations used by the editor and scrolling capture."""
import numpy as np
from PIL import Image


def mosaic(image, box, block=14):
    result = image.copy()
    region = result.crop(box)
    region = region.resize((max(1, region.width // block), max(1, region.height // block)), Image.Resampling.BOX)
    result.paste(region.resize((box[2] - box[0], box[3] - box[1]), Image.Resampling.NEAREST), box)
    return result


def stitch(previous, frame, minimum=40):
    """Find vertical overlap. Return (combined, appended pixels); reject ambiguous jumps.

    Match the most recent viewport, not a downscaled long composite. Animated
    content and sticky elements can prevent matching; callers must stop on failure.
    """
    previous, frame = previous.convert('RGB'), frame.convert('RGB')
    if previous.width != frame.width:
        raise ValueError('Scrolling capture width changed.')
    height = min(previous.height, frame.height)
    width = min(160, frame.width)
    a = np.asarray(previous.crop((0, previous.height-height, previous.width, previous.height)).resize((width, height)), dtype=np.float32)
    b = np.asarray(frame.resize((width, frame.height)), dtype=np.float32)
    if np.abs(a - b[-height:]).mean() < 1.2:
        return previous, 0
    # Ignore narrow borders and scrollbar during alignment.
    margin = max(1, width // 12)
    a, b = a[:, margin:-margin], b[:, margin:-margin]
    scores = [(float(np.abs(a[-n:] - b[:n]).mean()), n) for n in range(minimum, height)]
    if not scores:
        raise ValueError('Select a scrolling region at least 80 pixels tall.')
    error, overlap = min(scores)
    if error > 12:
        raise ValueError('Could not align this page. Avoid fixed headers, animations, and large scroll jumps.')
    addition = frame.height - overlap
    if previous.height + addition > 30000:
        raise ValueError('Reached the 30,000 pixel height limit.')
    result = Image.new('RGB', (previous.width, previous.height + addition))
    result.paste(previous)
    result.paste(frame.crop((0, overlap, frame.width, frame.height)), (0, previous.height))
    return result, addition
