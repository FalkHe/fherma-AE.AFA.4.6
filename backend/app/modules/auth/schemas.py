from pydantic import Field

from app.core.schemas import CamelModel


class RegisterRequest(CamelModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    password: str = Field(min_length=8, max_length=128)


# Deliberately looser than RegisterRequest: no username pattern, so a
# malformed username reaches the service and comes back 401
# INVALID_CREDENTIALS rather than a 422 that leaks the username shape (§5.4).
class SignInRequest(CamelModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)
