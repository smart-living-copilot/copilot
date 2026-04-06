import unittest

from copilot.agui_messages import strip_none_fields


class StripNoneFieldsTestCase(unittest.TestCase):
    def test_removes_null_optional_fields_from_message_payload(self) -> None:
        payload = {
            "id": "message-1",
            "role": "assistant",
            "name": None,
            "content": None,
            "toolCalls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "things_search",
                        "arguments": '{"query":"meter"}',
                    },
                    "encryptedValue": None,
                }
            ],
            "error": None,
        }

        self.assertEqual(
            strip_none_fields(payload),
            {
                "id": "message-1",
                "role": "assistant",
                "toolCalls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "things_search",
                            "arguments": '{"query":"meter"}',
                        },
                    }
                ],
            },
        )

    def test_preserves_lists_and_nested_non_null_values(self) -> None:
        payload = [
            {
                "id": "message-1",
                "content": [
                    {"type": "text", "text": "hello", "meta": None},
                    {"type": "image", "url": "https://example.com/image.png"},
                ],
            }
        ]

        self.assertEqual(
            strip_none_fields(payload),
            [
                {
                    "id": "message-1",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {"type": "image", "url": "https://example.com/image.png"},
                    ],
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
