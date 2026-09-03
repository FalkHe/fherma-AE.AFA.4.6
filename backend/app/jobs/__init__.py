"""Background jobs: the Taskiq broker and one module per job family.

`TransientJobError` lives here (not in `broker.py`) so job modules can raise it
without importing the broker's Redis wiring. It is the **only** exception class
the retry middleware acts on: raising it means "this failed for a reason that
may pass — network hiccup, upstream 5xx, LLM timeout". Every other exception is
a deterministic failure, is never retried, and marks its operation `failed`.
"""


class TransientJobError(Exception):
    """A job failure worth retrying with backoff."""
