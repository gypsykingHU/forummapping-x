"""JPEG helpers (Instagram only accepts JPEG; X accepts it too).

Rules (Milan, 2026-11-20):
  * Existing library: PNG masters stay in Posts/ for X; a JPEG copy of every non-JPEG map lives in
    Posts_jpeg/<same-stem>.jpg and is what Instagram posts.
  * New maps from now on are converted to JPEG at intake and stored ONLY as JPEG in Posts/
    (used by both X and Instagram).
  * jpeg_path(filename) -> the JPEG file to use for Instagram: Posts/<file> if it is already a JPEG,
    otherwise Posts_jpeg/<stem>.jpg.
"""
import os
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS = os.path.join(REPO, "Posts")
POSTS_JPEG = os.path.join(REPO, "Posts_jpeg")
QUALITY = 92
JPEG_EXT = (".jpg", ".jpeg")


def is_jpeg(name):
    return name.lower().endswith(JPEG_EXT)


def to_jpeg(src, dst, quality=QUALITY):
    """Convert any PIL-readable image to a high-quality sRGB JPEG (alpha flattened onto white).
    4:4:4 chroma keeps map text and thin borders crisp. Returns (width, height)."""
    im = Image.open(src)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    tmp = dst + ".tmp"
    im.save(tmp, format="JPEG", quality=quality, optimize=True, subsampling=0)
    os.replace(tmp, dst)
    return im.size


def jpeg_path(filename):
    """Path of the JPEG to post to Instagram for a library filename."""
    if is_jpeg(filename):
        return os.path.join(POSTS, filename)
    return os.path.join(POSTS_JPEG, os.path.splitext(filename)[0] + ".jpg")
