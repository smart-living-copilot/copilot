import unittest

from langchain_core.messages import AIMessage, HumanMessage

from copilot.few_shots.analysis import (
    ANALYSIS_FEW_SHOTS,
    ANALYSIS_NILM_DISAGGREGATION_FEW_SHOT,
)
from copilot.prompts import ANALYSIS_PROMPT


class AnalysisGuidanceTestCase(unittest.TestCase):
    def test_analysis_prompt_requires_full_affordance_inspection(self) -> None:
        self.assertIn(
            "Inspect every action or property you will use with wot_get_action or wot_get_property.",
            ANALYSIS_PROMPT,
        )
        self.assertIn(
            "Use all relevant NILM services you find unless the user narrows the scope.",
            ANALYSIS_PROMPT,
        )
        self.assertIn(
            'Only use the Current Time block below for relative requests like "last 24h".',
            ANALYSIS_PROMPT,
        )

    def test_nilm_few_shot_inspects_meter_and_all_services_before_run_code(self) -> None:
        self.assertIsInstance(ANALYSIS_NILM_DISAGGREGATION_FEW_SHOT[0], HumanMessage)
        self.assertIn(
            "Use all NILM services to disaggregate it.",
            ANALYSIS_NILM_DISAGGREGATION_FEW_SHOT[0].content,
        )

        tool_calls = [
            message.tool_calls[0]["name"]
            for message in ANALYSIS_NILM_DISAGGREGATION_FEW_SHOT
            if isinstance(message, AIMessage) and getattr(message, "tool_calls", None)
        ]
        self.assertEqual(
            tool_calls,
            [
                "things_search",
                "wot_get_action",
                "things_search",
                "wot_get_action",
                "wot_get_action",
                "run_code",
            ],
        )

        run_code_call = next(
            message.tool_calls[0]
            for message in ANALYSIS_NILM_DISAGGREGATION_FEW_SHOT
            if isinstance(message, AIMessage)
            and getattr(message, "tool_calls", None)
            and message.tool_calls[0]["name"] == "run_code"
        )
        code = run_code_call["args"]["code"]
        self.assertIn("1805511600000", code)
        self.assertIn("1805522400000", code)
        self.assertIn("urn:uuid:meter-05", code)
        self.assertIn("urn:uuid:nilm-kitchen-05", code)
        self.assertIn("urn:uuid:nilm-laundry-05", code)

    def test_analysis_few_shots_include_nilm_guidance_example(self) -> None:
        tail = ANALYSIS_FEW_SHOTS[-len(ANALYSIS_NILM_DISAGGREGATION_FEW_SHOT) :]
        self.assertEqual(tail, ANALYSIS_NILM_DISAGGREGATION_FEW_SHOT)


if __name__ == "__main__":
    unittest.main()
