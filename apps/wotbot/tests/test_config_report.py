import unittest

from wotbot.core.config_report import (
    CONFIG_SECTIONS,
    SECRET_MISSING,
    SECRET_PLACEHOLDER,
    Render,
    build_config_report,
    strip_url_credentials,
)
from wotbot.core.settings import Settings


def _settings(**overrides) -> Settings:
    """Isolated from the repo's own .env, so results do not depend on the checkout."""
    return Settings(_env_file=None, **overrides)


def _fields(report: dict) -> dict[str, dict]:
    return {field["name"]: field for section in report["sections"] for field in section["fields"]}


class ConfigAllowlistTestCase(unittest.TestCase):
    def test_every_allowlisted_field_exists_on_settings(self) -> None:
        """Catches an allowlist entry left behind by a rename in Settings."""
        for section in CONFIG_SECTIONS:
            for spec in section.fields:
                with self.subTest(field=spec.attribute):
                    self.assertIn(spec.attribute, Settings.model_fields)

    def test_no_duplicate_reported_names(self) -> None:
        names = [spec.name for section in CONFIG_SECTIONS for spec in section.fields]
        self.assertCountEqual(names, set(names))

    def test_credential_bearing_settings_are_never_reported_verbatim(self) -> None:
        """The allowlist's whole job: no value reaches the page in the clear.

        Anything whose value can embed a credential must be declared SECRET (not
        reported at all) or URL (userinfo stripped). A name-based filter would
        miss every entry in this list.
        """
        credential_bearing = {
            "openai_api_key",
            "openai_embedding_api_key",
            "stt_api_key",
            "tts_api_key",
            "livekit_api_key",
            "livekit_api_secret",
            "internal_api_key",
            "init_admin_token",
            "wot_runtime_registry_token",
            "wot_runtime_api_token",
            "virtual_servient_registry_token",
            "registry_database_url",
            "agent_state_database_url",
            "redis_url",
            "openai_base_url",
            "openai_embedding_api_base_url",
        }
        reported = {
            spec.attribute: spec.render for section in CONFIG_SECTIONS for spec in section.fields
        }

        for attribute in credential_bearing:
            with self.subTest(field=attribute):
                render = reported.get(attribute)
                if render is not None:
                    self.assertIn(render, {Render.SECRET, Render.URL})


class StripUrlCredentialsTestCase(unittest.TestCase):
    def test_password_is_removed_but_host_survives(self) -> None:
        self.assertEqual(
            strip_url_credentials("postgresql://wotbot:hunter2@postgres:5432/wotbot"),
            "postgresql://wotbot:***@postgres:5432/wotbot",
        )

    def test_url_without_credentials_is_untouched(self) -> None:
        self.assertEqual(strip_url_credentials("redis://valkey:6379"), "redis://valkey:6379")

    def test_password_containing_an_at_sign_is_fully_removed(self) -> None:
        self.assertEqual(
            strip_url_credentials("postgresql://user:p@ss@postgres:5432/db"),
            "postgresql://user:***@postgres:5432/db",
        )

    def test_bare_username_is_masked_without_inventing_a_password(self) -> None:
        self.assertEqual(
            strip_url_credentials("redis://token@valkey:6379"), "redis://***@valkey:6379"
        )

    def test_query_string_is_removed_wholesale(self) -> None:
        """Provider endpoints are routinely deployed with the key in a param."""
        self.assertEqual(
            strip_url_credentials("https://api.example.com/v1?api-key=sk-secret"),
            "https://api.example.com/v1?(query removed)",
        )

    def test_query_is_removed_even_without_userinfo(self) -> None:
        self.assertNotIn(
            "sk-secret",
            strip_url_credentials("https://api.example.com/v1/audio?token=sk-secret"),
        )

    def test_empty_value_stays_empty(self) -> None:
        self.assertEqual(strip_url_credentials(""), "")


class BuildConfigReportTestCase(unittest.TestCase):
    def test_secrets_report_presence_only(self) -> None:
        settings = _settings(openai_api_key="sk-super-secret-value", internal_api_key="")
        fields = _fields(build_config_report(settings, version="1.2.3"))

        self.assertEqual(fields["OPENAI_API_KEY"]["value"], SECRET_PLACEHOLDER)
        self.assertTrue(fields["OPENAI_API_KEY"]["configured"])
        self.assertEqual(fields["INTERNAL_API_KEY"]["value"], SECRET_MISSING)
        self.assertFalse(fields["INTERNAL_API_KEY"]["configured"])

    def test_no_secret_value_appears_anywhere_in_the_report(self) -> None:
        secret = "sk-do-not-leak-me"
        settings = _settings(
            # A key in the query string is as much a secret as the userinfo one.
            stt_transcriptions_url=f"https://stt.example.com/v1?api-key={secret}",
            openai_api_key=secret,
            livekit_api_secret=secret,
            init_admin_token=secret,
            registry_database_url=f"postgresql://wotbot:{secret}@postgres:5432/wotbot",
        )

        rendered = repr(build_config_report(settings, version="1.2.3"))

        self.assertNotIn(secret, rendered)

    def test_database_url_keeps_host_and_drops_password(self) -> None:
        settings = _settings(
            registry_database_url="postgresql://wotbot:hunter2@postgres:5432/wotbot"
        )
        fields = _fields(build_config_report(settings, version="1.2.3"))

        self.assertEqual(
            fields["REGISTRY_DATABASE_URL"]["value"],
            "postgresql://wotbot:***@postgres:5432/wotbot",
        )

    def test_default_and_custom_values_are_distinguished(self) -> None:
        settings = _settings(max_iterations=99)
        fields = _fields(build_config_report(settings, version="1.2.3"))

        self.assertEqual(fields["MAX_ITERATIONS"]["value"], 99)
        self.assertFalse(fields["MAX_ITERATIONS"]["is_default"])
        self.assertTrue(fields["RECURSION_LIMIT"]["is_default"])

    def test_reasoning_effort_is_reported_for_ui_comparison(self) -> None:
        settings = _settings(
            reasoning_effort_enabled=True,
            reasoning_effort_levels="low,high",
        )
        fields = _fields(build_config_report(settings, version="1.2.3"))

        self.assertTrue(fields["REASONING_EFFORT_ENABLED"]["value"])
        self.assertEqual(fields["REASONING_EFFORT_LEVELS"]["value"], "low,high")

    def test_version_is_carried_through(self) -> None:
        report = build_config_report(_settings(), version="1.2.3")
        self.assertEqual(report["version"], "1.2.3")


if __name__ == "__main__":
    unittest.main()
