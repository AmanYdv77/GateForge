import pytest
from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from gateforge.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SampleModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Concrete sample model for testing schema mixins and DDL generation."""

    __tablename__ = "test_samples"

    name: Mapped[str] = mapped_column(String(50), nullable=False)


def test_model_mixins_structure() -> None:
    """Verify that UUID and Timestamp mixins attach proper columns to models."""
    columns = {col.name for col in SampleModel.__table__.columns}

    assert "id" in columns
    assert "created_at" in columns
    assert "updated_at" in columns
    assert "name" in columns

    # Ensure id is primary key
    assert SampleModel.__table__.primary_key.columns.keys() == ["id"]


@pytest.mark.asyncio
async def test_async_database_lifecycle() -> None:
    """Verify DDL creation, insertion, and querying via async SQLite in-memory engine."""
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_factory() as session:
        sample = SampleModel(name="test_record")
        session.add(sample)
        await session.commit()

        # Query back
        result = await session.execute(select(SampleModel).where(SampleModel.name == "test_record"))
        fetched = result.scalar_one_or_none()

        assert fetched is not None
        assert fetched.name == "test_record"
        assert fetched.id is not None
        assert fetched.created_at is not None

    await test_engine.dispose()
