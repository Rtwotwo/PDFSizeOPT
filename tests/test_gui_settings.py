"""Preference persistence without opening a desktop window."""
from dataclasses import asdict
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from pdfsizeopt_app.engine import Settings
from pdfsizeopt_app.gui import App


class Value:
    def __init__(self,value):self.value=value
    def get(self):return self.value
    def set(self,value):self.value=value


def settings_view(path):
    app=App.__new__(App)
    app.settings_file=path
    app.options={key:Value(value) for key,value in asdict(Settings()).items()}
    app.output_dir=Value('')
    app.output_mode=Value('source')
    app.collision_label=Value('自动编号，保留两份')
    app.verify_note=Value('')
    app.status=Value('')
    app.busy=False
    for key in ('adaptive_mode','strict_mode','jpeg_quality_box','verify_check'):
        setattr(app,key,Mock())
    return app


class PreferenceTests(unittest.TestCase):
    def test_strict_selection_survives_restart_until_defaults_restored(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json'
            app=settings_view(path)
            app._load_settings()
            self.assertTrue(app._settings().photo_reencode)
            self.assertEqual(app._settings().jpeg_quality,96)
            app.options['photo_reencode'].set(False)
            app.options['verify_visual'].set(False)
            app._compression_mode_changed()
            self.assertTrue(app._settings().verify_visual)
            restarted=settings_view(path)
            restarted._load_settings()
            self.assertFalse(restarted._settings().photo_reencode)
            restarted.options['jpeg_quality'].set(100)
            restarted.reset_defaults()
            again=settings_view(path)
            again._load_settings()
            self.assertTrue(again._settings().photo_reencode)
            self.assertEqual(again._settings().jpeg_quality,96)


if __name__=='__main__':unittest.main()
