# Contributing

Bug reports, documentation improvements, and focused pull requests are welcome.

## Report a problem

Open a [GitHub issue](https://github.com/Rtwotwo/PDFSizeOPT/issues) with your Windows and Python versions, the settings used, expected behavior, and the observed result. Include a minimal reproducible PDF only if it is safe to share. Local reports contain file paths and hashes, so remove personal details before attaching them.

## Propose a change

1. Follow the [installation instructions](README.md#installation).
2. Read the [engine guide](docs/ENGINE.md) before changing compression behavior.
3. Keep the change focused and update the relevant documentation.
4. Run the tests with `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`.

Changes to rendering or rewriting should include a synthetic fixture or reproducible example that exercises the affected behavior. Report measured quality and size results without presenting a single example as a universal compression guarantee. Keep private PDFs, local environments, logs, and settings out of commits.

Original contributions to this project are provided under its [MIT License](LICENSE). Preserve third-party attribution and applicable license notices.
