from pathlib import Path
import sys
import tempfile
import threading
import unittest
import zlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from pypdf import PdfWriter, PdfReader
from pypdf.generic import (NameObject, DictionaryObject, DecodedStreamObject,
    ArrayObject, NumberObject, FloatObject)
from pdfsizeopt_app.engine import (Settings, compact_vectors, rewrite, render_verify,
    compress_pdf, output_path, Cancelled, sha256, structure_info)


def fixture(path, touch_clip=False):
    w=PdfWriter()
    page=w.add_blank_page(width=360,height=240)
    state=DictionaryObject({NameObject('/CA'):FloatObject(.7),NameObject('/ca'):FloatObject(.7)})
    form=DecodedStreamObject()
    rectangle=b'0 0 80 80' if touch_clip else b'10 10 60 60'
    form.set_data(b'/alpha gs\n0.1 0.4 0.9 rg\n'+rectangle+b' re f\n')
    form.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),
        NameObject('/BBox'):ArrayObject([NumberObject(x) for x in (0,0,80,80)]),
        NameObject('/Matrix'):ArrayObject([NumberObject(x) for x in (1,0,0,1,5,6)]),
        NameObject('/Resources'):DictionaryObject({NameObject('/ExtGState'):DictionaryObject({NameObject('/alpha'):state})})})
    leaf=w._add_object(form)
    parent=DecodedStreamObject()
    parent.set_data(b'q\n1 0 0 1 10 20 cm /leaf Do\nQ\nq\n0.8 0.2 -0.2 0.8 120 20 cm /leaf Do\nQ\n')
    parent.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),
        NameObject('/BBox'):ArrayObject([NumberObject(x) for x in (0,0,360,240)]),
        NameObject('/Group'):DictionaryObject({NameObject('/S'):NameObject('/Transparency')}),
        NameObject('/Resources'):DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/leaf'):leaf})})})
    parent_ref=w._add_object(parent)
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/parent'):parent_ref})})
    content=DecodedStreamObject();content.set_data(b'/parent Do\n')
    page[NameObject('/Contents')]=w._add_object(content)
    w.add_outline_item('测试书签',0)
    w.add_metadata({'/Title':'路径与裁剪测试'})
    unused=DecodedStreamObject();unused.set_data(b'x'*30000)
    w._add_object(unused)  # Recoverable unused data makes both candidates smaller.
    with Path(path).open('wb') as f:w.write(f)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests')
        self.root=Path(self.temp.name)
        self.pdf=self.root/'中文 空格 测试.pdf';fixture(self.pdf)
    def tearDown(self):self.temp.cleanup()

    def test_default_profile(self):
        s=Settings();s.validate()
        self.assertEqual(s.verify_width,8000)
        self.assertTrue(s.photo_reencode)
        self.assertEqual(s.jpeg_quality,96)
        self.assertEqual(s.suffix,'')

    def test_conservative_transform_clip_and_outline_preserved(self):
        target=self.root/'compact.pdf'
        r=rewrite(self.pdf,target,Settings(lossless_polish=False),False)
        self.assertEqual(r['inlined_forms'],0)
        self.assertEqual(structure_info(self.pdf),structure_info(target))
        ok,rows=render_verify(self.pdf,target,2000,False,threading.Event(),lambda *a,**k:None)
        self.assertTrue(ok,rows)
        self.assertTrue(PdfReader(target).outline)
        self.assertEqual(PdfReader(target).metadata.title,'路径与裁剪测试')

    def test_output_names_collisions_and_source_protection(self):
        s=Settings()
        a=output_path(self.pdf,None,s)
        self.assertEqual(a.parent.name,'compressed')
        self.assertEqual(a.name,self.pdf.name)
        a.write_bytes(b'existing')
        b=output_path(self.pdf,None,s)
        self.assertNotEqual(a,b)
        self.assertIsNone(output_path(self.pdf,None,Settings(collision='skip')))
        with self.assertRaises(ValueError):output_path(self.pdf,self.root,s)

    def test_cancel_does_not_create_output(self):
        event=threading.Event();event.set()
        output=self.root/'cancelled'
        with self.assertRaises(Cancelled):compress_pdf(self.pdf,output,Settings(lossless_polish=False),event)
        self.assertFalse(any(output.glob('*.pdf')))

    def test_original_untouched_atomic_output(self):
        before=sha256(self.pdf)
        r=compress_pdf(self.pdf,self.root/'result',Settings(lossless_polish=False,verify_width=2000))
        self.assertEqual(before,sha256(self.pdf))
        self.assertEqual(Path(r['output']).name,self.pdf.name)
        self.assertTrue(Path(r['output']).is_file())
        self.assertFalse(list((self.root/'result').glob('.pdfsizeopt-*')))

    def test_visual_change_is_rejected(self):
        w=PdfWriter();w.add_blank_page(width=360,height=240)
        other=self.root/'wrong.pdf'
        with other.open('wb') as f:w.write(f)
        ok,rows=render_verify(self.pdf,other,1000,False,threading.Event(),lambda *a,**k:None)
        self.assertFalse(ok)
        self.assertGreater(rows[0]['changed_pixels'],0)

    def test_clip_edge_rendering_difference_is_rejected(self):
        # PDFium rasterizes a form BBox and an explicit rotated clipping path
        # differently at their common edge. The verification gate must catch it.
        fixture(self.pdf,touch_clip=True)
        target=self.root/'clip.pdf'
        detail=rewrite(self.pdf,target,Settings(lossless_polish=False),True)
        self.assertEqual(detail['inlined_forms'],2)
        ok,rows=render_verify(self.pdf,target,2000,False,threading.Event(),lambda *a,**k:None)
        self.assertFalse(ok)
        self.assertGreater(rows[0]['changed_pixels'],0)
        result=compress_pdf(self.pdf,self.root/'safe',Settings(lossless_polish=False,verify_width=2000))
        self.assertTrue(result['fallback_used'])
        self.assertFalse(result['identical_original_copy'])
        self.assertEqual(result['inlined_forms'],0)
        self.assertTrue(all(v['changed_pixels']==0 for v in result['verification']))

    def test_optional_photo_compression_preserves_dimensions(self):
        w=PdfWriter();page=w.add_blank_page(width=512,height=512)
        rng=np.random.default_rng(27)
        # Smooth photographic-like color variation plus fine sensor noise.
        y,x=np.mgrid[:512,:512]
        base=np.stack([50+x/4,50+y/4,70+(x+y)/6],axis=-1)
        pixels=np.clip(base+rng.normal(0,4,base.shape),0,255).astype(np.uint8)
        bitmap=DecodedStreamObject()
        bitmap.set_data(pixels.tobytes())
        bitmap.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Image'),
            NameObject('/Width'):NumberObject(512),NameObject('/Height'):NumberObject(512),
            NameObject('/ColorSpace'):NameObject('/DeviceRGB'),NameObject('/BitsPerComponent'):NumberObject(8)})
        imref=w._add_object(bitmap.flate_encode())
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/Photo'):imref})})
        content=DecodedStreamObject();content.set_data(b'q 512 0 0 512 0 0 cm /Photo Do Q')
        page[NameObject('/Contents')]=w._add_object(content)
        source=self.root/'photo.pdf'
        with source.open('wb') as handle:w.write(handle)
        result=compress_pdf(source,self.root/'photo_result',Settings(lossless_polish=False,photo_reencode=True,verify_width=1000))
        self.assertEqual(len(result['reencoded_photos']),1)
        self.assertEqual(result['reencoded_photos'][0]['width'],512)
        self.assertEqual(result['reencoded_photos'][0]['height'],512)
        self.assertLess(result['output_bytes'],result['input_bytes'])
        self.assertTrue(all(v['psnr_db']>=40 for v in result['verification']))
        strict=compress_pdf(source,self.root/'strict_result',Settings(lossless_polish=False,photo_reencode=False,verify_width=1000))
        self.assertFalse(strict['reencoded_photos'])
        self.assertTrue(strict['identical_original_copy'] or all(v['changed_pixels']==0 for v in strict['verification']))

if __name__=='__main__':unittest.main()
