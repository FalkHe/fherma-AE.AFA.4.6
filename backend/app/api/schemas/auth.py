"""Schemas for the authentication endpoints.

`/auth/*` is plain JSON and exempt from JSON:API, but it keeps the camelCase
attribute convention of the rest of the API: Python stays snake_case and the
alias generator does the translation on the wire.

The username and password rules are field validators rather than checks inside
the endpoints, so a rejected value produces FastAPI's default 422 body with the
offending field in `loc`.

Those rules apply to **registration only**. Login is a credential check, not
data entry: a syntactically impossible username or password is simply a wrong
credential and must fail authentication with 401, not 422. `LoginRequest`
therefore normalises the username (the service looks up the normalised form)
and validates neither field's format — with one sanctioned exception (OQ-A):
`password` carries a `max_length` ceiling purely to cap Argon2 work per
attempt, not to validate the credential.
"""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 32
# Applied after normalisation: uppercase input is folded, not rejected.
USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]+$")

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

# Owner-approved (OQ-A) sole relaxation of "login is deliberately unvalidated"
# (see `docs/roadmap/phase-1/shared-knowledge.md`): caps Argon2 work per
# attempt, nothing else about login gains a rule.
LOGIN_PASSWORD_MAX_LENGTH = 1024


class AuthSchema(BaseModel):
    """Base for the auth payloads: camelCase on the wire, snake_case in Python."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class _CredentialsRequest(AuthSchema):
    """A username/password pair, with the username folded to its stored form."""

    username: str
    password: str

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        """Fold the username to the single form that is stored and queried."""
        return value.strip().lower()


class RegisterRequest(_CredentialsRequest):
    """Credentials for a new account, carrying the pinned validation rules."""

    @field_validator("username")
    @classmethod
    def check_username_format(cls, value: str) -> str:
        """Reject usernames that could never be stored.

        `value` has already been normalised by `normalize_username`: the
        inherited validator runs first, so uppercase and surrounding whitespace
        are folded rather than rejected.
        """
        if not USERNAME_MIN_LENGTH <= len(value) <= USERNAME_MAX_LENGTH:
            raise ValueError(
                f"Username must be between {USERNAME_MIN_LENGTH} and "
                f"{USERNAME_MAX_LENGTH} characters long."
            )
        if USERNAME_PATTERN.match(value) is None:
            raise ValueError(
                "Username may only contain lowercase letters, digits, "
                "underscores, dots and hyphens."
            )
        return value

    @field_validator("password")
    @classmethod
    def check_password_length(cls, value: str) -> str:
        """Enforce the length bounds; there is deliberately no other policy."""
        if not PASSWORD_MIN_LENGTH <= len(value) <= PASSWORD_MAX_LENGTH:
            raise ValueError(
                f"Password must be between {PASSWORD_MIN_LENGTH} and "
                f"{PASSWORD_MAX_LENGTH} characters long."
            )
        return value


class LoginRequest(_CredentialsRequest):
    """Credentials for an existing account, plus the cookie lifetime choice.

    Deliberately unvalidated beyond the username normalisation and the
    password length ceiling: a credential that could not possibly match is
    rejected by `user_service.authenticate` with a 401, on the same
    constant-time path as any other wrong password. `password`'s
    `max_length` is the one sanctioned exception (OQ-A) — it exists solely to
    cap Argon2 work per attempt, not as data-entry validation.
    """

    password: Annotated[str, Field(max_length=LOGIN_PASSWORD_MAX_LENGTH)]
    remember_me: bool = False


class UserResponse(AuthSchema):
    """The authenticated account, as every `/auth/*` success body returns it."""

    id: str
    username: str
    role: Literal["user", "admin"]
