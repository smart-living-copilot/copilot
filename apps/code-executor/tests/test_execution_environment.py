import shutil
import tempfile
import unittest
from types import SimpleNamespace

from code_executor.constants import MAX_STDOUT_CHARS
from code_executor.execution_environment import ExecutionEnvironment

RESULT_PREFIX = "__VIRTUAL_THING_RESULT__"


class ExecutionEnvironmentOutputTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self.env = ExecutionEnvironment.__new__(ExecutionEnvironment)
        self.env.artifacts_dir = self._tmp
        self.env.images = []
        self.env.plotly = []
        self.env.wot_calls = []
        self.env.records = []
        self.env.reports = []
        self.env.plt = SimpleNamespace(show=lambda: None)
        self.env.pio = SimpleNamespace(
            show=lambda: None,
            renderers=SimpleNamespace(default=""),
        )
        self.env.user_globals = {
            "__builtins__": __builtins__,
            "print": print,
            "report": self.env.report,
        }

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_echoes_final_expression_when_no_visible_output(self) -> None:
        result = self.env.execute_code("result = {'ok': True}\nresult")

        self.assertEqual(result["stdout"], "{'ok': True}\n")

    def test_does_not_duplicate_final_expression_when_stdout_exists(self) -> None:
        result = self.env.execute_code("result = {'ok': True}\nprint(result)\nresult")

        self.assertEqual(result["stdout"], "{'ok': True}\n")

    def test_does_not_echo_final_expression_when_report_exists(self) -> None:
        result = self.env.execute_code("report('done')\n{'debug': True}")

        self.assertEqual(result["stdout"], "")
        self.assertEqual(result["reports"], ["done"])

    def test_ignores_none_final_expression(self) -> None:
        result = self.env.execute_code("None")

        self.assertEqual(result["stdout"], "")

    def test_trims_large_human_stdout(self) -> None:
        result = self.env.execute_code(f"print({'x' * (MAX_STDOUT_CHARS + 50)!r})")

        self.assertIn("... truncated", result["stdout"])
        self.assertLess(len(result["stdout"]), MAX_STDOUT_CHARS + 200)

    def test_preserves_virtual_thing_result_line_when_stdout_is_trimmed(self) -> None:
        payload = (
            RESULT_PREFIX + '{"payload":"' + ("x" * (MAX_STDOUT_CHARS + 50)) + '"}'
        )
        result = self.env.execute_code(
            f"print({'debug ' + ('d' * MAX_STDOUT_CHARS)!r})\nprint({payload!r})"
        )

        self.assertIn("... truncated", result["stdout"])
        self.assertIn(payload, result["stdout"].splitlines())


if __name__ == "__main__":
    unittest.main()
