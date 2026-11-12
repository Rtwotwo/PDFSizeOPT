"""Install project-local dependencies without changing system configuration."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import time
import urllib.request
import venv
import zipfile

ROOT=Path(__file__).resolve().parent


def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):
            result.update(block)
    return result.hexdigest()


def fetch(url,destination):
    # Windows curl is more reliable than urllib behind some local proxies.
    curl=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32'/'curl.exe'
    if os.name=='nt' and curl.is_file():
        subprocess.run([str(curl),'--location','--fail','--connect-timeout','15',
            '--max-time','180','--silent','--show-error','--output',str(destination),url],
            check=True,timeout=200,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return
    request=urllib.request.Request(url,headers={'User-Agent':'PdfSizeOPT-Setup/1.0'})
    started=time.monotonic()
    with urllib.request.urlopen(request,timeout=30) as response,destination.open('wb') as handle:
        read=getattr(response,'read1',response.read)
        while True:
            if time.monotonic()-started>180:
                raise TimeoutError('Download exceeded three minutes; check network access and retry.')
            block=read(64*1024)
            if not block:break
            handle.write(block)


def download(spec,cache):
    cache.mkdir(parents=True,exist_ok=True)
    target=cache/spec['filename']
    if target.exists() and digest(target)==spec['sha256']:
        print('Verified cached '+target.name,flush=True)
        return target
    temporary=target.with_suffix(target.suffix+'.partial')
    print('Downloading '+spec['url'],flush=True)
    try:
        fetch(spec['url'],temporary)
        if digest(temporary)!=spec['sha256']:
            raise RuntimeError('Checksum mismatch for '+target.name+'. The download was not installed.')
        os.replace(temporary,target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def install_optimizer(root=ROOT):
    manifest=json.loads((root/'dependencies.json').read_text(encoding='utf-8'))
    bundle=download(manifest['pdfsizeopt_windows'],root/'.downloads')
    program=download(manifest['pdfsizeopt_program'],root/'.downloads')
    destination=root/'bin'
    destination.mkdir(exist_ok=True)
    with zipfile.ZipFile(bundle) as archive:
        for member in archive.infolist():
            name=PurePosixPath(member.filename.replace('\\','/'))
            if name.is_absolute() or '..' in name.parts or ':' in str(name):
                raise RuntimeError('Unsafe path in dependency archive.')
            target=(destination/Path(*name.parts)).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise RuntimeError('Dependency path escapes bin/.')
        archive.extractall(destination)
    shutil.copyfile(program,destination/'pdfsizeopt.single')
    if not (destination/'pdfsizeopt.exe').is_file():
        raise RuntimeError('Unexpected optimizer archive layout.')
    print('Pinned pdfsizeopt tools installed in bin/.',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-optimizer',action='store_true',help='Install the Python environment only.')
    parser.add_argument('--optimizer-only',action='store_true',help='Download verified optimizer tools without creating a Python environment.')
    args=parser.parse_args()
    if args.skip_optimizer and args.optimizer_only:
        parser.error('Choose only one of --skip-optimizer and --optimizer-only.')
    if os.name!='nt':
        raise RuntimeError('This installer targets Windows. See README.md for platform support.')
    if not args.optimizer_only:
        if sys.version_info[:2] not in ((3,12),(3,13)) or sys.maxsize<=2**32:
            raise RuntimeError('Use 64-bit Python 3.12 or 3.13, with pip and Tcl/Tk installed.')
        import tkinter
        tkinter.Tcl().eval('info patchlevel')
        environment=ROOT/'.venv'
        python=environment/'Scripts'/'python.exe'
        if not python.exists():
            print('Creating .venv/',flush=True)
            venv.EnvBuilder(with_pip=True).create(environment)
        print('Installing pinned Python dependencies...',flush=True)
        subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','-r',str(ROOT/'requirements.txt')],check=True)
        subprocess.run([str(python),'-c','import tkinter, pypdf, numpy, PIL, pypdfium2; tkinter.Tcl().eval("info patchlevel"); print("Python dependencies OK")'],check=True)
    if not args.skip_optimizer:
        install_optimizer()
    print('\nSetup complete. Double-click start.cmd to open PdfSizeOPT.',flush=True)
    print('Optional shortcut: run create_shortcut.ps1 from PowerShell.',flush=True)


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        print('\nSetup failed: '+str(error),file=sys.stderr)
        sys.exit(1)
