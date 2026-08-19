import asyncio
import logging
from services.garbage_collector import start_storage_garbage_collector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

async def main():
    logging.info("Starting standalone Garbage Collector worker...")
    await start_storage_garbage_collector(check_interval_hours=1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Garbage Collector worker stopped.")
