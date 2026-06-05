import base64
import unittest

from copilot.api.wot_runtime import _decode_payload


class DecodePayloadTestCase(unittest.TestCase):
    def test_decodes_json_payload(self) -> None:
        encoded = base64.b64encode(b'{"value": 42}').decode("ascii")
        self.assertEqual(
            _decode_payload(encoded, "application/json"),
            {"value": 42},
        )

    def test_decodes_plain_text_payload(self) -> None:
        encoded = base64.b64encode(b"hello").decode("ascii")
        self.assertEqual(_decode_payload(encoded, "text/plain"), "hello")

    def test_returns_none_for_empty_payload(self) -> None:
        self.assertIsNone(_decode_payload("", "application/json"))

    def test_falls_back_to_base64_for_binary(self) -> None:
        encoded = base64.b64encode(b"\xff\xfe\x00").decode("ascii")
        self.assertEqual(
            _decode_payload(encoded, "application/octet-stream"),
            {"base64": encoded},
        )

    def test_returns_text_when_json_is_malformed(self) -> None:
        encoded = base64.b64encode(b"not json").decode("ascii")
        self.assertEqual(_decode_payload(encoded, "application/json"), "not json")


if __name__ == "__main__":
    unittest.main()
