"""Standalone worker + scheduler process: `python -m app.worker`."""

from __future__ import annotations

import asyncio
import logging
import signal

from app.db.base import Database
from app.logging import setup_logging
from app.main import build_integrations
from app.queue.jobs import JobQueue
from app.queue.scheduler import Scheduler
from app.queue.worker import Worker


async def main() -> None:
    setup_logging()
    db = Database()
    await db.create_all()
    queue = JobQueue(db)
    worker = Worker(db, queue, build_integrations())
    scheduler = Scheduler(db, queue)
    await worker.start()
    await scheduler.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    logging.getLogger("worker").info("running; Ctrl-C to stop")
    await stop.wait()
    await scheduler.stop()
    await worker.stop()
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
