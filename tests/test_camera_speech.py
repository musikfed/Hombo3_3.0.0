"""No hardware/no network tests for opt-in WIFICAM voice path."""
import importlib
import io
import sys
import types
import unittest
import wave


config = types.ModuleType("backend.app.config")
config.settings = types.SimpleNamespace(
    camera_voice_enabled=True,
    camera_voice_access_token="manual-operator-key-123456789",
    camera_audio_enabled=True,
    camera_stt_url="http://127.0.0.1:9999/v1/audio/transcriptions",
)
sys.modules["backend.app.config"] = config
camera = types.ModuleType("backend.app.camera")
camera.camera_hub = object()
sys.modules["backend.app.camera"] = camera
sys.modules["httpx"] = types.ModuleType("httpx")
speech = importlib.import_module("backend.app.camera_speech")


class CameraSpeechTests(unittest.TestCase):
    def test_pcm_to_wav_valid_length_and_sample_rate(self):
        payload = bytes(range(256)) * 40
        blob = speech.as_wav(payload)
        with wave.open(io.BytesIO(blob), "rb") as wav:
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getsampwidth(), 2)
            self.assertEqual(wav.getframerate(), 16000)
            self.assertEqual(wav.getnframes(), len(payload) // 2)
            self.assertEqual(wav.readframes(20000), payload)

    def test_empty_or_unbounded_pcm_is_rejected(self):
        for payload in (b"", b"x" * 7, b"x" * 640002):
            with self.assertRaises(RuntimeError):
                speech.as_wav(payload)

    def test_operator_token_required(self):
        speech.require_operator_token("manual-operator-key-123456789")
        with self.assertRaises(PermissionError):
            speech.require_operator_token("wrong")
        config.settings.camera_voice_enabled = False
        with self.assertRaises(RuntimeError):
            speech.require_operator_token("manual-operator-key-123456789")


if __name__ == "__main__":
    unittest.main()
