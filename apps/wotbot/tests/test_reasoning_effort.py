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

    def test_openrouter_style_sends_the_reasoning_object(self) -> None:
        """The plain reasoning_effort field makes OpenRouter bill for reasoning
        it never returns; only the object form sends the text back."""
        self.assertEqual(
            reasoning_effort_kwargs("medium", "openrouter"),
            {"extra_body": {"reasoning": {"effort": "medium"}}},
        )

    def test_openrouter_style_maps_none_to_disabled(self) -> None:
        """OpenRouter's effort scale has no "none", so that level turns it off."""
        self.assertEqual(
            reasoning_effort_kwargs("none", "openrouter"),
            {"extra_body": {"reasoning": {"enabled": False}}},
        )


if __name__ == "__main__":
    unittest.main()
