from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class SourceUnit(Base):
    """Bitta xabar yoki albom — pipeline'ning ishlov birligi."""

    __tablename__ = "source_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, index=True)
    channel_title: Mapped[str] = mapped_column(String(256), default="")
    grouped_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    media_kinds: Mapped[list] = mapped_column(JSON, default=list)
    source_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(32), default="received", index=True)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    messages: Mapped[list["UnitMessage"]] = relationship(
        back_populates="unit", cascade="all, delete-orphan", order_by="UnitMessage.message_id", lazy="selectin"
    )


class UnitMessage(Base):
    """Birlikka tegishli har bir Telegram xabari (albomda bir nechta)."""

    __tablename__ = "unit_messages"
    __table_args__ = (UniqueConstraint("channel_id", "message_id", name="uq_channel_message"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("source_units.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)

    unit: Mapped[SourceUnit] = relationship(back_populates="messages")


class AuditLog(Base):
    """Har qaror/hodisa uchun izlanadigan yozuv."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_unit_created", "unit_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("source_units.id", ondelete="SET NULL"), nullable=True)
    event: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UnitHash(Base):
    """Dublikat aniqlash uchun matn hash va media perceptual hash'lari."""

    __tablename__ = "unit_hashes"
    __table_args__ = (Index("ix_hash_kind_value", "kind", "value"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("source_units.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # "text" | "phash"
    value: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
