import base64
import io
import unittest
import zipfile

from code_executor.wot_client import SandboxWotClient


class SandboxWotClientPayloadTestCase(unittest.TestCase):
    def test_extracts_existing_runtime_binary_payload_as_bytes(self) -> None:
        value = b"PK\x03\x04gtfs"
        result = {
            "completed_result": {
                "payload": {
                    "kind": "binary",
                    "content_type": "application/zip",
                    "body_base64": base64.b64encode(value).decode(),
                }
            }
        }

        self.assertEqual(SandboxWotClient._extract_payload(result), value)

    def test_rejects_malformed_runtime_binary_payloads(self) -> None:
        result = {
            "completed_result": {
                "payload": {"kind": "binary", "body_base64": "not base64!"}
            }
        }

        with self.assertRaisesRegex(RuntimeError, "invalid base64"):
            SandboxWotClient._extract_payload(result)

    def test_binary_action_result_opens_as_an_archive_without_an_http_helper(
        self,
    ) -> None:
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("stops.txt", "stop_id,stop_name\n1,Central\n")
        result = {
            "completed_result": {
                "payload": {
                    "kind": "binary",
                    "content_type": "application/zip",
                    "body_base64": base64.b64encode(archive.getvalue()).decode(),
                }
            }
        }

        value = SandboxWotClient._extract_payload(result)

        self.assertIsInstance(value, bytes)
        with zipfile.ZipFile(io.BytesIO(value)) as bundle:
            self.assertEqual(
                bundle.read("stops.txt"),
                b"stop_id,stop_name\n1,Central\n",
            )


if __name__ == "__main__":
    unittest.main()
