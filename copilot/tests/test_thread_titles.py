import unittest
from dataclasses import dataclass

from copilot.thread_titles import suggest_thread_title


@dataclass
class _FakeMessage:
    role: str | None = None
    type: str | None = None
    content: object = ""


class SuggestThreadTitleTestCase(unittest.TestCase):
    def test_uses_latest_user_string_message(self) -> None:
        messages = [
            _FakeMessage(role="user", content="First question"),
            _FakeMessage(role="assistant", content="First answer"),
            _FakeMessage(type="human", content="Latest question"),
        ]

        self.assertEqual(suggest_thread_title(messages), "Latest question")

    def test_flattens_text_blocks_and_ignores_non_text_items(self) -> None:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "https://example.com/example.png"}},
                    {"type": "text", "text": "Check the"},
                    {"type": "input_text", "text": "garage sensor"},
                ],
            }
        ]

        self.assertEqual(suggest_thread_title(messages), "Check the garage sensor")

    def test_returns_none_when_no_user_text_exists(self) -> None:
        messages = [
            _FakeMessage(role="assistant", content="Hello"),
            _FakeMessage(role="user", content=[{"type": "image_url", "image_url": {"url": "x"}}]),
        ]

        self.assertIsNone(suggest_thread_title(messages))

    def test_truncates_titles_to_fifty_characters(self) -> None:
        title = suggest_thread_title([_FakeMessage(role="user", content="x" * 80)])

        self.assertEqual(title, "x" * 50)


if __name__ == "__main__":
    unittest.main()
