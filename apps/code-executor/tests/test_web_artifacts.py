import os
import tempfile
import unittest

from fastapi.testclient import TestClient


class WebArtifactRouteTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["ARTIFACTS_DIR"] = self._tmp
        os.environ["INTERNAL_API_KEY"] = "test-key"
        from code_executor.api.app import app

        self.app = app
        self.headers = {"Authorization": "Bearer test-key"}

    def test_store_then_serve_html_artifact(self) -> None:
        with TestClient(self.app) as client:
            stored = client.post(
                "/web-artifacts",
                json={"html": "<h1>hi</h1>"},
                headers=self.headers,
            )
            self.assertEqual(stored.status_code, 200)
            filename = stored.json()["filename"]
            self.assertTrue(filename.endswith(".html"))

            served = client.get(f"/artifacts/{filename}", headers=self.headers)
            self.assertEqual(served.status_code, 200)
            self.assertIn("text/html", served.headers["content-type"])
            self.assertEqual(served.text, "<h1>hi</h1>")

    def test_store_rejects_invalid_key(self) -> None:
        with TestClient(self.app) as client:
            res = client.post(
                "/web-artifacts",
                json={"html": "x"},
                headers={"Authorization": "Bearer wrong"},
            )
            self.assertEqual(res.status_code, 401)


if __name__ == "__main__":
    unittest.main()
