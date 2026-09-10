from sqlalchemy import CHAR
from ulid import ULID

# 26-character Crockford base32 ULID string. Every model's primary key (and
# any foreign key referencing one) declares its column type through `ID_TYPE`
# -- there is no second way to declare an id in this codebase. Ids are `str`
# in Python and on the wire; `uuid.UUID` is never used after this change.
#
# Usage:
#   id: Mapped[str] = mapped_column(ID_TYPE, primary_key=True, default=generate_id)
#   user_id: Mapped[str] = mapped_column(ID_TYPE, ForeignKey("users.id"), ...)
ID_LENGTH = 26
ID_TYPE = CHAR(ID_LENGTH)


def generate_id() -> str:
    return str(ULID())
