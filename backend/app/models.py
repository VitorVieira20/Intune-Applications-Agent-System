from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AppHistory(Base):
    __tablename__ = "apps_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    installer_url_or_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    in_store: Mapped[bool] = mapped_column(Boolean, default=False)
    install_cmd: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uninstall_cmd: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detection_rule: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    is_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    intunewin_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending|success|failed
    errors: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    correction_loops: Mapped[int] = mapped_column(Integer, default=0)

    thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    logs: Mapped[list["SystemLog"]] = relationship(
        back_populates="app_history", cascade="all, delete-orphan"
    )


class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_history_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("apps_history.id", ondelete="CASCADE"), nullable=True
    )
    node_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    level: Mapped[str] = mapped_column(String(20), default="INFO")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    app_history: Mapped[Optional["AppHistory"]] = relationship(back_populates="logs")
