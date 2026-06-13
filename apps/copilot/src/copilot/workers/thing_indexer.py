import asyncio
import logging
import signal
import sys
from contextlib import suppress

from copilot.core.config import get_settings
from copilot.core.database import init_db
from copilot.thing_indexer.consumer import (
    ThingIndexerConsumerState,
    ThingIndexerStreamConsumer,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("thing_indexer_consumer")


async def main() -> None:
    settings = get_settings()
    state = ThingIndexerConsumerState()
    stop_event = asyncio.Event()

    consumer = ThingIndexerStreamConsumer(
        settings=settings,
        state=state,
    )

    def _on_signal() -> None:
        logger.info("Signal received, stopping consumer...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _on_signal)

    try:
        await asyncio.to_thread(init_db)
        await consumer.start()
        logger.info("Thing indexer consumer started.")
        await consumer.run_forever(stop_event)
    except Exception as exc:
        logger.error("Consumer error: %s", exc)
        sys.exit(1)
    finally:
        await consumer.close()
        logger.info("Thing indexer consumer stopped.")


def run() -> None:
    with suppress(KeyboardInterrupt):
        asyncio.run(main())


if __name__ == "__main__":
    run()
