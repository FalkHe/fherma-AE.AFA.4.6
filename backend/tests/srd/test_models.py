"""WI1: `SrdRule` column shape and the HNSW vector-cosine index it carries
(`module-structure.md` §2). Engine-free -- everything here is read off the
declarative model's `Table`, never a real connection."""

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import CHAR, Integer, String, Text
from sqlalchemy.types import DateTime

from app.modules.srd.models import EMBEDDING_WIDTH, SrdRule


def _column(name):
    return SrdRule.__table__.columns[name]


def test_embedding_width_is_1536():
    assert EMBEDDING_WIDTH == 1536


def test_id_is_the_shared_id_type_primary_key():
    column = _column("id")
    assert isinstance(column.type, CHAR)
    assert column.type.length == 26
    assert column.primary_key
    assert column.default is not None


def test_source_version_is_a_non_nullable_string():
    column = _column("source_version")
    assert isinstance(column.type, String)
    assert column.nullable is False


def test_heading_path_is_a_non_nullable_string():
    column = _column("heading_path")
    assert isinstance(column.type, String)
    assert column.nullable is False


def test_ordinal_is_a_non_nullable_integer():
    column = _column("ordinal")
    assert isinstance(column.type, Integer)
    assert column.nullable is False


def test_text_is_a_non_nullable_text_column():
    column = _column("text")
    assert isinstance(column.type, Text)
    assert column.nullable is False


def test_token_count_is_a_non_nullable_integer():
    column = _column("token_count")
    assert isinstance(column.type, Integer)
    assert column.nullable is False


def test_embedding_model_is_a_non_nullable_string():
    column = _column("embedding_model")
    assert isinstance(column.type, String)
    assert column.nullable is False


def test_embedding_is_a_vector_of_embedding_width():
    column = _column("embedding")
    assert isinstance(column.type, VECTOR)
    assert column.type.dim == EMBEDDING_WIDTH
    assert column.nullable is False


def test_created_at_is_a_timezone_aware_datetime_with_server_default():
    column = _column("created_at")
    assert isinstance(column.type, DateTime)
    assert column.type.timezone is True
    assert column.server_default is not None


def test_table_name_is_srd_rules():
    assert SrdRule.__tablename__ == "srd_rules"


def test_embedding_index_uses_hnsw_and_vector_cosine_ops():
    indexes = {index.name: index for index in SrdRule.__table__.indexes}
    index = indexes["ix_srd_rules_embedding"]

    assert [column.name for column in index.columns] == ["embedding"]
    assert index.dialect_kwargs["postgresql_using"] == "hnsw"
    assert index.dialect_kwargs["postgresql_ops"] == {"embedding": "vector_cosine_ops"}


def test_source_version_heading_path_ordinal_is_unique():
    # <- WI1/AC2: no two stored passages can claim the same citation -- the
    # database refuses a duplicate `(source_version, heading_path, ordinal)`
    # rather than trusting the splitter. Named per `Base.metadata`'s
    # `NAMING_CONVENTION` (`app/core/db.py`), matching the `0003` migration.
    constraints = {c.name: c for c in SrdRule.__table__.constraints}
    unique = constraints["uq_srd_rules_source_version"]

    assert [column.name for column in unique.columns] == [
        "source_version",
        "heading_path",
        "ordinal",
    ]
