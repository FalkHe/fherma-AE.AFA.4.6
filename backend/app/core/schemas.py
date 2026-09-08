from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class ErrorBody(CamelModel):
    code: str
    message: str
    details: dict[str, Any] | None


class ErrorEnvelope(CamelModel):
    error: ErrorBody
