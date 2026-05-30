import os
import unittest

import pytest

from copilot.core.config import get_settings
from copilot.core.database import get_connection_pool, init_db
from copilot.threads.store import (
    create_thread,
    delete_thread,
    get_thread,
    list_threads,
    sync_thread_after_run,
    touch_thread,
    update_thread_title,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("COPILOT_TEST_DATABASE_URL"),
    reason="COPILOT_TEST_DATABASE_URL is required for Postgres thread store tests",
)


def _close_cached_pool() -> None:
    if get_connection_pool.cache_info().currsize:
        get_connection_pool().close()
    get_connection_pool.cache_clear()


class ThreadStoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["REGISTRY_DATABASE_URL"] = os.environ["COPILOT_TEST_DATABASE_URL"]
        get_settings.cache_clear()
        _close_cached_pool()
        init_db()
        with get_connection_pool().connection() as connection:
            connection.execute("TRUNCATE threads")
            connection.commit()

    def tearDown(self) -> None:
        get_settings.cache_clear()
        _close_cached_pool()

    def test_create_thread_lists_newest_first(self) -> None:
        first = create_thread(thread_id="thread-a", title="First")
        second = create_thread(thread_id="thread-b", title="Second")

        threads = list_threads()

        self.assertEqual([thread["id"] for thread in threads], ["thread-b", "thread-a"])
        self.assertEqual(first["title"], "First")
        self.assertEqual(second["title"], "Second")

    def test_touch_thread_preserves_existing_title_and_updates_timestamp(self) -> None:
        created = create_thread(thread_id="thread-a", title="Pinned title")
        touched = touch_thread("thread-a")

        self.assertIsNotNone(touched)
        self.assertEqual(touched["title"], "Pinned title")
        self.assertEqual(touched["createdAt"], created["createdAt"])
        self.assertGreaterEqual(touched["updatedAt"], created["updatedAt"])

    def test_touch_thread_ignores_missing_thread(self) -> None:
        touched = touch_thread("thread-a")

        self.assertIsNone(touched)
        self.assertEqual(list_threads(), [])

    def test_get_thread_returns_thread_record(self) -> None:
        created = create_thread(thread_id="thread-a", title="Pinned title")

        self.assertEqual(get_thread("thread-a"), created)
        self.assertIsNone(get_thread("missing-thread"))

    def test_sync_thread_after_run_sets_suggested_title_once_and_updates_timestamp(self) -> None:
        created = create_thread(thread_id="thread-a")

        first_sync = sync_thread_after_run(
            "thread-a",
            suggested_title="Suggested title from the first user prompt",
        )
        second_sync = sync_thread_after_run(
            "thread-a",
            suggested_title="Newer suggestion that should not replace the first one",
        )

        self.assertIsNotNone(first_sync)
        self.assertIsNotNone(second_sync)
        self.assertEqual(
            first_sync["title"],
            "Suggested title from the first user prompt"[:50],
        )
        self.assertEqual(second_sync["title"], first_sync["title"])
        self.assertGreaterEqual(first_sync["updatedAt"], created["updatedAt"])
        self.assertGreaterEqual(second_sync["updatedAt"], first_sync["updatedAt"])

    def test_sync_thread_after_run_preserves_custom_titles(self) -> None:
        create_thread(thread_id="thread-a", title="Pinned title")

        synced = sync_thread_after_run(
            "thread-a",
            suggested_title="Suggested title from the run",
        )

        self.assertIsNotNone(synced)
        self.assertEqual(synced["title"], "Pinned title")

    def test_update_thread_title_respects_force_flag(self) -> None:
        create_thread(thread_id="thread-a", title="Custom title")

        unchanged = update_thread_title(
            thread_id="thread-a",
            title="Suggested title",
            force=False,
        )
        forced = update_thread_title(
            thread_id="thread-a",
            title="Forced title",
            force=True,
        )

        self.assertEqual(unchanged["title"], "Custom title")
        self.assertEqual(forced["title"], "Forced title")

    def test_delete_thread_removes_metadata(self) -> None:
        create_thread(thread_id="thread-a")

        self.assertTrue(delete_thread("thread-a"))
        self.assertFalse(delete_thread("thread-a"))
        self.assertEqual(list_threads(), [])


if __name__ == "__main__":
    unittest.main()
