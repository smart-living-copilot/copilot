import unittest

from copilot.prompts import ANALYSIS_PROMPT, CONTROL_PROMPT


class AnalysisGuidanceTestCase(unittest.TestCase):
    def test_analysis_prompt_requires_full_affordance_inspection(self) -> None:
        self.assertIn("wot_get_action or wot_get_property", ANALYSIS_PROMPT)
        self.assertIn(
            "Use all relevant NILM services",
            ANALYSIS_PROMPT,
        )
        self.assertIn("Current Time", ANALYSIS_PROMPT)

    def test_analysis_prompt_describes_nilm_workflow(self) -> None:
        self.assertIn("NILM services for that household", ANALYSIS_PROMPT)
        self.assertIn("stacked area chart", ANALYSIS_PROMPT)

    def test_analysis_prompt_describes_typical_workflow(self) -> None:
        self.assertIn("## Typical workflow", ANALYSIS_PROMPT)
        self.assertIn("things_search", ANALYSIS_PROMPT)
        self.assertIn("wot_get_action", ANALYSIS_PROMPT)
        self.assertIn("run_code", ANALYSIS_PROMPT)


class ControlGuidanceTestCase(unittest.TestCase):
    def test_control_prompt_requires_confirmation_for_safety_critical(self) -> None:
        self.assertIn("explicit confirmation", CONTROL_PROMPT)
        self.assertIn("unlocking doors", CONTROL_PROMPT)

    def test_control_prompt_describes_confirm_then_proceed_flow(self) -> None:
        self.assertIn("until the user confirms", CONTROL_PROMPT)


if __name__ == "__main__":
    unittest.main()
