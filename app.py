"""Entry point for the desktop app and its isolated compression worker."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
if (ROOT/'runtime'/'tcl'/'tcl8.6').exists():
    os.environ['TCL_LIBRARY'] = str(ROOT/'runtime'/'tcl'/'tcl8.6')
    os.environ['TK_LIBRARY'] = str(ROOT/'runtime'/'tcl'/'tk8.6')
if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        from pdfsizeopt_app.worker import run
        sys.exit(run(Path(sys.argv[2])))
    try:
        from pdfsizeopt_app.gui import main
        main(sys.argv[1:])
    except Exception:
        import traceback
        (ROOT/'logs').mkdir(exist_ok=True)
        (ROOT/'logs'/'startup_error.log').write_text(traceback.format_exc(),encoding='utf-8')
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,'启动失败，详情已保存到 logs/startup_error.log。','PdfSizeOPT',16)
        raise
