import base64
import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TEST_DB = Path(tempfile.gettempdir()) / "jarvis_max_v3_smoke.db"
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["JARVIS_DB_FILE"] = str(TEST_DB)
os.environ.pop("GROQ_API_KEY", None)

main = importlib.import_module("main")
main.init_db()


class JarvisMaxSmokeTests(unittest.TestCase):
    def test_self_check(self):
        result = main.self_check()
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["checks"]["database"]["ok"])
        self.assertTrue(result["checks"]["calculator"]["ok"])
        self.assertTrue(result["checks"]["sympy"]["ok"])

    def test_direct_math_route(self):
        result = main.direct_route("test", "Resuelve x² - 5x + 6 = 0 paso a paso.")
        self.assertIsNotNone(result)
        self.assertIn("x = 2", result["reply"])
        self.assertIn("x = 3", result["reply"])
        self.assertEqual(result["usage"]["total_tokens"], 0)

    def test_memory_lifecycle(self):
        saved = main.memory_save("test", "Prefiero código completo", "preference", 4)
        found = main.memory_search("test", "código", 5)
        self.assertTrue(any(item["id"] == saved["id"] for item in found))
        deleted = main.memory_delete("test", saved["id"])
        self.assertTrue(deleted["deleted"])

    def test_document_text_upload(self):
        payload = base64.b64encode(b"Documento de prueba sobre inflacion y economia.").decode()
        doc = main.save_document("test", "prueba.txt", payload)
        self.assertEqual(doc["file_type"], ".txt")
        matches = main.document_search("test", "inflacion", 5)
        self.assertTrue(matches["matches"])

    def test_dashboard(self):
        data = main.dashboard("test")
        self.assertEqual(data["version"], "3.0.0")
        self.assertIn("counts", data)
        self.assertIn("models", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
