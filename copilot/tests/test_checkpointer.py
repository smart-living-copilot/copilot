import unittest

from langgraph.checkpoint.base import CheckpointTuple

from copilot.graph.checkpointer import CachingCheckpointSaver


def _config(thread_id: str):
    return {"configurable": {"thread_id": thread_id}}


def _checkpoint(checkpoint_id: str, message: str):
    return {
        "id": checkpoint_id,
        "channel_values": {"messages": [message]},
    }


class _FakeSaver:
    serde = object()
    config_specs: list = []

    def __init__(self) -> None:
        self.tuples: dict[str, CheckpointTuple] = {}
        self.put_calls: list[tuple[str | None, str]] = []
        self.write_calls: list[tuple[str | None, str]] = []
        self.deleted_threads: list[str] = []

    async def aget_tuple(self, config):
        return self.tuples.get((config.get("configurable") or {}).get("thread_id"))

    async def alist(self, config, *, filter=None, before=None, limit=None):
        if False:
            yield config, filter, before, limit

    async def aput(self, config, checkpoint, metadata, new_versions):
        thread_id = (config.get("configurable") or {}).get("thread_id")
        result = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": (config.get("configurable") or {}).get("checkpoint_ns", ""),
                "checkpoint_id": checkpoint["id"],
            }
        }
        self.put_calls.append((thread_id, checkpoint["id"]))
        if thread_id:
            self.tuples[thread_id] = CheckpointTuple(
                config=result,
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=config,
            )
        return result

    async def aput_writes(self, config, writes, task_id, task_path=""):
        thread_id = (config.get("configurable") or {}).get("thread_id")
        self.write_calls.append((thread_id, task_id))

    async def adelete_thread(self, thread_id: str):
        self.deleted_threads.append(thread_id)
        self.tuples.pop(thread_id, None)

    def get_next_version(self, current, channel):
        return current


class CachingCheckpointSaverTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_flush_only_persists_requested_thread(self) -> None:
        underlying = _FakeSaver()
        saver = CachingCheckpointSaver(underlying)

        await saver.aput_writes(_config("thread-a"), [("messages", "a")], "task-a")
        await saver.aput(
            _config("thread-a"),
            _checkpoint("checkpoint-a", "message-a"),
            {"source": "test"},
            {"messages": 1},
        )
        await saver.aput(
            _config("thread-b"),
            _checkpoint("checkpoint-b", "message-b"),
            {"source": "test"},
            {"messages": 1},
        )

        await saver.flush("thread-a")

        self.assertEqual(underlying.write_calls, [("thread-a", "task-a")])
        self.assertEqual(underlying.put_calls, [("thread-a", "checkpoint-a")])

        await saver.flush("thread-b")

        self.assertEqual(
            underlying.put_calls,
            [("thread-a", "checkpoint-a"), ("thread-b", "checkpoint-b")],
        )

    async def test_delete_thread_discards_cached_and_pending_state(self) -> None:
        underlying = _FakeSaver()
        saver = CachingCheckpointSaver(underlying)
        config = _config("thread-a")

        await saver.aput(
            config,
            _checkpoint("checkpoint-a", "message-a"),
            {"source": "test"},
            {"messages": 1},
        )
        await saver.aput_writes(config, [("messages", "a")], "task-a")

        await saver.adelete_thread("thread-a")

        self.assertEqual(underlying.deleted_threads, ["thread-a"])
        self.assertTrue(await saver.is_deleted_thread("thread-a"))
        self.assertIsNone(await saver.aget_tuple(config))

        await saver.aput(
            config,
            _checkpoint("checkpoint-b", "message-b"),
            {"source": "test"},
            {"messages": 2},
        )
        await saver.aput_writes(config, [("messages", "b")], "task-b")
        await saver.flush("thread-a")

        self.assertEqual(underlying.put_calls, [])
        self.assertEqual(underlying.write_calls, [])


if __name__ == "__main__":
    unittest.main()
