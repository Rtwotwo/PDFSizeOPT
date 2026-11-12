"""Conservative vector compaction and atomic, validated PDF output.

Default settings never downsample or recompress photographic JPEG streams.
Simple non-transparency Form XObjects are inlined without rounding coordinates.
Every candidate must pass structural checks and optional whole-page rendering.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Callable
import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import zlib

import numpy as np
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, IndirectObject, NameObject
import pypdf.generic._base as pdf_base
import pypdfium2 as pdfium
from .quality import choose_photo_encoding

pdf_base.FLOAT_WRITE_PRECISION = 15
logging.getLogger("pypdf").setLevel(logging.ERROR)
APP_ROOT = Path(__file__).resolve().parents[2]
_RENDER_LOCK = threading.Lock()  # PDFium is not thread-safe.
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Cancelled(Exception):
    pass


@dataclass
class Settings:
    compact_vectors: bool = True
    deduplicate: bool = True
    lossless_polish: bool = True
    compression_level: int = 9
    verify_visual: bool = True
    verify_width: int = 8000
    photo_reencode: bool = False
    jpeg_quality: int = 96
    collision: str = "rename"
    suffix: str = ""

    def validate(self):
        if not 1 <= self.compression_level <= 9:
            raise ValueError("无损压缩级别必须为 1–9。")
        if not 1000 <= self.verify_width <= 12000:
            raise ValueError("校验长边必须为 1000–12000 像素。")
        if not 90 <= self.jpeg_quality <= 100:
            raise ValueError("JPEG 质量必须为 90–100。")
        if self.collision not in ("rename", "skip", "replace"):
            raise ValueError("无效的同名文件处理方式。")
        if any(c in self.suffix for c in '\\/:*?"<>|'):
            raise ValueError("文件名后缀包含无效字符。")


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled("已取消。")


def collect_objects(reader):
    """Include both regular and object-stream xrefs, without scanning file bytes."""
    refs = {(num, gen) for gen, entries in reader.xref.items() for num in entries if num}
    refs.update((num, 0) for num in reader.xref_objStm)
    for num, gen in sorted(refs):
        obj = reader.get_object(IndirectObject(num, gen, reader))
        yield num, obj


def pdf_reader(path):
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise ValueError("暂不处理加密 PDF，请先另存为未加密副本。")
    if not reader.pages:
        raise ValueError("PDF 没有页面。")
    # Signed documents cannot keep a valid signature after rewriting.
    root = reader.trailer['/Root']
    if root.get('/Perms'):
        raise ValueError("此 PDF 带有认证签名，压缩会破坏签名，请使用未签名副本。")
    fields = reader.get_fields() if root.get('/AcroForm') else None
    if fields and any(f.get('/FT') == '/Sig' for f in fields.values()):
        raise ValueError("此 PDF 包含签名字段，请使用未签名副本。")
    return reader


def _serialized(obj):
    stream = io.BytesIO()
    obj.write_to_stream(stream)
    return stream.getvalue()


def _state_signature(obj):
    obj = obj.get_object()
    return tuple(sorted((str(k), _serialized(v.get_object())) for k, v in obj.items()))


def _safe_path_content(data):
    # Conservative guard against substitutions inside strings, inline images,
    # comments, text blocks, or marked-content dictionaries.
    return not any(s in data for s in (b'(', b'<', b'%', b'BI', b'BT', b'BDC', b'BMC'))


def compact_vectors(reader, level=9, cancel=None):
    forms = {num: obj for num, obj in collect_objects(reader)
             if isinstance(obj, DictionaryObject) and obj.get('/Subtype') == '/Form'}
    leaves = {}
    allowed = {'/Type', '/Subtype', '/FormType', '/BBox', '/Matrix', '/Resources',
               '/Filter', '/DecodeParms', '/Length'}
    name_pattern = re.compile(rb'/[^\s\[\]()<>/%]+')
    for index, (number, obj) in enumerate(forms.items()):
        if index % 256 == 0:
            check_cancel(cancel)
        if set(obj) - allowed or '/BBox' not in obj:
            continue  # Transparency groups and structural tagging stay intact.
        res = obj.get('/Resources', DictionaryObject()).get_object()
        if set(res) - {'/ExtGState'}:
            continue
        data = obj.get_data()
        if not _safe_path_content(data):
            continue
        states = res.get('/ExtGState', DictionaryObject()).get_object()
        if set(name_pattern.findall(data)) - {str(k).encode() for k in states}:
            continue
        leaves[number] = (obj, states, data)

    do_pattern = re.compile(rb'(/[^\s\[\]()<>/%]+)\s+Do\b')
    count = 0
    for number, obj in forms.items():
        check_cancel(cancel)
        if number in leaves:
            continue
        resources = obj.get('/Resources', DictionaryObject()).get_object()
        xobjects = resources.get('/XObject', DictionaryObject()).get_object()
        eligible = {str(k).encode(): v.idnum for k, v in xobjects.items()
                    if isinstance(v, IndirectObject) and v.idnum in leaves}
        if not eligible:
            continue
        original = obj.get_data()
        if not _safe_path_content(original):
            continue
        resources = DictionaryObject(dict(resources))
        states = DictionaryObject(dict(resources.get('/ExtGState', DictionaryObject()).get_object()))
        known = {_state_signature(v): k for k, v in states.items()}
        expansions = {}
        for name, leaf_number in eligible.items():
            leaf, leaf_states, data = leaves[leaf_number]
            remap = {}
            for old_name, value in leaf_states.items():
                signature = _state_signature(value)
                new_name = known.get(signature)
                if new_name is None:
                    n = len(known)
                    new_name = NameObject('/compactGS' + str(n))
                    while new_name in states:
                        n += 1
                        new_name = NameObject('/compactGS' + str(n))
                    states[new_name] = value
                    known[signature] = new_name
                remap[str(old_name).encode()] = str(new_name).encode()
            data = name_pattern.sub(lambda m: remap[m.group(0)], data)
            prefix = b'q\n'
            if '/Matrix' in leaf:
                prefix += b' '.join(str(x).encode() for x in leaf['/Matrix']) + b' cm\n'
            x0, y0, x1, y1 = (Decimal(str(x)) for x in leaf['/BBox'])
            prefix += b' '.join(str(x).encode() for x in (x0, y0, x1-x0, y1-y0)) + b' re W n\n'
            expansions[name] = prefix + data + b'\nQ\n'
        used = set()
        def expand(match):
            nonlocal count
            name = match.group(1)
            if name not in expansions:
                return match.group(0)
            used.add(name)
            count += 1
            return expansions[name]
        result = do_pattern.sub(expand, original)
        if not used:
            continue
        resources[NameObject('/XObject')] = DictionaryObject(
            {k: v for k, v in xobjects.items() if str(k).encode() not in used})
        resources[NameObject('/ExtGState')] = states
        obj[NameObject('/Resources')] = resources
        obj[NameObject('/Filter')] = NameObject('/FlateDecode')
        obj.pop('/DecodeParms', None)
        obj._data = zlib.compress(result, level)
        obj.decoded_self = None
    return count


def photo_reencode(writer, quality, cancel=None):
    """Adaptive high-quality JPEG, never downsampling or reencoding old JPEGs."""
    records, visited = [], set()
    for page in writer.pages:
        check_cancel(cancel)
        for im_file in page.images:
            ref = im_file.indirect_reference
            if ref is None or ref.idnum in visited:
                continue
            visited.add(ref.idnum)
            obj = ref.get_object()
            if (obj.get('/BitsPerComponent') != 8
                or str(obj.get('/ColorSpace')) not in ('/DeviceRGB', '/DeviceGray')
                or any(k in obj for k in ('/SMask', '/Mask', '/Decode'))
                or any(f in str(obj.get('/Filter')) for f in ('DCTDecode', 'JPXDecode'))
                or int(obj['/Width']) * int(obj['/Height']) < 200000):
                continue
            im = im_file.image
            thumb = im.copy()
            thumb.thumbnail((192, 192))
            if ((str(obj.get('/ColorSpace')) != '/DeviceGray' and thumb.getcolors(1024) is not None)
                    or thumb.convert('L').entropy() < 5.0):
                continue
            # Exclude flat-background diagrams even when antialiasing introduces
            # many colors. This remains a conservative heuristic, not a classifier.
            quantized = np.asarray(thumb.convert('RGB'), dtype=np.uint8) // 16
            color_codes = (quantized[:,:,0].astype(np.int32)*256
                           + quantized[:,:,1].astype(np.int32)*16 + quantized[:,:,2])
            if np.bincount(color_codes.ravel(), minlength=4096).max()/color_codes.size > .4:
                continue
            selected = choose_photo_encoding(im, quality, len(obj._data), cancel)
            check_cancel(cancel)
            if selected is None:
                continue
            data, metrics = selected
            # Install exactly the bytes checked above, preserving the image's
            # dictionary (including interpolation), dimensions, and color space.
            obj[NameObject('/Filter')] = NameObject('/DCTDecode')
            obj.pop('/DecodeParms', None)
            obj._data = data
            obj.decoded_self = None
            records.append({'width': im.width, 'height': im.height,
                'requested_quality': quality, 'object': ref.idnum, **metrics})
    return records


def rewrite(source, dest, settings, compact=True, cancel=None):
    reader = pdf_reader(source)
    count = compact_vectors(reader, settings.compression_level, cancel) if compact else 0
    # Clone the catalog as well as pages: links, outlines, and metadata survive.
    writer = PdfWriter(clone_from=reader)
    photos = photo_reencode(writer, settings.jpeg_quality, cancel) if settings.photo_reencode else []
    if settings.deduplicate:
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    check_cancel(cancel)
    with Path(dest).open('wb') as handle:
        writer.write(handle)
    writer.close()
    reader.close()
    return {'inlined_forms': count, 'reencoded_photos': photos}


def polish(source, output, log, cancel, emit):
    engine = APP_ROOT / 'bin' / 'pdfsizeopt.exe'
    if not engine.exists():
        emit('progress', message='无损引擎未安装，使用内置压缩结果。')
        return False
    args = [str(engine), '--use-pngout=no', '--use-jbig2=no',
            '--do-optimize-fonts=no', '--do-unify-fonts=no', '--do-regenerate-all-fonts=no',
            str(source), str(output)]
    env = dict(os.environ)
    env['TEMP'] = env['TMP'] = str(Path(log).parent)
    with Path(log).open('wb') as handle:
        process = subprocess.Popen(args, stdout=handle, stderr=subprocess.STDOUT,
            cwd=Path(log).parent, env=env, creationflags=CREATE_NO_WINDOW)
        while process.poll() is None:
            if cancel.is_set():
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
                process.wait()
                raise Cancelled('已取消。')
            cancel.wait(.15)
    if process.returncode or not Path(output).is_file():
        emit('progress', message='附加优化未完成，继续检查内置压缩结果。')
        return False
    return True


def structure_info(path):
    reader = pdf_reader(path)
    boxes = [(list(p.mediabox), list(p.cropbox), p.rotation) for p in reader.pages]
    # Preserve navigation, form fields, embedded files and page annotations.
    annotations = []
    for page in reader.pages:
        annots = page.get('/Annots', [])
        if isinstance(annots, IndirectObject):
            annots = annots.get_object()
        annotations.append(len(annots) if isinstance(annots, (list, tuple)) else 0)
    catalog = reader.trailer['/Root']
    features = {k: k in catalog for k in ('/Outlines','/AcroForm','/Names','/StructTreeRoot','/OCProperties')}
    reader.close()
    return {'boxes': boxes, 'annotations': annotations, 'features': features}


def render_verify(original, candidate, width, lossy, cancel, emit):
    rows=[]
    with _RENDER_LOCK:
        before, after = pdfium.PdfDocument(original), pdfium.PdfDocument(candidate)
        try:
            if len(before) != len(after):
                return False, []
            # Both ordinary reading scale and an enlarged detail scale.
            for i in range(len(before)):
                for resolution in sorted(set((min(2000, width), width))):
                    check_cancel(cancel)
                    emit('progress', message=f'校验第 {i+1}/{len(before)} 页 · {resolution} px')
                    pa, pb = before[i], after[i]
                    if pa.get_size() != pb.get_size():
                        pa.close(); pb.close()
                        return False, rows
                    scale = resolution / max(pa.get_size())
                    ba = pa.render(scale=scale)
                    bb = pb.render(scale=scale)
                    try:
                        aa, ab = ba.to_numpy(), bb.to_numpy()
                        if aa.shape != ab.shape:
                            return False, rows
                        changed, error, pixels = 0, 0, aa.shape[0]*aa.shape[1]
                        for y in range(0, aa.shape[0], 128):
                            check_cancel(cancel)
                            left,right = aa[y:y+128,:,:3],ab[y:y+128,:,:3]
                            changed += int(np.any(left!=right,axis=2).sum())
                            if lossy:
                                d=left.astype(np.int32)-right.astype(np.int32)
                                error += int((d*d).sum())
                        mse=error/(pixels*3)
                        psnr=float('inf') if mse==0 else 10*np.log10(255**2/mse)
                        row={'page':i+1,'resolution':resolution,'changed_pixels':changed}
                        if lossy:
                            row['psnr_db']=round(float(psnr),3) if mse else None
                        rows.append(row)
                        if (not lossy and changed) or (lossy and psnr < 40):
                            return False, rows
                    finally:
                        ba.close(); bb.close(); pa.close(); pb.close()
        finally:
            before.close(); after.close()
    return True, rows


def output_path(source, directory, settings):
    source=Path(source).resolve()
    folder=Path(directory).expanduser().resolve() if directory else source.parent/'压缩结果'
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/(source.stem+settings.suffix+source.suffix)
    if target.resolve()==source:
        raise ValueError('输出与原文件完全相同。请选择其他输出目录或填写文件名后缀。')
    if target.exists():
        if settings.collision=='skip':
            return None
        if settings.collision=='rename':
            n=2
            while target.exists():
                target=folder/f'{source.stem}{settings.suffix} ({n}){source.suffix}'
                n+=1
    return target


def compress_pdf(source, directory=None, settings=None, cancel=None, emit=None):
    settings=settings or Settings()
    settings.validate()
    cancel=cancel or threading.Event()
    emit=emit or (lambda *args,**kw:None)
    source=Path(source).expanduser().resolve(strict=True)
    if source.suffix.lower()!='.pdf':
        raise ValueError('请选择 PDF 文件。')
    # Validate before creating output folders.
    original_structure=structure_info(source)
    target=output_path(source,directory,settings)
    if target is None:
        return {'status':'skipped','source':str(source),'message':'同名文件已存在，已跳过。'}
    started=time.monotonic()
    input_hash=sha256(source)
    total=source.stat().st_size
    emit('progress',message='分析矢量对象和图片资源…')
    logs=APP_ROOT/'logs'
    logs.mkdir(exist_ok=True)
    stamp=time.strftime('%Y%m%d_%H%M%S')+'_'+input_hash[:8]+'_'+str(time.time_ns()%1000000)
    details={}
    with tempfile.TemporaryDirectory(prefix='.pdfsizeopt-',dir=target.parent) as temp:
        work=Path(temp)
        original=work/'original.pdf'
        shutil.copyfile(source,original)
        check_cancel(cancel)
        if sha256(original)!=input_hash:
            raise ValueError('读取过程中原文件发生变化，请重试。')
        base=work/'compact.pdf'
        # Validate all vector/object transformations without a lossy tolerance.
        # Photo error must never hide a changed label, line, or clipping edge.
        lossless_settings=Settings(**{**asdict(settings),'photo_reencode':False})
        details=rewrite(original,base,lossless_settings,settings.compact_vectors,cancel)
        candidates=[base]
        if settings.lossless_polish:
            emit('progress',message='压缩重复资源及 PDF 对象结构…')
            polished=work/'polished.pdf'
            if polish(base,polished,work/'engine.log',cancel,emit):
                candidates.append(polished)
            if (work/'engine.log').exists():
                shutil.copyfile(work/'engine.log',logs/(stamp+'_engine.log'))
        candidates.sort(key=lambda p:p.stat().st_size)
        chosen=original
        checks=[]
        fallback=False
        accepted_details=details
        for candidate in candidates:
            check_cancel(cancel)
            if candidate.stat().st_size>=total:
                continue
            if structure_info(candidate)!=original_structure:
                fallback=True
                continue
            if settings.verify_visual:
                passed,checks=render_verify(original,candidate,settings.verify_width,
                    False,cancel,emit)
                if not passed:
                    fallback=True
                    emit('progress',message='检测到画面差异，尝试更保守的结果…')
                    continue
            chosen=candidate
            break
        if chosen==original and settings.compact_vectors and fallback:
            conservative=work/'conservative.pdf'
            conservative_settings=Settings(**{**asdict(settings),'photo_reencode':False})
            conservative_details=rewrite(original,conservative,conservative_settings,False,cancel)
            if conservative.stat().st_size<total and structure_info(conservative)==original_structure:
                passed,checks=render_verify(original,conservative,settings.verify_width,False,cancel,emit) if settings.verify_visual else (True,[])
                if passed:
                    chosen=conservative
                    accepted_details=conservative_details
        if chosen==original:
            accepted_details={'inlined_forms':0,'reencoded_photos':[]}
            checks=[]
        if settings.photo_reencode:
            emit('progress',message='逐张检查照片细节，自动提高必要的 JPEG 质量…')
            photo_base=work/'photos.pdf'
            photo_details=rewrite(chosen,photo_base,settings,False,cancel)
            if photo_details['reencoded_photos']:
                photo_candidate=photo_base
                if settings.lossless_polish:
                    photo_polished=work/'photos-polished.pdf'
                    if polish(photo_base,photo_polished,work/'photo-engine.log',cancel,emit):
                        if (photo_polished.stat().st_size<photo_base.stat().st_size
                                and structure_info(photo_polished)==original_structure):
                            exact,_=render_verify(photo_base,photo_polished,settings.verify_width,
                                False,cancel,emit) if settings.verify_visual else (True,[])
                            if exact:
                                photo_candidate=photo_polished
                            else:
                                fallback=True
                    if (work/'photo-engine.log').exists():
                        shutil.copyfile(work/'photo-engine.log',logs/(stamp+'_photo_engine.log'))
                if (photo_candidate.stat().st_size<chosen.stat().st_size
                        and structure_info(photo_candidate)==original_structure):
                    passed,photo_checks=render_verify(original,photo_candidate,settings.verify_width,
                        True,cancel,emit) if settings.verify_visual else (True,[])
                    if passed:
                        chosen=photo_candidate
                        accepted_details={**accepted_details,'reencoded_photos':photo_details['reencoded_photos']}
                        checks=photo_checks
                    else:
                        fallback=True
                        emit('progress',message='照片候选未通过画面检查，保留已验证的无损结果。')
        check_cancel(cancel)
        if sha256(source)!=input_hash:
            raise ValueError('处理过程中原文件发生变化，已停止输出。')
        if chosen==original:
            accepted_details={'inlined_forms':0,'reencoded_photos':[]}
            checks=[]
        size=chosen.stat().st_size
        result={'status':'done','source':str(source),'output':str(target),
            'input_bytes':total,'output_bytes':size,'saved_percent':round(100*(1-size/total),3),
            'settings':asdict(settings),'input_sha256':input_hash,'output_sha256':sha256(chosen),
            'seconds':round(time.monotonic()-started,2),'verification':checks,
            'identical_original_copy':chosen==original,'fallback_used':fallback,**accepted_details}
        staged=work/'ready.pdf'
        shutil.copyfile(chosen,staged)
        # Save the report before publishing. No half-written final PDFs.
        report_path=logs/(stamp+'.json')
        report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        check_cancel(cancel)
        if settings.collision=='replace':
            os.replace(staged,target)
        else:
            # Windows rename is atomic and refuses an existing destination.
            try:
                os.rename(staged,target)
            except FileExistsError:
                raise ValueError('输出文件刚被其他程序创建，请重试或换一个输出目录。')
        result['report']=str(report_path)
    return result
