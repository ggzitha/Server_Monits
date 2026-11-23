from datetime import datetime, timezone
from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class SystemConfig(Base):
    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Use LONGTEXT on MySQL/MariaDB (4 GB vs 64 KB TEXT limit) so large 3D building JSON + snapshots never truncate
    value: Mapped[str] = mapped_column(
        Text().with_variant(LONGTEXT, "mysql").with_variant(LONGTEXT, "mariadb"),
        default="",
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

