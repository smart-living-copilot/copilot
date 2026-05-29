from copilot.thing_events import ValkeyThingEventStreamPublisher


class FakeRedisClient:
    def __init__(self) -> None:
        self.stream_writes: list[tuple[str, dict[str, str]]] = []
        self.closed = False

    def xadd(self, stream: str, fields: dict[str, str]) -> None:
        self.stream_writes.append((stream, fields))

    def close(self) -> None:
        self.closed = True


def test_stream_publisher_writes_structured_event(monkeypatch) -> None:
    fake_client = FakeRedisClient()

    class FakeRedisFactory:
        @staticmethod
        def from_url(_url: str, decode_responses: bool = True) -> FakeRedisClient:
            assert decode_responses is True
            return fake_client

    monkeypatch.setattr(
        "copilot.thing_events.publisher.redis.Redis", FakeRedisFactory
    )

    publisher = ValkeyThingEventStreamPublisher("redis://valkey:6379", "thing_events")
    publisher.publish(
        {
            "eventType": "update",
            "id": "urn:thing:test",
            "hash": "abc123",
            "title": "Test",
        }
    )
    publisher.close()

    assert fake_client.closed is True
    assert len(fake_client.stream_writes) == 1
    stream, fields = fake_client.stream_writes[0]
    assert stream == "thing_events"
    assert fields["event_type"] == "update"
    assert fields["thing_id"] == "urn:thing:test"
    assert fields["event_hash"] == "abc123"
    assert '"eventType": "update"' in fields["event_json"]
