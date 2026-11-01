"""PTZ calibration and hardware-independent ONVIF zoom tests.

Only camera.py is imported; external cv2/onvif/database are stubbed.
"""
from __future__ import annotations
import asyncio
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest


class Settings:
    camera_pan_invert = False
    camera_tilt_invert = False
    camera_onvif_host = "127.0.0.1"
    camera_onvif_port = 80
    camera_username = ""
    camera_password = ""
    camera_rtsp_url = ""
    head_pan_range_deg = 300.0
    head_ptz_step_deg = 18.0


def camera_module(temp):
    pkg = types.ModuleType("backend.app.config")
    pkg.settings = Settings()
    pkg.settings.root_dir = Path(temp)
    sys.modules["backend.app.config"] = pkg
    db = types.ModuleType("backend.app.database")
    db.log_event = lambda *a, **kw: None
    sys.modules["backend.app.database"] = db
    sys.modules["cv2"] = types.ModuleType("cv2")
    sys.modules.pop("backend.app.camera", None)
    return importlib.import_module("backend.app.camera")


class FakeRequest:
    pass


class FakePTZ:
    def __init__(self):
        self.moves = []
        self.stops = []
        self.fail_zoom = False

    def create_type(self, kind):
        return FakeRequest()

    def ContinuousMove(self, request):
        if self.fail_zoom and "Zoom" in request.Velocity:
            raise RuntimeError("ZoomUnsupported")
        self.moves.append(request.Velocity)

    def Stop(self, request):
        self.stops.append((request.PanTilt, request.Zoom))


class FakeImaging:
    def __init__(self):
        self.moves = []
        self.stops = 0
        self.auto = []
        self.fail_motion = False

    def create_type(self, name):
        return FakeRequest()

    def Move(self, request):
        if self.fail_motion:
            raise RuntimeError("FixedFocus")
        self.moves.append(request.Focus["Continuous"]["Speed"])

    def Stop(self, request):
        self.stops += 1

    def SetImagingSettings(self, request):
        self.auto.append((request.ImagingSettings, request.ForcePersistence))


class PtzTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.mod = camera_module(self.temp.name)
        self.cam = self.mod.CameraHub()
        self.ptz = FakePTZ()
        self.cam._ptz_service = self.ptz
        self.cam._ptz_profile_token = "profile"

    def tearDown(self):
        self.temp.cleanup()

    def test_reverse_both_axes_persist_and_semantic_position(self):
        values = self.cam.set_ptz_calibration(True, True)
        self.assertEqual(values, {"pan_invert": True, "tilt_invert": True})
        self.assertEqual(json.loads((Path(self.temp.name)/"data/camera-ptz-calibration.json").read_text()), values)
        asyncio.run(self.cam.ptz_move(-.5, .5))
        self.assertEqual(self.ptz.moves[-1]["PanTilt"], {"x": .5, "y": -.5})
        self.assertEqual(self.ptz.stops[-1], (True, False))
        self.assertLess(self.cam._head_pan_deg, 0)  # semantic LEFT remains left
        again = self.mod.CameraHub()
        self.assertTrue(again._pan_invert)
        self.assertTrue(again._tilt_invert)

    def test_zoom_sent_and_motor_stop(self):
        asyncio.run(self.cam.ptz_move(0, 0, .4))
        self.assertEqual(self.ptz.moves[-1], {"Zoom": {"x": .4}})
        self.assertEqual(self.ptz.stops[-1], (False, True))
        self.assertTrue(self.cam._optical_zoom_supported)

    def test_unsupported_optical_zoom_reports_failure_and_stops(self):
        self.ptz.fail_zoom = True
        with self.assertRaisesRegex(RuntimeError, "ZoomUnsupported"):
            asyncio.run(self.cam.ptz_move(0, 0, .4))
        self.assertFalse(self.cam._optical_zoom_supported)
        self.assertEqual(self.ptz.stops[-1], (False, True))

    def test_focus_pulse_near_far_and_stop(self):
        imaging = FakeImaging()
        self.cam._imaging_service = imaging
        self.cam._video_source_token = "src"
        asyncio.run(self.cam.focus_step("near"))
        asyncio.run(self.cam.focus_step("far"))
        self.assertEqual(imaging.moves, [-0.35, 0.35])
        self.assertEqual(imaging.stops, 2)
        self.assertTrue(self.cam._manual_focus_supported)

    def test_fixed_focus_rejected_and_stopped(self):
        imaging = FakeImaging()
        imaging.fail_motion = True
        self.cam._imaging_service = imaging
        self.cam._video_source_token = "src"
        with self.assertRaisesRegex(RuntimeError, "FixedFocus"):
            asyncio.run(self.cam.focus_step("near"))
        self.assertEqual(imaging.stops, 1)
        self.assertFalse(self.cam._manual_focus_supported)

    def test_autofocus_is_not_persisted_to_flash(self):
        imaging = FakeImaging()
        self.cam._imaging_service = imaging
        self.cam._video_source_token = "src"
        result = asyncio.run(self.cam.autofocus())
        self.assertTrue(result["ok"])
        self.assertEqual(imaging.auto, [
            ({"Focus": {"AutoFocusMode": "AUTO"}}, False),
        ])


if __name__ == "__main__":
    unittest.main()
