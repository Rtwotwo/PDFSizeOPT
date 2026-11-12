import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject,
                          NameObject, NumberObject)

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from pdfsizeopt_app.quality import choose_photo_encoding, photo_metrics
from pdfsizeopt_app.engine import Settings, compress_pdf, structure_info
from pdfsizeopt_app.engine import compact_vectors, collect_objects
from test_engine import fixture


def add_photo(writer, jpeg=False):
    rng=np.random.default_rng(109)
    y,x=np.mgrid[:512,:512]
    base=np.stack([50+x/4,50+y/4,70+(x+y)/6],axis=-1)
    pixels=np.clip(base+rng.normal(0,15,base.shape),0,255).astype(np.uint8)
    im=Image.fromarray(pixels)
    data=DecodedStreamObject();data.set_data(pixels.tobytes())
    data.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Image'),
        NameObject('/Width'):NumberObject(512),NameObject('/Height'):NumberObject(512),
        NameObject('/ColorSpace'):NameObject('/DeviceRGB'),NameObject('/BitsPerComponent'):NumberObject(8)})
    if jpeg:
        buf=io.BytesIO();im.save(buf,format='JPEG',quality=93,subsampling=0)
        from pypdf.generic import EncodedStreamObject
        data=EncodedStreamObject.initialize_from_dictionary({**data,NameObject('/Filter'):NameObject('/DCTDecode'),
                                                           '__streamdata__':buf.getvalue()})
    else:
        data=data.flate_encode()
    page=writer.pages[0]
    resources=page['/Resources']
    if '/XObject' not in resources:resources[NameObject('/XObject')]=DictionaryObject()
    resources['/XObject'][NameObject('/Photo')]=writer._add_object(data)
    contents=page.get_contents()
    old=contents.get_data() if contents is not None else b''
    commands=DecodedStreamObject();commands.set_data(old+b'\nq 100 0 0 100 240 140 cm /Photo Do Q\n')
    page[NameObject('/Contents')]=writer._add_object(commands)


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests')
        self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()

    def test_adaptive_quality_protects_native_noise_detail(self):
        im=Image.fromarray(np.random.default_rng(3).integers(0,256,(512,512,3),dtype=np.uint8))
        selected=choose_photo_encoding(im,96,im.width*im.height*6)
        self.assertIsNotNone(selected)
        data,metrics=selected
        self.assertGreater(metrics['quality'],96)
        self.assertGreaterEqual(metrics['psnr_db'],48)
        self.assertGreaterEqual(metrics['tile_p01_psnr_db'],42)
        self.assertGreaterEqual(metrics['tile_min_psnr_db'],40)
        with Image.open(io.BytesIO(data)) as decoded:self.assertEqual(decoded.size,im.size)

    def test_no_larger_jpeg_is_accepted(self):
        im=Image.fromarray(np.random.default_rng(3).integers(0,256,(256,256,3),dtype=np.uint8))
        self.assertIsNone(choose_photo_encoding(im,96,100))

    def test_grayscale_photo_keeps_resolution_and_quality(self):
        src=self.root/'gray.pdf';fixture(src)
        w=PdfWriter(clone_from=src);add_photo(w)
        obj=w.pages[0]['/Resources']['/XObject']['/Photo']
        import zlib
        rgb=np.frombuffer(obj.get_data(),dtype=np.uint8).reshape(512,512,3)
        gray=Image.fromarray(rgb).convert('L')
        obj[NameObject('/ColorSpace')]=NameObject('/DeviceGray')
        obj._data=zlib.compress(gray.tobytes());obj.decoded_self=None
        w.write(src);w.close()
        result=compress_pdf(src,self.root/'gray_out',Settings(lossless_polish=False,photo_reencode=True,verify_width=1000))
        self.assertEqual(len(result['reencoded_photos']),1)
        self.assertGreaterEqual(result['reencoded_photos'][0]['psnr_db'],48)
        im=PdfReader(result['output']).pages[0].images[0]
        self.assertEqual(im.image.size,(512,512))
        self.assertEqual(im.indirect_reference.get_object()['/ColorSpace'],'/DeviceGray')

    def test_masked_photo_retains_image_and_alpha_pixels(self):
        src=self.root/'masked.pdf';fixture(src)
        w=PdfWriter(clone_from=src);add_photo(w)
        obj=w.pages[0]['/Resources']['/XObject']['/Photo']
        alpha=DecodedStreamObject();alpha.set_data(bytes(range(256))*1024)
        alpha.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Image'),
            NameObject('/Width'):NumberObject(512),NameObject('/Height'):NumberObject(512),
            NameObject('/ColorSpace'):NameObject('/DeviceGray'),NameObject('/BitsPerComponent'):NumberObject(8)})
        obj[NameObject('/SMask')]=w._add_object(alpha.flate_encode())
        w.write(src);w.close()
        result=compress_pdf(src,self.root/'masked_out',Settings(lossless_polish=False,photo_reencode=True,verify_width=1000))
        self.assertFalse(result['reencoded_photos'])
        self.assertTrue(all(x['changed_pixels']==0 for x in result['verification']))

    def test_local_damage_cannot_hide_in_page_average(self):
        a=np.zeros((2048,2048,3),dtype=np.uint8);b=a.copy()
        b[128:192,128:192]=255
        m=photo_metrics(Image.fromarray(a),Image.fromarray(b))
        self.assertEqual(m['tile_min_psnr_db'],0)

    def test_indirect_annotations_are_supported(self):
        src=self.root/'annotations.pdf'
        w=PdfWriter();p=w.add_blank_page(width=360,height=240)
        p[NameObject('/Annots')]=w._add_object(ArrayObject([w._add_object(DictionaryObject({
            NameObject('/Type'):NameObject('/Annot'),NameObject('/Subtype'):NameObject('/Text'),
            NameObject('/Rect'):ArrayObject([NumberObject(x) for x in (20,20,30,30)])}))]))
        w.write(src);w.close()
        self.assertEqual(structure_info(src)['annotations'],[1])
        result=compress_pdf(src,self.root/'output',Settings(lossless_polish=False,verify_width=1000))
        self.assertEqual(structure_info(result['output'])['annotations'],[1])

    def test_photo_mode_still_rejects_changed_vectors(self):
        src=self.root/'mixed.pdf';fixture(src,touch_clip=True)
        w=PdfWriter(clone_from=src);add_photo(w);w.write(src);w.close()
        def defective_compactor(reader,level,cancel):
            count=compact_vectors(reader,level,cancel)
            for _,obj in collect_objects(reader):
                if hasattr(obj,'get') and obj.get('/Subtype')=='/Form' and '/Group' in obj:
                    import zlib
                    obj._data=zlib.compress(obj.get_data()+b'\n0 0 0 rg 200 210 2 2 re f\n')
                    obj[NameObject('/Filter')]=NameObject('/FlateDecode')
                    obj.decoded_self=None
            return count
        # A small vector defect must fail exact validation even when its page
        # PSNR would be hidden by a large photograph and the lossy threshold.
        with patch('pdfsizeopt_app.engine.compact_vectors',side_effect=defective_compactor):
            result=compress_pdf(src,self.root/'mixed_out',Settings(lossless_polish=False,photo_reencode=True,verify_width=2000))
        self.assertTrue(result['fallback_used'])
        self.assertEqual(result['inlined_forms'],0)
        self.assertEqual(len(result['reencoded_photos']),1)

    def test_existing_jpeg_is_not_reencoded(self):
        src=self.root/'jpeg.pdf';fixture(src)
        w=PdfWriter(clone_from=src);add_photo(w,jpeg=True);w.write(src);w.close()
        before=PdfReader(src).pages[0].images[0].indirect_reference.get_object()._data
        result=compress_pdf(src,self.root/'jpeg_out',Settings(lossless_polish=False,photo_reencode=True,verify_width=1000))
        after=PdfReader(result['output']).pages[0].images[0].indirect_reference.get_object()._data
        self.assertEqual(before,after)
        self.assertFalse(result['reencoded_photos'])

    def test_rejected_photo_keeps_lossless_savings(self):
        src=self.root/'fallback.pdf';fixture(src,touch_clip=True)
        w=PdfWriter(clone_from=src);add_photo(w);w.write(src);w.close()
        with patch('pdfsizeopt_app.engine.choose_photo_encoding',return_value=None):
            result=compress_pdf(src,self.root/'fallback_out',Settings(lossless_polish=False,photo_reencode=True,verify_width=1000))
        self.assertLess(result['output_bytes'],result['input_bytes'])
        self.assertFalse(result['reencoded_photos'])
        self.assertTrue(all(x['changed_pixels']==0 for x in result['verification']))


if __name__=='__main__':unittest.main()
