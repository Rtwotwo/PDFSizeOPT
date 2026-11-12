# Local compression benchmark

Use the corpus runner to compare strict lossless and adaptive photo profiles on PDFs you are authorized to process. Source files and derived measurements stay on your machine. The repository does not include the private test corpus or its measurements.

## Run

```powershell
.\.venv\Scripts\python.exe benchmarks\run_corpus.py C:\MyPDFs C:\PDFBenchmarkResults
```

Use a separate output directory outside the input directory. Subdirectories are scanned. The harness retains filenames and records sizes, settings, timing, source hashes, and verification results. Outputs are split into `lossless` and `adaptive_photo`. Per-file errors are recorded in `results.json` and produce a nonzero exit status. It never uploads data.

The default verification long edge is 8,000 pixels. You can set it with `--width`. Every page is also checked at 2,000 pixels or the selected width if lower. Larger widths require more time and memory.

## Choose a varied corpus

Include uncompressed photographs with different lighting and texture, video-frame montages, vector charts, photographs mixed with text, transparent images, grayscale images, and already-compressed controls. Include multi-page documents when that matches your workflow. Keep redundant exports and already-compressed controls clearly labeled rather than treating them as independent samples.

## Inspect the results

1. Check that inputs are unchanged and outputs have not grown.
2. For strict lossless results, require exact rendered agreement at the tested scales or an unchanged original copy.
3. For re-encoded photos, inspect native dimensions and the per-image quality metrics in `reencoded_photos`. The JPEG starting quality is raised when necessary; it is never lowered to meet a size target.
4. Review native-resolution crops of fine textures, dark areas, edges, labels, and small details side by side.
5. Where possible, repeat representative rendering checks with a second PDF renderer.

Decode the actual stored JPEG streams for independent native-image measurements. Some PDF image-export helpers can re-save JPEGs and introduce a separate encoding error that is unrelated to the compressor.

## Interpretation

Compression depends on input redundancy and existing encoding. Already-compressed images and compact vector files may show little or no reduction. A large reduction on a redundant vector export does not predict the same result on a photographic PDF.

Adaptive photo mode is lossy even at JPEG quality 100. Native-image and local-tile thresholds limit error but do not prove perceptual equivalence for every subject. Exact rendered agreement at finite scales also does not prove equivalence in every PDF viewer or interactive feature. Retain strict lossless mode when that is required.

Machine-specific reports may reveal source names, hashes, or document characteristics. The default generated reports and benchmark results are ignored by Git; review and authorize any publication separately.
