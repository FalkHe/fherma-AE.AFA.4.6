class LlmError(Exception):
    """Base for every LLM-access failure.

    Sprint 02 adds the eight provider failure classes as further subclasses
    here, plus a `classify()` helper. This sprint needs only the
    configuration case below.
    """


class LlmConfigurationError(LlmError):
    """Raised when the seam is misconfigured, before any client is built."""

    def __init__(self, message: str = "OPENROUTER_API_KEY is not set.") -> None:
        super().__init__(message)
