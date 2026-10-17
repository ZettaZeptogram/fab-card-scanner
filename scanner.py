import difflib
import re
from datetime import date
from datetime import datetime
import os

import numpy as np
from PIL import Image, ImageOps
from rapidocr_onnxruntime import RapidOCR

engine = RapidOCR()

def strip_of(path, top, bottom):
    """Cut a horizontal band out of a photo; top and bottom are fractions of its height."""
    img = ImageOps.exif_transpose(Image.open(path)).convert("L")   # L = grayscale
    w, h = img.size
    band = img.crop((0, int(h * top), w, int(h * bottom)))
    name = datetime.now().strftime("%Y%m%d-%H%M%S-%f cropped") + ".jpg"
    path = os.path.join("photos/cropped", name)
    band.save(path)
    return band.resize((band.width * 2, band.height * 2))        # enlarge small print


def read_text(img):
    """Run OCR on a picture; return the pieces of text it found."""
    result, _ = engine(np.array(img))
    return [text for _box, text, score in (result or []) if score > 0.5]


# characters OCR often confuses with each other
CONFUSED = {"I": "1", "1": "I", "O": "0", "0": "O", "S": "5", "5": "S", "B": "8", "8": "B"}


def parse_code(text, valid_codes):
    t = re.sub(r"[^A-Z0-9]", "", text.upper())

    # Find every possible 3-character code followed by 1-4 digits/O's
    pattern = r"([A-Z0-9]{3})([0-9O]{1,4})"

    for m in re.finditer(pattern, t):
        code, number = m.groups()

        # Require at least one actual digit
        if not any(ch.isdigit() for ch in number):
            continue

        number = int(number.replace("O", "0"))

        if code not in valid_codes:
            # Try correcting commonly confused characters
            swaps = [
                code[:i] + CONFUSED[ch] + code[i + 1:]
                for i, ch in enumerate(code)
                if ch in CONFUSED
            ]

            fixed = [c for c in swaps if c in valid_codes]

            if not fixed:
                continue

            code = fixed[0]

        return code, number

    return None


def clean_name(text):
    """Lowercase and drop odd symbols, so OCR text can be compared with card names."""
    return re.sub(r"[^a-z0-9 ,'-]", "", text.lower()).strip()