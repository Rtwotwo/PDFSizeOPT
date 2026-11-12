"""Run both profiles on your own PDFs. Inputs are never uploaded or modified."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pdfsizeopt_app.engine import Settings, compress_pdf, sha256


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_dir',type=Path)
    parser.add_argument('output_dir',type=Path)
    parser.add_argument('--width',type=int,default=8000)
    args=parser.parse_args()
    source=args.input_dir.resolve(strict=True)
    output=args.output_dir.resolve()
    if output==source or source in output.parents:
        parser.error('Use an output directory outside the input directory.')
    files=sorted(source.rglob('*.pdf'))
    if not files:parser.error('No PDF inputs found.')
    output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for i,path in enumerate(files,1):
        digest=sha256(path)
        relative=path.relative_to(source)
        for profile,lossy in (('lossless',False),('adaptive_photo',True)):
            try:
                result=compress_pdf(path,output/profile/relative.parent,
                    Settings(photo_reencode=lossy,verify_width=args.width))
                assert sha256(path)==digest,'Input changed during benchmark'
                # Portable report: no machine-specific absolute paths.
                row={k:v for k,v in result.items() if k not in ('source','output','report')}
                row.update(sample=str(relative),profile=profile)
                print(f'{i}/{len(files)} {relative} {profile}: {result["saved_percent"]:.2f}% smaller',flush=True)
            except Exception as exc:
                row={'sample':str(relative),'profile':profile,'error':str(exc)}
                print(f'{relative} {profile}: ERROR {exc}',flush=True)
            rows.append(row)
            (output/'results.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf-8')
    return int(any('error' in row for row in rows))


if __name__=='__main__':raise SystemExit(main())
