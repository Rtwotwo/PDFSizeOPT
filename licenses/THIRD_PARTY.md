# Third-party components

This project's original application code, documentation, and logo are covered by the [MIT License](../LICENSE). That license does not replace any of the third-party terms below.

This source repository does not redistribute Python runtimes, Python wheels, or the optimizer's executable bundle. `setup_windows.py` installs packages into `.venv/` and downloads the optional optimizer directly from upstream. Generated dependencies are excluded from Git.

| Component | License / notices | Upstream |
|---|---|---|
| CPython | Python Software Foundation License | https://www.python.org/ |
| Tcl/Tk | BSD-style terms; consult the installed distribution | https://www.tcl.tk/ |
| pypdf | BSD-3-Clause | https://github.com/py-pdf/pypdf |
| NumPy | BSD-3-Clause plus bundled numerical-library notices | https://numpy.org/ |
| Pillow | HPND plus bundled dependency notices | https://python-pillow.github.io/ |
| pypdfium2 / PDFium | Apache-2.0 / BSD-style plus PDFium third-party notices | https://github.com/pypdfium2-team/pypdfium2 |
| pdfsizeopt | GPL-2.0; its tool bundle has separate component licenses | https://github.com/pts/pdfsizeopt |

Installed packages contain their license notices, typically under `*.dist-info/licenses/`. A prepared local runtime also retains its Python and Tcl/Tk license files.

The optional optimizer runs as a separate process. Its ZIP release and program revision are pinned in `dependencies.json`, with checksums verified before installation. The application disables PNGOUT, JBIG2, font optimization, font unification, and font regeneration. Inclusion in the upstream bundle does not mean a component is invoked.

If redistributing an installed runtime or executable bundle, retain applicable notices and meet the redistribution and source-availability requirements of each component. Refer to upstream for the full terms.

The original optimizer is [pts/pdfsizeopt](https://github.com/pts/pdfsizeopt), by Peter Szabo and contributors. Its [license](https://github.com/pts/pdfsizeopt/blob/master/LICENSE) and [source tree at the pinned program revision](https://github.com/pts/pdfsizeopt/tree/bc6c3ec21eb73888797f6411c6c96dadfeb56f76/lib/pdfsizeopt) remain available upstream. The executable bundle is obtained from its [official release](https://github.com/pts/pdfsizeopt/releases/tag/2023-04-18).
