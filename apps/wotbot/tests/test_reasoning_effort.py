import unittest

from wotbot.core.reasoning_effort import reasoning_effort_kwargs


class ReasoningEffortKwargsTestCase(unittest.TestCase):
    def test_openai_style_sends_reasoning_effort_field(self) -> None:
        self.assertEqual(reasoning_effort_kwargs("high", "openai"), {"reasoning_effort": "high"})

    def test_qwen_style_maps_none_to_thinking_off(self) -> None:
        self.assertEqual(
            reasoning_effort_kwargs("none", "qwen"),
            {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}},
        )

    def test_qwen_style_maps_any_other_level_to_thinking_on(self) -> None:
        for level in ("minimal", "low", "medium", "high", "xhigh"):
            with self.subTest(level=level):
                self.assertEqual(
                    reasoning_effort_kwargs(level, "qwen"),
                    {"extra_body": {"chat_template_kwargs": {"enable_thinking": True}}},
                )


if __name__ == "__main__":
    unittest.main()
