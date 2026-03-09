from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, String, Text, text
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.schema import Index
from sqlalchemy.types import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from app.models.repository import JSONStringDictType, UTCDateTimeType, _enum_values


class RepositoryArtifactKind(StrEnum):
    README_SNAPSHOT = "readme_snapshot"
    ANALYSIS_RESULT = "analysis_result"


class RepositoryArtifact(SQLModel, table=True):
    __tablename__ = "repository_artifact"
    __table_args__ = (
        CheckConstraint(
            "runtime_relative_path != ''", name="ck_repository_artifact_path_not_blank"
        ),
        CheckConstraint("source_kind != ''", name="ck_repository_artifact_source_kind_not_blank"),
        CheckConstraint("content_sha256 != ''", name="ck_repository_artifact_sha_not_blank"),
        CheckConstraint("content_type != ''", name="ck_repository_artifact_content_type_not_blank"),
        CheckConstraint("byte_size >= 0", name="ck_repository_artifact_byte_size_non_negative"),
        Index("ix_repository_artifact_generated_at", "generated_at"),
    )

    github_repository_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("repository_intake.github_repository_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
    )
    artifact_kind: RepositoryArtifactKind = Field(
        sa_column=Column(
            SQLEnum(
                RepositoryArtifactKind,
                values_callable=_enum_values,
                name="repository_artifact_kind",
                native_enum=False,
                create_constraint=True,
            ),
            primary_key=True,
            nullable=False,
        ),
    )
    runtime_relative_path: str = Field(
        sa_column=Column(String(1024), nullable=False),
    )
    content_sha256: str = Field(
        sa_column=Column(String(64), nullable=False),
    )
    byte_size: int = Field(
        sa_column=Column(BigInteger, nullable=False),
    )
    content_type: str = Field(
        sa_column=Column(
            String(255),
            nullable=False,
            server_default=text("'application/octet-stream'"),
        ),
    )
    source_kind: str = Field(
        sa_column=Column(String(64), nullable=False),
    )
    source_url: str | None = Field(
        default=None,
        sa_column=Column(Text(), nullable=True),
    )
    provenance_metadata: dict[str, object] = Field(
        default_factory=dict,
        sa_column=Column(
            MutableDict.as_mutable(JSONStringDictType()),
            nullable=False,
            server_default=text("'{}'"),
        ),
    )
    generated_at: datetime = Field(
        sa_column=Column(UTCDateTimeType(), nullable=False),
    )
