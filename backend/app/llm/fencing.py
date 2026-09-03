"""Fencing untrusted content in a prompt: the one definition site.

Any prompt surface that interpolates retrieved or user-derived text into an
LLM prompt imports the fence markers and the `fence()` helper from here — this
is the single place `FENCE_START`/`FENCE_END` are defined, so no other module
may declare its own sentinel pair.
"""

import re

# The fence around one block of untrusted text in a prompt. Deliberately
# unlikely to occur in fetched prose, and stripped from the text before it is
# fenced, so the text cannot close its own block and continue as if it were
# the instructions.
FENCE_START = "<<<UNTRUSTED-DOCUMENT-START>>>"
FENCE_END = "<<<UNTRUSTED-DOCUMENT-END>>>"
FENCE_LOOKALIKE = re.compile(r"<{2,}\s*/?\s*UNTRUSTED[- _]?DOCUMENT[^>]*>{2,}", re.IGNORECASE)
_FENCE_REPLACEMENT = "[fence removed]"


def fence(text: str) -> str:
    """Return `text` with anything resembling a fence marker removed."""
    return FENCE_LOOKALIKE.sub(_FENCE_REPLACEMENT, text)
