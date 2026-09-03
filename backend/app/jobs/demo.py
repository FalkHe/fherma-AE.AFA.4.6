"""`demo.ping` — the smallest possible job, proving the queue loop works.

`app jobs ping` enqueues it and the worker log shows it executing: that is the
only thing this module is for. It carries `retry_on_error=True` because that is
the convention for every task the retry middleware should see (the middleware's
type filter still limits retries to `TransientJobError`).
"""

import logging

from app.jobs.broker import broker

logger = logging.getLogger(__name__)


@broker.task("demo.ping", retry_on_error=True)
async def ping(message: str = "pong") -> str:
    """Log the received message and return it."""
    logger.info("demo.ping executed with message %r", message)
    return message
