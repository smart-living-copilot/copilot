import unittest

from copilot.agent.prompts import ANALYSIS_PROMPT, CONTROL_PROMPT, JOBS_PROMPT, ROUTER_PROMPT


class RouterGuidanceTestCase(unittest.TestCase):
    def test_router_prompt_classifies_external_kg_requests_as_analysis(self) -> None:
        self.assertIn("external knowledge graphs", ROUTER_PROMPT)
        self.assertIn("SPARQL endpoint", ROUTER_PROMPT)
        self.assertIn("RDF entity", ROUTER_PROMPT)


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
        self.assertNotIn("query_knowledge", ANALYSIS_PROMPT)
        self.assertNotIn("sparql_query", ANALYSIS_PROMPT)
        self.assertIn("wot_get_action", ANALYSIS_PROMPT)
        self.assertIn("run_code", ANALYSIS_PROMPT)

    def test_analysis_prompt_explains_sparql_tool_choice(self) -> None:
        self.assertIn("## Discovery Tool Choice", ANALYSIS_PROMPT)
        self.assertIn("things_list/things_get", ANALYSIS_PROMPT)
        self.assertIn("things_sparql", ANALYSIS_PROMPT)
        self.assertIn("read-only SPARQL", ANALYSIS_PROMPT)
        self.assertIn("local Thing graph", ANALYSIS_PROMPT)
        self.assertIn("wot.invoke_action", ANALYSIS_PROMPT)
        self.assertIn("sparqlQuery", ANALYSIS_PROMPT)


class ControlGuidanceTestCase(unittest.TestCase):
    def test_control_prompt_requires_confirmation_for_safety_critical(self) -> None:
        self.assertIn("explicit confirmation", CONTROL_PROMPT)
        self.assertIn("unlocking doors", CONTROL_PROMPT)

    def test_control_prompt_describes_confirm_then_proceed_flow(self) -> None:
        self.assertIn("until the user confirms", CONTROL_PROMPT)

    def test_control_prompt_explains_sparql_tool_choice(self) -> None:
        self.assertIn("things_sparql", CONTROL_PROMPT)
        self.assertNotIn("query_knowledge", CONTROL_PROMPT)
        self.assertNotIn("sparql_query", CONTROL_PROMPT)
        self.assertIn("things_list/things_get", CONTROL_PROMPT)
        self.assertIn("read-only SPARQL", CONTROL_PROMPT)
        self.assertIn("wot_invoke_action", CONTROL_PROMPT)
        self.assertIn("sparqlQuery", CONTROL_PROMPT)


class JobGuidanceTestCase(unittest.TestCase):
    def test_jobs_prompt_explains_sparql_tool_choice(self) -> None:
        self.assertIn("things_sparql", JOBS_PROMPT)
        self.assertNotIn("query_knowledge", JOBS_PROMPT)
        self.assertNotIn("sparql_query", JOBS_PROMPT)
        self.assertIn("things_list/things_get", JOBS_PROMPT)
        self.assertIn("read-only SPARQL", JOBS_PROMPT)
        self.assertIn("wot.invoke_action", JOBS_PROMPT)
        self.assertIn("sparqlQuery", JOBS_PROMPT)


if __name__ == "__main__":
    unittest.main()
