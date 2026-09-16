class SrdError(Exception):
    """Base for every SRD failure."""


class SrdCorpusEmptyError(SrdError):
    """The corpus holds no rules."""


class SrdVectorWidthError(SrdError):
    """An embedding did not match `EMBEDDING_WIDTH`."""


class SrdSourceError(SrdError):
    """The SRD source document could not be fetched, stored or parsed."""
