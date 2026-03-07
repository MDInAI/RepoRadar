import asyncio
import logging
import signal
import sys

from agentic_workers.core.config import settings

# Configure root logger
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting Agentic-Workflow worker processes...")
    
    # Placeholder for scheduler startup
    logger.info("Worker processes running. Press Ctrl+C to stop.")
    
    stop_event = asyncio.Event()

    def handle_sigint():
        logger.info("Received stop signal. Shutting down...")
        stop_event.set()

    # Register signal handler for graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_sigint)

    await stop_event.wait()
    logger.info("Worker shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
