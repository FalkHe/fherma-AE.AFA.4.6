class PromptError(Exception):
    """Base for every prompt-resolution failure."""


class PromptIdInvalidError(PromptError):
    """Raised when a prompt id is not three well-formed segments, or a
    requested `--version` fails `VERSION_PATTERN`.

    Raised by whitelist, before any `Path` is constructed — never for a
    well-formed id whose file happens to be missing (that is
    `PromptNotFoundError`), so the two stay distinguishable (← AC4).
    """

    code = "PROMPT_ID_INVALID"

    def __init__(self, value: str, reason: str) -> None:
        self.value = value
        self.reason = reason
        super().__init__(f"invalid prompt id: {value} ({reason})")


class PromptNotFoundError(PromptError):
    """Raised when a prompt id is well-formed but the capability directory,
    `prompts/`, the version directory or `<id>.md` is missing.

    Never raised for a malformed id — that is `PromptIdInvalidError`.
    """

    code = "PROMPT_NOT_FOUND"

    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        super().__init__(f"prompt not found: {relative_path}")
