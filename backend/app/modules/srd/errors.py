class SrdError(Exception):
    """Base for every SRD failure."""


class SrdCorpusEmptyError(SrdError):
    """The corpus holds no rules."""


class SrdVectorWidthError(SrdError):
    """An embedding did not match `EMBEDDING_WIDTH`."""


class SrdSourceError(SrdError):
    """The SRD source markdown could not be fetched, written or parsed:
    an unreachable host, a non-2xx response, an unwritable target path, or
    a file with no markdown headings to chunk."""
