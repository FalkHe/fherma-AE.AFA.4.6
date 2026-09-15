class ContentError(Exception):
    """Base for every content failure."""


class ContentNotFoundError(ContentError):
    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        super().__init__(f"content not found: {relative_path}")


class ContentInvalidError(ContentError):
    def __init__(self, campaign_id: str, version: str, errors: list[str]) -> None:
        self.campaign_id = campaign_id
        self.version = version
        self.errors = errors
        detail = errors[0] if errors else "no detail"
        super().__init__(
            f"{campaign_id}/{version}: invalid content ({len(errors)} problem(s)): {detail}"
        )
