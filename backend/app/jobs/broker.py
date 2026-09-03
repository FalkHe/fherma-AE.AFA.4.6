"""The process-wide Taskiq broker.

Redis is the queue; PostgreSQL (the `operations` table) is the application-
visible job state, so the broker deliberately has **no result backend** — task
return values are never read back.

Importing this module must not touch the network: `ListQueueBroker` only builds
a lazy Redis connection pool, so the CLI, the API and the test suite can import
it while Redis is down. The connection is opened by `startup()`.

The worker is started with this module path:

    taskiq worker app.jobs.broker:broker app.jobs.demo
"""

from taskiq.middlewares import SmartRetryMiddleware
from taskiq_redis import ListQueueBroker

from app.core.config import get_settings
from app.jobs import TransientJobError

# Backoff is delay x attempt, capped at `max_delay_exponent` seconds, plus
# 0-1 s of jitter. `types_of_exceptions` is the built-in type filter: anything
# that is not a `TransientJobError` fails the task immediately, however the
# task is labelled.
broker = ListQueueBroker(
    url=get_settings().redis_url,
    # Mandatory with redis-py >= 8: its connections default to
    # `socket_timeout=5`, while `ListQueueBroker.listen()` issues an infinite
    # `BRPOP`. The blocking read then raises `redis.TimeoutError` after five
    # idle seconds, which taskiq-redis does not catch (it handles
    # `ConnectionError` only), killing the worker process — and any task
    # running in it — every five seconds. `None` restores blocking semantics.
    socket_timeout=None,
).with_middlewares(
    SmartRetryMiddleware(
        default_retry_count=3,
        default_delay=5,
        use_jitter=True,
        use_delay_exponent=True,
        max_delay_exponent=60,
        types_of_exceptions=[TransientJobError],
    ),
)
