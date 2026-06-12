import unittest

from copilot.agent.prompts import ROUTER_PROMPT, VIRTUAL_THINGS_PROMPT


class VirtualThingPromptTestCase(unittest.TestCase):
    def test_router_mentions_virtual_things_intent(self) -> None:
        self.assertIn("virtual_things", ROUTER_PROMPT)
        self.assertIn("computed/synthetic/virtual Things", ROUTER_PROMPT)

    def test_authoring_prompt_uses_draft_before_define_and_forbids_upsert(self) -> None:
        self.assertIn("draft_virtual_thing_definition", VIRTUAL_THINGS_PROMPT)
        self.assertIn("define_virtual_thing", VIRTUAL_THINGS_PROMPT)
        self.assertIn("Never use things_upsert", VIRTUAL_THINGS_PROMPT)
        self.assertIn("def handle(input, state, context)", VIRTUAL_THINGS_PROMPT)
        self.assertIn("state = state or {}", VIRTUAL_THINGS_PROMPT)

    def test_authoring_prompt_directs_reuse_of_prior_analysis(self) -> None:
        self.assertIn("Reusing Prior Analysis", VIRTUAL_THINGS_PROMPT)
        self.assertIn("Prior Analysis Code", VIRTUAL_THINGS_PROMPT)

    def test_authoring_prompt_mentions_async_virtual_servient_production(self) -> None:
        self.assertIn("created asynchronously by virtual-servient", VIRTUAL_THINGS_PROMPT)
        self.assertIn("do not redefine it immediately", VIRTUAL_THINGS_PROMPT)


if __name__ == "__main__":
    unittest.main()
