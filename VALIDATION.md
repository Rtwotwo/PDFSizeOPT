# Validation notes

Recorded on Windows x64 with Python 3.12 and the pinned application dependencies.

## Default-profile regression

A single-page, vector-heavy reference figure was processed through the batch worker.

| Measurement | Result |
|---|---:|
| Input | 23,114,956 bytes |
| Output | 2,337,355 bytes |
| Reduction | 89.888% |
| Initial processing time | 15.78 seconds |
| Changed pixels at 2,000-pixel long edge | 0 |
| Changed pixels at 8,000-pixel long edge | 0 |
| Inlined simple form invocations | 43,630 |
| Lossy photo re-encodings | 0 |

Page count, geometry, annotation counts, and catalog-feature checks passed. The source file's digest remained unchanged. A second run from the desktop package with Chinese input/output paths produced the same result in 22.88 seconds. An already-optimized input with the same basename was preserved unchanged and saved with a numeric suffix.

The reference PDF is not distributed. This example measures the benefit for a file with many redundant vector objects, not a general compression benchmark. Pixel agreement refers to PDFium at the stated scales, not all viewers or zoom levels.

## Automated tests

All 12 tests passed in a clean environment installed from the public package versions in `requirements.txt`. Tests generate synthetic fixtures for naming, source preservation, cancellation, atomic output, bookmarks and metadata, transformed and clipped graphics, visual-difference rejection with fallback, optional photo compression without resizing, and installer checksum/cache/archive handling.

The complete setup was exercised, including the pinned upstream tool bundle and program. A regression through this fresh installation reproduced the 2,337,355-byte output with zero differences at both render scales in 35.08 seconds. Timing varies with system load and should not be treated as a performance guarantee.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
