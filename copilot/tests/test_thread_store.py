import tempfile
import unittest
from pathlib import Path

from copilot.thread_store import (
    create_thread,
    delete_thread,
    get_thread,
    list_threads,
    sync_thread_after_run,
    touch_thread,
    update_thread_title,
)


class ThreadStoreTestCase(unittest.TestCase):
    def test_create_thread_lists_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "agent_state.db")

            first = create_thread(db_path, thread_id="thread-a", title="First")
            second = create_thread(db_path, thread_id="thread-b", title="Second")

            threads = list_threads(db_path)

            self.assertEqual([thread["id"] for thread in threads], ["thread-b", "thread-a"])
            self.assertEqual(first["title"], "First")
            self.assertEqual(second["title"], "Second")

    def test_touch_thread_preserves_existing_title_and_updates_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "agent_state.db")

            created = create_thread(db_path, thread_id="thread-a", title="Pinned title")
            touched = touch_thread(db_path, "thread-a")

            self.assertEqual(touched["title"], "Pinned title")
            self.assertEqual(touched["createdAt"], created["createdAt"])
            self.assertGreaterEqual(touched["updatedAt"], created["updatedAt"])

    def test_touch_thread_ignores_missing_thread(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "agent_state.db")

            touched = touch_thread(db_path, "thread-a")

            self.assertIsNone(touched)
            self.assertEqual(list_threads(db_path), [])

    def test_get_thread_returns_thread_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "agent_state.db")

            created = create_thread(db_path, thread_id="thread-a", title="Pinned title")

            self.assertEqual(get_thread(db_path, "thread-a"), created)
            self.assertIsNone(get_thread(db_path, "missing-thread"))

    def test_sync_thread_after_run_sets_suggested_title_once_and_updates_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "agent_state.db")

            created = create_thread(db_path, thread_id="thread-a")

            first_sync = sync_thread_after_run(
                db_path,
                "thread-a",
                suggested_title="Suggested title from the first user prompt",
            )
            second_sync = sync_thread_after_run(
                db_path,
                "thread-a",
                suggested_title="Newer suggestion that should not replace the first one",
            )

            self.assertEqual(
                first_sync["title"],
                "Suggested title from the first user prompt"[:50],
            )
            self.assertEqual(second_sync["title"], first_sync["title"])
            self.assertGreaterEqual(first_sync["updatedAt"], created["updatedAt"])
            self.assertGreaterEqual(second_sync["updatedAt"], first_sync["updatedAt"])

    def test_sync_thread_after_run_preserves_custom_titles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "agent_state.db")

            create_thread(db_path, thread_id="thread-a", title="Pinned title")

            synced = sync_thread_after_run(
                db_path,
                "thread-a",
                suggested_title="Suggested title from the run",
            )

            self.assertEqual(synced["title"], "Pinned title")

    def test_update_thread_title_respects_force_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "agent_state.db")

            create_thread(db_path, thread_id="thread-a", title="Custom title")

            unchanged = update_thread_title(
                db_path,
                thread_id="thread-a",
                title="Suggested title",
                force=False,
            )
            forced = update_thread_title(
                db_path,
                thread_id="thread-a",
                title="Forced title",
                force=True,
            )

            self.assertEqual(unchanged["title"], "Custom title")
            self.assertEqual(forced["title"], "Forced title")

    def test_delete_thread_removes_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "agent_state.db")

            create_thread(db_path, thread_id="thread-a")

            self.assertTrue(delete_thread(db_path, "thread-a"))
            self.assertFalse(delete_thread(db_path, "thread-a"))
            self.assertEqual(list_threads(db_path), [])


if __name__ == "__main__":
    unittest.main()
