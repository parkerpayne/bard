"""Database models and async engine for SQLite."""
import os
from datetime import datetime, timezone
from sqlalchemy import String, Integer, BigInteger, Boolean, DateTime, Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, AsyncAttrs


_default_path = os.environ.get("DATABASE_PATH", "./data/bard.db")
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{_default_path}"
)
# Ensure data dir exists for sqlite
if "sqlite" in DATABASE_URL:
    path = DATABASE_URL.replace("sqlite+aiosqlite:///", "").split("?")[0]
    if path and not path.startswith("/"):
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    dm_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    category_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    game_role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dm_role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # DM-only role for manage_channels etc.
    text_important_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text_scheduling_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text_general_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    voice_game_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    voice_private_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    dm_character_name: Mapped[str | None] = mapped_column(String(32), nullable=True)

    players: Mapped[list["Player"]] = relationship("Player", back_populates="game", cascade="all, delete-orphan")
    schedule_polls: Mapped[list["SchedulePoll"]] = relationship(
        "SchedulePoll", back_populates="game", cascade="all, delete-orphan"
    )

    def is_game_text_channel(self, channel_id: int) -> bool:
        return channel_id in (self.text_important_id, self.text_scheduling_id, self.text_general_id)


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    character_name: Mapped[str | None] = mapped_column(String(32), nullable=True)

    game: Mapped["Game"] = relationship("Game", back_populates="players")

    __table_args__ = ({"sqlite_autoincrement": True},)


class SchedulePoll(Base):
    __tablename__ = "schedule_polls"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expiry: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reminder_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    game: Mapped["Game"] = relationship("Game", back_populates="schedule_polls")


# ---------------------------------------------------------------------------
# Music
# ---------------------------------------------------------------------------

class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    youtube_id: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    playlist_entries: Mapped[list["PlaylistTrack"]] = relationship("PlaylistTrack", back_populates="track", cascade="all, delete-orphan")


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    cover_path: Mapped[str | None] = mapped_column(Text, nullable=True)  # relative path under web/covers/
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # space/comma-separated words
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    tracks: Mapped[list["PlaylistTrack"]] = relationship("PlaylistTrack", back_populates="playlist", cascade="all, delete-orphan", order_by="PlaylistTrack.position")


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    playlist_id: Mapped[int] = mapped_column(ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    playlist: Mapped["Playlist"] = relationship("Playlist", back_populates="tracks")
    track: Mapped["Track"] = relationship("Track", back_populates="playlist_entries")

    __table_args__ = (UniqueConstraint("playlist_id", "position", name="uq_playlist_position"),)


class PlaybackState(Base):
    """Single-row table (id=1) tracking the current playback session."""
    __tablename__ = "playback_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    device_type: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "browser" | "voice"
    voice_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    playlist_id: Mapped[int | None] = mapped_column(ForeignKey("playlists.id", ondelete="SET NULL"), nullable=True)
    track_id: Mapped[int | None] = mapped_column(ForeignKey("tracks.id", ondelete="SET NULL"), nullable=True)
    position_sec: Mapped[float] = mapped_column(Float, default=0.0)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    shuffled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )


engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Add new columns to existing tables (no-op if already present)
    if "sqlite" in DATABASE_URL:
        import sqlite3
        raw_path = DATABASE_URL.replace("sqlite+aiosqlite:///", "").split("?")[0]
        sync_conn = sqlite3.connect(raw_path)
        for sql in (
            "ALTER TABLE games ADD COLUMN dm_character_name VARCHAR(32)",
            "ALTER TABLE players ADD COLUMN character_name VARCHAR(32)",
            "ALTER TABLE games ADD COLUMN dm_role_id BIGINT",
        ):
            try:
                sync_conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # column already exists
        sync_conn.commit()
        sync_conn.close()
