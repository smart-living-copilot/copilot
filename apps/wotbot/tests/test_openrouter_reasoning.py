import unittest

from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from wotbot.core.openrouter import REASONING_KEY, ChatOpenRouter


def _client() -> ChatOpenRouter:
    return ChatOpenRouter(model="test-model", api_key="test-key")


def _completion(message: dict) -> dict:
    return {
        "id": "gen-1",
        "model": "test-model",
        "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
    }


def _stream_chunk(delta: dict) -> dict:
    return {
        "id": "gen-1",
        "model": "test-model",
        "choices": [{"index": 0, "finish_reason": None, "delta": delta}],
    }


class CreateChatResultTestCase(unittest.TestCase):
    def test_reasoning_is_kept_where_the_stock_parser_drops_it(self) -> None:
        result = _client()._create_chat_result(
            _completion({"role": "assistant", "content": "391", "reasoning": "17 x 23 = 391"})
        )

        message = result.generations[0].message
        self.assertEqual(message.content, "391")
        self.assertEqual(message.additional_kwargs[REASONING_KEY], "17 x 23 = 391")

    def test_response_without_reasoning_gains_no_key(self) -> None:
        result = _client()._create_chat_result(_completion({"role": "assistant", "content": "391"}))

        self.assertNotIn(REASONING_KEY, result.generations[0].message.additional_kwargs)

    def test_empty_reasoning_is_not_recorded(self) -> None:
        """What a plain reasoning_effort request returns: billed, but blank."""
        result = _client()._create_chat_result(
            _completion({"role": "assistant", "content": "391", "reasoning": ""})
        )

        self.assertNotIn(REASONING_KEY, result.generations[0].message.additional_kwargs)


class StreamingTestCase(unittest.TestCase):
    def _convert(self, chunk: dict) -> ChatGenerationChunk | None:
        return _client()._convert_chunk_to_generation_chunk(chunk, AIMessageChunk, None)

    def test_reasoning_delta_is_kept(self) -> None:
        generation = self._convert(_stream_chunk({"reasoning": "thinking..."}))

        assert generation is not None
        self.assertEqual(generation.message.additional_kwargs[REASONING_KEY], "thinking...")

    def test_deltas_concatenate_into_the_whole_trace(self) -> None:
        """Chunk merging is what assembles the trace, so it has to append."""
        first = self._convert(_stream_chunk({"reasoning": "step one "}))
        second = self._convert(_stream_chunk({"reasoning": "step two"}))

        assert first is not None and second is not None
        merged = first.message + second.message

        self.assertEqual(merged.additional_kwargs[REASONING_KEY], "step one step two")

    def test_content_delta_without_reasoning_is_untouched(self) -> None:
        generation = self._convert(_stream_chunk({"content": "391"}))

        assert generation is not None
        self.assertEqual(generation.message.content, "391")
        self.assertNotIn(REASONING_KEY, generation.message.additional_kwargs)


if __name__ == "__main__":
    unittest.main()
