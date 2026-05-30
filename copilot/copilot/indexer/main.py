import asyncio
import logging
import signal
import sys

from copilot.core.config import get_settings
from copilot.indexer.consumer import (
    SearchIndexerStreamConsumer,
    SearchIndexerConsumerState,
)


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("search_indexer_consumer")


async def main() -> None:
    settings = get_settings()
    state = SearchIndexerConsumerState()
    stop_event = asyncio.Event()

    consumer = SearchIndexerStreamConsumer(
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
        await consumer.start()
        logger.info("Search indexer consumer started.")
        await consumer.run_forever(stop_event)
    except Exception as exc:
        logger.error("Consumer error: %s", exc)
        sys.exit(1)
    finally:
        await consumer.close()
        logger.info("Search indexer consumer stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
