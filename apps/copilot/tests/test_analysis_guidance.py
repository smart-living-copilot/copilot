import unittest

from copilot.agent.prompts import ANALYSIS_PROMPT, CONTROL_PROMPT, JOBS_PROMPT


class AnalysisGuidanceTestCase(unittest.TestCase):
    def test_analysis_prompt_requires_full_affordance_inspection(self) -> None:
        self.assertIn("wot_get_action or wot_get_property", ANALYSIS_PROMPT)
        self.assertIn(
            "Use all relevant services",
            ANALYSIS_PROMPT,
        )
        self.assertIn("Current Time", ANALYSIS_PROMPT)

    def test_analysis_prompt_describes_breakdown_workflow(self) -> None:
        self.assertIn("matching analysis services for that household", ANALYSIS_PROMPT)
        self.assertIn("stacked area chart", ANALYSIS_PROMPT)

    def test_analysis_prompt_describes_typical_workflow(self) -> None:
        self.assertIn("## Typical workflow", ANALYSIS_PROMPT)
        self.assertIn("things_search", ANALYSIS_PROMPT)
        self.assertIn("things_sparql", ANALYSIS_PROMPT)
        self.assertIn("wot_get_action", ANALYSIS_PROMPT)
        self.assertIn("run_code", ANALYSIS_PROMPT)

    def test_analysis_prompt_explains_sparql_tool_choice(self) -> None:
        self.assertIn("## Discovery Tool Choice", ANALYSIS_PROMPT)
        self.assertIn("precise filter", ANALYSIS_PROMPT)
        self.assertIn("When unsure", ANALYSIS_PROMPT)
        self.assertIn("narrow the candidates with things_sparql", ANALYSIS_PROMPT)


class ControlGuidanceTestCase(unittest.TestCase):
    def test_control_prompt_requires_confirmation_for_safety_critical(self) -> None:
        self.assertIn("explicit confirmation", CONTROL_PROMPT)
        self.assertIn("unlocking doors", CONTROL_PROMPT)

    def test_control_prompt_describes_confirm_then_proceed_flow(self) -> None:
        self.assertIn("until the user confirms", CONTROL_PROMPT)

    def test_control_prompt_explains_sparql_tool_choice(self) -> None:
        self.assertIn("things_sparql", CONTROL_PROMPT)
        self.assertIn("operation types", CONTROL_PROMPT)
        self.assertIn("narrow with things_sparql", CONTROL_PROMPT)


class JobGuidanceTestCase(unittest.TestCase):
    def test_jobs_prompt_explains_sparql_tool_choice(self) -> None:
        self.assertIn("things_sparql", JOBS_PROMPT)
        self.assertIn("exact Thing Description", JOBS_PROMPT)
        self.assertIn("narrow candidates with things_sparql", JOBS_PROMPT)


if __name__ == "__main__":
    unittest.main()
