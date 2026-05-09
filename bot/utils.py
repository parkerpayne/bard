"""Helpers: resolve game from channel, check permissions."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import Game, Player


async def get_game_by_channel(session: AsyncSession, guild_id: int, channel_id: int) -> Game | None:
    result = await session.execute(
        select(Game).where(Game.guild_id == guild_id).where(
            (Game.text_important_id == channel_id)
            | (Game.text_scheduling_id == channel_id)
            | (Game.text_general_id == channel_id)
        )
    )
    return result.scalars().one_or_none()


async def get_game_by_name(session: AsyncSession, guild_id: int, name: str) -> Game | None:
    result = await session.execute(
        select(Game).where(Game.guild_id == guild_id, Game.name == name.strip())
    )
    return result.scalars().one_or_none()


async def get_game_by_scheduling_channel(session: AsyncSession, guild_id: int, channel_id: int) -> Game | None:
    result = await session.execute(
        select(Game).where(Game.guild_id == guild_id, Game.text_scheduling_id == channel_id)
    )
    return result.scalars().one_or_none()


async def count_games_where_dm(session: AsyncSession, guild_id: int, user_id: int) -> int:
    """Return how many games in this guild have this user as DM."""
    from sqlalchemy import func
    result = await session.execute(
        select(func.count()).select_from(Game).where(Game.guild_id == guild_id, Game.dm_user_id == user_id)
    )
    return result.scalar() or 0


async def get_player_ids(session: AsyncSession, game_id: int) -> set[int]:
    result = await session.execute(select(Player.user_id).where(Player.game_id == game_id))
    return {r[0] for r in result.all()}


async def get_character_name_for_voice_channel(
    session: AsyncSession, guild_id: int, channel_id: int, user_id: int
) -> str | None:
    """Return the game character name for this user in this voice channel, or None."""
    result = await session.execute(
        select(Game).where(
            Game.guild_id == guild_id,
            (Game.voice_game_id == channel_id) | (Game.voice_private_id == channel_id),
        )
    )
    game = result.scalars().one_or_none()
    if not game:
        return None
    if game.dm_user_id == user_id:
        return getattr(game, "dm_character_name", None) or None
    player_result = await session.execute(
        select(Player).where(Player.game_id == game.id, Player.user_id == user_id)
    )
    player = player_result.scalars().one_or_none()
    if not player:
        return None
    return getattr(player, "character_name", None) or None
