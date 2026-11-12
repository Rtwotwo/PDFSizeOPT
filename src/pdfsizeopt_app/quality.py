"""Native-resolution photo checks; a page average cannot protect small photos."""
import io
import threading

import numpy as np
from PIL import Image, ImageFile


MIN_PHOTO_PSNR = 48.0
MIN_TILE_P01_PSNR = 42.0
MIN_TILE_PSNR = 40.0
_JPEG_LOCK = threading.Lock()


def encode_jpeg(image, quality):
    # Pillow's default optimized-JPEG buffer assumes at most 2 bytes/pixel.
    # High-entropy 4:4:4 images can exceed that. Restore the global afterwards.
    with _JPEG_LOCK:
        previous = ImageFile.MAXBLOCK
        try:
            ImageFile.MAXBLOCK = max(previous, image.width*image.height*4 + 65536)
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=quality, subsampling=0, optimize=True)
            return buffer.getvalue()
        finally:
            ImageFile.MAXBLOCK = previous


def photo_metrics(original, decoded):
    """RGB error at native resolution, including every edge tile (64 x 64)."""
    a, b = np.asarray(original), np.asarray(decoded)
    if a.shape != b.shape:
        raise ValueError('Photo dimensions or channels changed')
    total = absolute = 0
    tiles = []
    # Keep error buffers bounded, including for large photographic images.
    for y in range(0, a.shape[0], 64):
        diff = a[y:y+64].astype(np.int32) - b[y:y+64].astype(np.int32)
        squared = diff * diff
        total += int(squared.sum())
        absolute += int(np.abs(diff).sum())
        for x in range(0, a.shape[1], 64):
            tiles.append(float(squared[:, x:x+64].mean()))
    def psnr(mse):
        return float(10*np.log10(65025/mse)) if mse else 120.0
    return {'psnr_db': psnr(total/a.size),
            'tile_p01_psnr_db': psnr(float(np.percentile(tiles, 99))),
            'tile_min_psnr_db': psnr(max(tiles)),
            'mean_absolute_error_255': absolute/a.size}


def choose_photo_encoding(image, requested_quality, max_bytes, cancel=None):
    """Raise quality as needed; retain original if no smaller candidate passes.

    JPEG quality is a starting value, never reduced to chase file size.
    Existing JPEGs are filtered by the caller and are never re-encoded here.
    """
    native = image.convert('RGB')
    for quality in sorted(set(range(requested_quality, 101, 2)) | {100}):
        if cancel is not None and cancel.is_set():
            return None  # The caller raises its normal cancellation exception.
        try:
            data = encode_jpeg(image, quality)
        except (OSError, ValueError):
            return None  # Unsupported/failed image encoding preserves the original.
        if len(data) >= max_bytes:
            continue
        with Image.open(io.BytesIO(data)) as candidate:
            metrics = photo_metrics(native, candidate.convert('RGB'))
        if (metrics['psnr_db'] >= MIN_PHOTO_PSNR
                and metrics['tile_p01_psnr_db'] >= MIN_TILE_P01_PSNR
                and metrics['tile_min_psnr_db'] >= MIN_TILE_PSNR):
            return data, {'quality': quality, **{k: round(v, 5) for k, v in metrics.items()}}
    return None
