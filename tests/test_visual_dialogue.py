"""Hardware-free tests: no Ollama, camera, microphone or robot is contacted."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock

from backend.app.visual_memory import VisualMemory
from backend.app.visual_dialogue import VisualDialogue, OllamaGateway, _plan


class MemoryTests(unittest.TestCase):
    def test_confirmed_metadata_and_private_optional_jpeg(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            memory = VisualMemory(folder / "state.sqlite3", folder / "images")
            self.assertEqual((folder / "state.sqlite3").stat().st_mode & 0o777, 0o600)
            saved = memory.remember("  датчик  ", "  пользователь объяснил, что это датчик ", [],
                                    jpeg=b"\xff\xd8\xff", save_image=False)
            self.assertEqual(saved["label"], "датчик")
            self.assertEqual(saved["image_saved"], False)
            self.assertFalse((folder / "images").exists())
            self.assertEqual(len(memory.list()), 1)
            image = memory.remember("реле", "подтверждено", [],
                                    jpeg=b"\xff\xd8\xff", save_image=True)
            self.assertEqual((folder / "images" / (image["id"] + ".jpg")).read_bytes(), b"\xff\xd8\xff")
            self.assertEqual((folder / "images" / (image["id"] + ".jpg")).stat().st_mode & 0o777, 0o600)
            self.assertTrue(memory.delete(image["id"]))
            self.assertFalse((folder / "images" / (image["id"] + ".jpg")).exists())
            with self.assertRaises(ValueError):
                memory.delete("../../etc/passwd")
            self.assertEqual(len(memory.list()), 1)
            self.assertTrue(memory.delete(saved["id"]))

    def test_malformed_image_rejected_and_default_no_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            memory = VisualMemory(Path(d) / "m.sqlite3", Path(d) / "frames")
            with self.assertRaises(ValueError):
                memory.remember("relay", "test", [], jpeg=b"junk", save_image=True)
            with self.assertRaises(ValueError):
                memory.remember("", "test", [], save_image=False)
            self.assertEqual(memory.list(), [])


class FakeGateway:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []
    async def chat(self, model, messages, **kwargs):
        self.calls.append({"model": model, "messages": messages, **kwargs})
        return next(self.outputs)


class DialogueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.memory = VisualMemory(Path(self.temp.name) / "m.sqlite3", Path(self.temp.name) / "images")
        self.frame = AsyncMock(return_value=b"\xff\xd8\xffmock")
        self.detector = AsyncMock(return_value=[
            {"label": "cup", "confidence": .9}, {"label": "cup", "confidence": .8},
            {"label": "book", "confidence": .7}])
    async def asyncTearDown(self):
        self.temp.cleanup()

    def make(self, outputs, **options):
        gateway = FakeGateway(outputs)
        dialogue = VisualDialogue(gateway=gateway, memories=self.memory,
                                  frame_provider=self.frame,
                                  frame_status=lambda: {"connected": True, "frame_age_ms": 100},
                                  detect=self.detector, **options)
        return dialogue, gateway

    async def test_ordinary_chat_uses_no_camera_or_gpu(self):
        dialogue, gateway = self.make(['{"intent":"chat","reply":"Привет, как дела?","use_yolo":false,"use_cv":false,"use_vlm":false}'])
        result = await dialogue.respond("Привет!")
        self.assertEqual(result["tools"], ["dialogue_planner"])
        self.assertEqual(result["reply"], "Привет, как дела?")
        self.frame.assert_not_awaited()
        self.detector.assert_not_awaited()
        self.assertTrue(gateway.calls[0]["cpu"])
        self.assertEqual(gateway.calls[0]["model"], "qwen3:4b-instruct")

    async def test_contextual_followup_chooses_vision_without_keyword_trigger(self):
        outputs = [
            '{"intent":"chat","reply":"Хорошо, слушаю.","use_yolo":false,"use_cv":false,"use_vlm":false}',
            '{"intent":"observe","reply":"","use_yolo":true,"use_cv":false,"use_vlm":true}',
            "На кадре две чашки и книга.",
        ]
        dialogue, gateway = self.make(outputs)
        await dialogue.respond("Пока я найду предмет")
        reply = await dialogue.respond("А этот?")
        self.assertIn("acer_cpu_yolo", reply["tools"])
        self.assertIn("core_vlm", reply["tools"])
        self.assertEqual(reply["visual_evidence"]["yolo"]["counts"], {"cup": 2, "book": 1})
        self.assertEqual(self.frame.await_count, 1)
        self.assertEqual(self.detector.await_count, 1)
        self.assertEqual(gateway.calls[2]["model"], "qwen2.5vl:7b")
        self.assertIn("images", gateway.calls[2]["messages"][1])
        # History explicitly includes previous turn and prior assistant answer.
        self.assertIn("Хорошо, слушаю.", gateway.calls[1]["messages"][1]["content"])

    async def test_teaching_requires_next_turn_explicit_confirmation(self):
        outputs = [
            '{"intent":"teach","label":"датчик Холла","reply":"Вижу небольшой предмет.","use_yolo":true}',
            "Похож на электронный модуль.",
            '{"intent":"confirm","reply":"Ок"}',
        ]
        dialogue, gateway = self.make(outputs)
        first = await dialogue.respond("Это датчик Холла, давай запомним его")
        self.assertEqual(first["pending_label"], "датчик Холла")
        self.assertEqual(len(self.memory.list()), 0)
        second = await dialogue.respond("Да, запомни")
        self.assertIn("Запомнил", second["reply"])
        self.assertIn("visual_memory_write", second["tools"])
        records = self.memory.list()
        self.assertEqual(records[0]["label"], "датчик Холла")
        self.assertEqual(records[0]["image_saved"], 0)
        self.assertFalse((Path(self.temp.name) / "images").exists())

    async def test_confirmation_without_pending_does_not_write(self):
        dialogue, _ = self.make(['{"intent":"confirm","reply":"Подтверждаю."}'])
        result = await dialogue.respond("Да, запомни")
        self.assertIn("Нет ожидающего", result["reply"])
        self.assertEqual(self.memory.list(), [])

    async def test_no_fresh_frame_no_hallucination(self):
        dialogue, gw = self.make(['{"intent":"observe","reply":"Перед камерой стакан","use_vlm":true}'])
        dialogue.frame_status = lambda: {"connected": True, "frame_age_ms": 9999}
        answer = await dialogue.respond("Что передо мной?")
        self.assertIn("нет свежего кадра", answer["reply"])
        self.assertNotIn("стакан", answer["reply"])
        self.frame.assert_not_awaited()
        self.assertEqual(len(gw.calls), 1)

    async def test_visual_confirmation_can_store_image_when_opted_in(self):
        dialogue, _ = self.make([
            '{"intent":"teach","label":"мой куб","reply":"Куб","use_vlm":false}',
            '{"intent":"confirm","reply":"Подтверждаю"}',
        ], save_images=True)
        await dialogue.respond("Это мой куб")
        answer = await dialogue.respond("Верно, сохрани пример")
        self.assertIn("Запомнил", answer["reply"])
        rows = self.memory.list()
        self.assertEqual(rows[0]["image_saved"], 1)
        self.assertTrue((Path(self.temp.name) / "images" / (rows[0]["id"]+".jpg")).exists())


class GatewaySafetyTests(unittest.TestCase):
    def test_private_host_and_model_validation(self):
        with self.assertRaises(ValueError):
            OllamaGateway("http://8.8.8.8:11434")
        with self.assertRaises(ValueError):
            OllamaGateway("http://evil:pw@127.0.0.1:11434")
        gateway = OllamaGateway("http://192.168.0.100:11434")
        self.assertEqual(gateway.url, "http://192.168.0.100:11434")
        self.assertEqual(_plan("not-json")["use_vlm"], False)


if __name__ == "__main__":
    unittest.main()
