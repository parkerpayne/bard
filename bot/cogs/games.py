"""Create game, delete game, add/remove players."""
from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select
from bot.db import Game, Player, async_session_factory
from bot.utils import count_games_where_dm, get_game_by_channel, get_game_by_name

if TYPE_CHECKING:
    from bot.main import Bot

log = logging.getLogger(__name__)


# ----- Channel order: important, scheduling, general, game, private -----
CHANNEL_ORDER = [
    ("important", discord.ChannelType.text),
    ("scheduling", discord.ChannelType.text),
    ("general", discord.ChannelType.text),
    ("game", discord.ChannelType.voice),
    ("private", discord.ChannelType.voice),
]

GAME_NAME_PATTERN = re.compile(r"^[\w\s\-']{1,100}$")


class DeleteGameView(discord.ui.View):
    def __init__(self, game: Game, guild: discord.Guild, *, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.game = game
        self.guild = guild
        self.confirmed = False

    @discord.ui.button(label="Delete game", style=discord.ButtonStyle.danger, custom_id="delete_confirm")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.dm_user_id:
            await interaction.response.send_message("Only the DM can confirm deletion.", ephemeral=True)
            return
        self.confirmed = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="delete_cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Cancelled.", view=None)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(content="Deletion timed out.", view=None)
            except discord.NotFound:
                pass


class TransferGameView(discord.ui.View):
    def __init__(self, game: Game, new_dm: discord.Member, *, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.game = game
        self.new_dm = new_dm
        self.confirmed = False

    @discord.ui.button(label="Transfer", style=discord.ButtonStyle.primary, custom_id="transfer_confirm")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.dm_user_id:
            await interaction.response.send_message("Only the current DM can confirm the transfer.", ephemeral=True)
            return
        self.confirmed = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="transfer_cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Transfer cancelled.", view=None)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(content="Transfer timed out.", view=None)
            except discord.NotFound:
                pass


class GamesCog(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self._register_commands()

    async def _sync_dm_resource_role(self, guild: discord.Guild, user_id: int) -> None:
        """Add or remove the generic DM resource role so it matches whether this user is DM of any game."""
        role_id_str = os.environ.get("DM_RESOURCE_ROLE_ID", "").strip()
        if not role_id_str:
            return
        try:
            role_id = int(role_id_str)
        except ValueError:
            return
        role = guild.get_role(role_id)
        member = guild.get_member(user_id)
        if not role or not member:
            return
        async with async_session_factory() as session:
            count = await count_games_where_dm(session, guild.id, user_id)
        try:
            if count >= 1:
                if role not in member.roles:
                    await member.add_roles(role)
            else:
                if role in member.roles:
                    await member.remove_roles(role)
        except discord.Forbidden:
            pass

    async def _apply_game_channel_permissions(
        self,
        guild: discord.Guild,
        role: discord.Role,
        dm_target: discord.Role | discord.Member,
        channels: dict[str, discord.abc.GuildChannel],
    ) -> None:
        """
        Set permissions per spec; anything not listed uses server defaults.
        - Category: everyone no view/manage_channels/manage_roles; game role view; DM role view + manage_channels + manage_roles.
        - Important: everyone no view; game role view, no send; DM role view, send.
        - Scheduling/General: everyone no view; game role view.
        - Game voice: everyone no view; game role view.
        - Private voice: everyone no view, no connect; game role no view, no connect; DM role view, connect, move_members.
        """
        category = channels.get("category")
        important = channels.get("important")
        scheduling = channels.get("scheduling")
        general = channels.get("general")
        voice_game = channels.get("game")
        voice_private = channels.get("private")

        # Game category: everyone cannot see/manage; game role can see only (no manage in overwrite); DM role can manage
        if category:
            await category.set_permissions(
                guild.default_role,
                view_channel=False,
                manage_channels=False,
                manage_roles=False,
            )
            await category.set_permissions(role, view_channel=True)
            await category.set_permissions(
                dm_target, view_channel=True, manage_channels=True, manage_roles=True
            )

        # Important: game role see/read only, no send; reactions and external emojis allowed; DM role can manage
        if important:
            await important.set_permissions(guild.default_role, view_channel=False)
            await important.set_permissions(
                role,
                view_channel=True,
                read_message_history=True,
                send_messages=False,
                add_reactions=True,
                use_external_emojis=True,
            )
            await important.set_permissions(
                dm_target,
                view_channel=True,
                read_message_history=True,
                send_messages=True,
                manage_channels=True,
                manage_roles=True,
            )

        # Scheduling: game role see/read/send + threads, embeds, files, reactions, stickers, mention @everyone, voice msgs, polls, slash; DM role can manage
        if scheduling:
            await scheduling.set_permissions(guild.default_role, view_channel=False)
            await scheduling.set_permissions(
                role,
                view_channel=True,
                read_message_history=True,
                send_messages=True,
                send_messages_in_threads=True,
                create_public_threads=True,
                create_private_threads=True,
                embed_links=True,
                attach_files=True,
                add_reactions=True,
                use_external_emojis=True,
                use_external_stickers=True,
                mention_everyone=True,
                send_voice_messages=True,
                create_polls=True,
                use_application_commands=True,
            )
            await scheduling.set_permissions(
                dm_target,
                view_channel=True,
                read_message_history=True,
                manage_channels=True,
                manage_roles=True,
            )

        # General: game role see/read/send + threads, embeds, files, reactions, stickers, mention @everyone, voice msgs, polls, slash; DM role can manage
        if general:
            await general.set_permissions(guild.default_role, view_channel=False)
            await general.set_permissions(
                role,
                view_channel=True,
                read_message_history=True,
                send_messages=True,
                send_messages_in_threads=True,
                create_public_threads=True,
                create_private_threads=True,
                embed_links=True,
                attach_files=True,
                add_reactions=True,
                use_external_emojis=True,
                use_external_stickers=True,
                mention_everyone=True,
                send_voice_messages=True,
                create_polls=True,
                use_application_commands=True,
            )
            await general.set_permissions(
                dm_target,
                view_channel=True,
                read_message_history=True,
                manage_channels=True,
                manage_roles=True,
            )

        # Game voice: same structure as private — game role see/connect/speak; DM role full (view, connect, speak, manage)
        if voice_game:
            await voice_game.set_permissions(guild.default_role, view_channel=False)
            await voice_game.set_permissions(
                role, view_channel=True, connect=True, speak=True, use_voice_activation=True
            )
            await voice_game.set_permissions(
                dm_target,
                view_channel=True,
                connect=True,
                speak=True,
                use_voice_activation=True,
                move_members=True,
                manage_channels=True,
                manage_roles=True,
            )

        # Private voice: game role no view/connect; DM role can see, join, speak, move members, manage
        if voice_private:
            await voice_private.set_permissions(
                guild.default_role, view_channel=False, connect=False
            )
            await voice_private.set_permissions(role, view_channel=False, connect=False)
            await voice_private.set_permissions(
                dm_target,
                view_channel=True,
                connect=True,
                speak=True,
                use_voice_activation=True,
                move_members=True,
                manage_channels=True,
                manage_roles=True,
            )

    async def sync_all_game_permissions(self) -> None:
        """
        On startup: ensure every existing game's channels have the correct permissions
        (category/game role/DM role; important game role see/no send, DM see/send;
        scheduling/general game role see; game voice game role see;
        private everyone/game no view no connect, DM see/connect/move_members).
        """
        async with async_session_factory() as session:
            result = await session.execute(select(Game))
            games = result.scalars().all()
        for game in games:
            guild = self.bot.get_guild(game.guild_id)
            if not guild:
                continue
            role = guild.get_role(game.game_role_id)
            if not role:
                log.warning("Game %s: game role %s not found, skipping permission sync", game.name, game.game_role_id)
                continue
            dm_role_id = getattr(game, "dm_role_id", None)
            dm_target: discord.Role | discord.Member | None = guild.get_role(dm_role_id) if dm_role_id else None
            if not dm_target:
                dm_member = guild.get_member(game.dm_user_id)
                if dm_member:
                    dm_target = dm_member  # legacy: no dm_role, use member overwrites
                else:
                    log.warning("Game %s: no DM role and DM member not found, skipping", game.name)
                    continue
            category = guild.get_channel(game.category_id)
            if not category or not isinstance(category, discord.CategoryChannel):
                log.warning("Game %s: category not found, skipping permission sync", game.name)
                continue
            channels = {
                "category": category,
                "important": guild.get_channel(game.text_important_id),
                "scheduling": guild.get_channel(game.text_scheduling_id),
                "general": guild.get_channel(game.text_general_id),
                "game": guild.get_channel(game.voice_game_id),
                "private": guild.get_channel(game.voice_private_id),
            }
            if not all(channels.values()):
                log.warning("Game %s: one or more channels missing, skipping permission sync", game.name)
                continue
            try:
                await self._apply_game_channel_permissions(guild, role, dm_target, channels)
                log.info("Synced channel permissions for game %s", game.name)
            except discord.Forbidden as e:
                log.warning("Game %s: permission sync failed (forbidden): %s", game.name, e)
            except Exception as e:
                log.exception("Game %s: permission sync failed: %s", game.name, e)

    def _register_commands(self):
        self.bot.tree.add_command(
            app_commands.command(name="create-game", description="Create a new D&D game")(self.create_game)
        )
        self.bot.tree.add_command(
            app_commands.command(name="delete-game", description="Delete a game (DM only, use outside game channels)")(
                self.delete_game
            )
        )
        game_group = app_commands.Group(name="game", description="Game management (use in game text channels)")
        game_group.add_command(
            app_commands.describe(user="Member to add")(app_commands.command(name="add-player")(self.add_player))
        )
        game_group.add_command(
            app_commands.describe(user="Member to remove")(
                app_commands.command(name="remove-player")(self.remove_player)
            )
        )
        game_group.add_command(
            app_commands.command(name="info", description="List the DM and players for this game")(
                self.game_info
            )
        )
        game_group.add_command(
            app_commands.describe(user="Member who will become the new DM")(
                app_commands.command(name="transfer", description="Transfer game ownership to another member (current DM only)")(self.game_transfer)
            )
        )
        game_group.add_command(
            app_commands.describe(name="Your character name for this game (e.g. for voice)")(
                app_commands.command(name="set-nickname", description="Set your game-specific character name")(self.game_set_nickname)
            )
        )
        game_group.add_command(
            app_commands.command(name="remove-nickname", description="Remove your game-specific character name")(
                self.game_remove_nickname
            )
        )
        game_group.add_command(
            app_commands.describe(
                ignore="Comma-separated category names to skip (default: General, Archives, DM Tools)",
                create_missing="Recreate any missing game channels (default: yes)",
            )(
                app_commands.command(
                    name="rebuild",
                    description="Rebuild the game database by scanning this server (use after data loss)",
                )(self.game_rebuild)
            )
        )
        game_group.add_command(
            app_commands.describe(name="Name of the game to unregister")(
                app_commands.command(
                    name="forget",
                    description="Remove a game from the database WITHOUT deleting its channels",
                )(self.game_forget)
            )
        )
        self.bot.tree.add_command(game_group)

    async def create_game(self, interaction: discord.Interaction, name: str):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        name = name.strip()
        if not name:
            await interaction.response.send_message("Game name cannot be empty.", ephemeral=True)
            return
        if not GAME_NAME_PATTERN.match(name):
            await interaction.response.send_message(
                "Game name can only contain letters, numbers, spaces, hyphens, and apostrophes (max 100 chars).",
                ephemeral=True,
            )
            return
        async with async_session_factory() as session:
            existing = await get_game_by_name(session, interaction.guild.id, name)
            if existing:
                await interaction.response.send_message(f"A game named **{name}** already exists.", ephemeral=True)
                return

        await interaction.response.defer(ephemeral=True)
        try:
            guild = interaction.guild
            role = await guild.create_role(name=f"Game: {name}", mentionable=False)
            dm_role = await guild.create_role(
                name=f"DM: {name}",
                mentionable=False,
                permissions=discord.Permissions(move_members=True),  # move players between voice channels
            )
            # DM role above game role so DM overwrites take precedence when user has both roles
            try:
                await dm_role.edit(position=role.position + 1)
            except discord.Forbidden:
                pass
            category = await guild.create_category(name=name)

            channel_ids = {}
            channels_for_perms = {"category": category}
            for ch_name, ch_type in CHANNEL_ORDER:
                if ch_type == discord.ChannelType.text:
                    ch = await guild.create_text_channel(ch_name, category=category)
                else:
                    ch = await guild.create_voice_channel(ch_name, category=category)
                channel_ids[ch_name] = ch.id
                if ch_name == "important":
                    channels_for_perms["important"] = ch
                elif ch_name == "scheduling":
                    channels_for_perms["scheduling"] = ch
                elif ch_name == "general":
                    channels_for_perms["general"] = ch
                elif ch_name == "game":
                    channels_for_perms["game"] = ch
                elif ch_name == "private":
                    channels_for_perms["private"] = ch

            await self._apply_game_channel_permissions(guild, role, dm_role, channels_for_perms)

            # Give DM both roles (game role for access, dm role for manage + important/private)
            await interaction.user.add_roles(role, dm_role)

            async with async_session_factory() as session:
                game = Game(
                    guild_id=guild.id,
                    name=name,
                    dm_user_id=interaction.user.id,
                    category_id=category.id,
                    game_role_id=role.id,
                    dm_role_id=dm_role.id,
                    text_important_id=channel_ids["important"],
                    text_scheduling_id=channel_ids["scheduling"],
                    text_general_id=channel_ids["general"],
                    voice_game_id=channel_ids["game"],
                    voice_private_id=channel_ids["private"],
                )
                session.add(game)
                await session.commit()
                await session.refresh(game)

            await self._sync_dm_resource_role(guild, interaction.user.id)
            await interaction.followup.send(
                f"Game **{name}** created. You are the DM. Use the **game** category and channels. "
                "Use `/game add-player` in one of the game text channels to add players.",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to create channels or roles.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Something went wrong: {e}", ephemeral=True)

    async def delete_game(self, interaction: discord.Interaction, name: str):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        async with async_session_factory() as session:
            game = await get_game_by_name(session, interaction.guild.id, name)
            if not game:
                await interaction.response.send_message(f"No game named **{name}** found.", ephemeral=True)
                return
            if game.dm_user_id != interaction.user.id:
                await interaction.response.send_message("Only the DM of that game can delete it.", ephemeral=True)
                return
            # Must be run outside game channels
            if game.is_game_text_channel(interaction.channel_id):
                await interaction.response.send_message(
                    "Run this command **outside** the game channels (e.g. in a general server channel).",
                    ephemeral=True,
                )
                return

        view = DeleteGameView(game, interaction.guild)
        await interaction.response.send_message(
            f"Delete game **{game.name}**? Every channel (voice and text) inside the category will be removed. "
            "Move any channels you want to keep out of the category before confirming.",
            view=view,
        )
        view.message = await interaction.original_response()
        await view.wait()

        if not view.confirmed:
            return

        await self._do_delete_game(interaction, view, game)

    async def _do_delete_game(self, interaction: discord.Interaction, view: DeleteGameView, game: Game):
        guild = interaction.guild
        former_dm_id = game.dm_user_id
        try:
            cat = guild.get_channel(game.category_id)
            if cat and isinstance(cat, discord.CategoryChannel):
                for ch in list(cat.channels):
                    await ch.delete()
            if cat:
                await cat.delete()
            dm_role = guild.get_role(getattr(game, "dm_role_id", None) or 0) if getattr(game, "dm_role_id", None) else None
            if dm_role:
                await dm_role.delete()
            role = guild.get_role(game.game_role_id)
            if role:
                await role.delete()
            async with async_session_factory() as session:
                g = await session.get(Game, game.id)
                if g:
                    await session.delete(g)
                await session.commit()
            await self._sync_dm_resource_role(guild, former_dm_id)
            await view.message.edit(content=f"Game **{game.name}** has been deleted.", view=None)
        except Exception as e:
            await view.message.edit(content=f"Error during deletion: {e}", view=None)

    async def game_info(self, interaction: discord.Interaction):
        """List the DM and players for this game. Use in any game text channel."""
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        async with async_session_factory() as session:
            game = await get_game_by_channel(session, interaction.guild.id, interaction.channel_id)
            if not game:
                await interaction.response.send_message(
                    "Run this command in one of the game's text channels (important, scheduling, or general).",
                    ephemeral=True,
                )
                return
            dm_member = interaction.guild.get_member(game.dm_user_id)
            dm_mention = dm_member.mention if dm_member else f"<@{game.dm_user_id}>"
            dm_display = f"{dm_mention} ({game.dm_character_name})" if getattr(game, "dm_character_name", None) else dm_mention
            result = await session.execute(select(Player).where(Player.game_id == game.id))
            players = result.scalars().all()
            if not players:
                player_list = "*No players yet.*"
            else:
                lines = []
                for p in players:
                    m = interaction.guild.get_member(p.user_id)
                    mention = m.mention if m else f"<@{p.user_id}>"
                    char = getattr(p, "character_name", None)
                    lines.append(f"{mention} ({char})" if char else mention)
                player_list = "\n".join(lines)
        embed = discord.Embed(
            title=game.name,
            description="DM and players for this game.",
            color=discord.Color.blue(),
        )
        embed.add_field(name="DM", value=dm_display, inline=False)
        embed.add_field(name="Players", value=player_list, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def game_set_nickname(self, interaction: discord.Interaction, name: str):
        """Set your game-specific character name. Use in a game text channel."""
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        name = name.strip()[:32] if name else ""
        if not name:
            await interaction.response.send_message("Please provide a character name (max 32 characters).", ephemeral=True)
            return
        async with async_session_factory() as session:
            game = await get_game_by_channel(session, interaction.guild.id, interaction.channel_id)
            if not game:
                await interaction.response.send_message(
                    "Run this command in one of the game's text channels (important, scheduling, or general).",
                    ephemeral=True,
                )
                return
            if game.dm_user_id == interaction.user.id:
                game_record = await session.get(Game, game.id)
                if game_record:
                    game_record.dm_character_name = name
                await session.commit()
                await interaction.response.send_message(f"Your character name for this game is now **{name}**.", ephemeral=True)
                return
            result = await session.execute(select(Player).where(Player.game_id == game.id, Player.user_id == interaction.user.id))
            player = result.scalars().one_or_none()
            if not player:
                await interaction.response.send_message("You are not a player in this game.", ephemeral=True)
                return
            player.character_name = name
            await session.commit()
        await interaction.response.send_message(f"Your character name for this game is now **{name}**.", ephemeral=True)

    async def game_remove_nickname(self, interaction: discord.Interaction):
        """Remove your game-specific character name. Use in a game text channel."""
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        async with async_session_factory() as session:
            game = await get_game_by_channel(session, interaction.guild.id, interaction.channel_id)
            if not game:
                await interaction.response.send_message(
                    "Run this command in one of the game's text channels (important, scheduling, or general).",
                    ephemeral=True,
                )
                return
            if game.dm_user_id == interaction.user.id:
                game_record = await session.get(Game, game.id)
                if not game_record or not game_record.dm_character_name:
                    await interaction.response.send_message("You don't have a character name set for this game.", ephemeral=True)
                    return
                game_record.dm_character_name = None
                await session.commit()
                await interaction.response.send_message("Your game character name has been removed.", ephemeral=True)
                return
            result = await session.execute(select(Player).where(Player.game_id == game.id, Player.user_id == interaction.user.id))
            player = result.scalars().one_or_none()
            if not player:
                await interaction.response.send_message("You are not a player in this game.", ephemeral=True)
                return
            if not getattr(player, "character_name", None):
                await interaction.response.send_message("You don't have a character name set for this game.", ephemeral=True)
                return
            player.character_name = None
            await session.commit()
        await interaction.response.send_message("Your game character name has been removed.", ephemeral=True)

    async def game_transfer(self, interaction: discord.Interaction, user: discord.Member):
        """Transfer game ownership to another member. Current DM only. Use in a game text channel."""
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message("You cannot transfer ownership to a bot.", ephemeral=True)
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message("You are already the DM.", ephemeral=True)
            return
        async with async_session_factory() as session:
            game = await get_game_by_channel(session, interaction.guild.id, interaction.channel_id)
            if not game:
                await interaction.response.send_message(
                    "Run this command in one of the game's text channels (important, scheduling, or general).",
                    ephemeral=True,
                )
                return
            if game.dm_user_id != interaction.user.id:
                await interaction.response.send_message("Only the current DM can transfer ownership.", ephemeral=True)
                return

        view = TransferGameView(game, user)
        await interaction.response.send_message(
            f"Transfer ownership of **{game.name}** to {user.mention}? You will become a player.",
            view=view,
        )
        view.message = await interaction.original_response()
        await view.wait()

        if not view.confirmed:
            return

        guild = interaction.guild
        old_dm_id = interaction.user.id
        new_dm = view.new_dm
        role = guild.get_role(game.game_role_id)
        dm_role_id = getattr(game, "dm_role_id", None)
        dm_role = guild.get_role(dm_role_id) if dm_role_id else None
        try:
            if dm_role:
                # Game has separate DM role: move role from old DM to new DM
                if interaction.user.get_role(dm_role.id):
                    await interaction.user.remove_roles(dm_role)
                await new_dm.add_roles(dm_role)
                if role and role not in new_dm.roles:
                    await new_dm.add_roles(role)
            else:
                # Legacy: no DM role, use member overwrites
                category = guild.get_channel(game.category_id)
                important = guild.get_channel(game.text_important_id)
                private = guild.get_channel(game.voice_private_id)
                if category:
                    await category.set_permissions(interaction.user, overwrite=None)
                    await category.set_permissions(new_dm, view_channel=True, manage_channels=True)
                if important:
                    await important.set_permissions(interaction.user, overwrite=None)
                    await important.set_permissions(role, view_channel=True, send_messages=False)
                    await important.set_permissions(new_dm, view_channel=True, send_messages=True)
                if private:
                    await private.set_permissions(interaction.user, overwrite=None)
                    await private.set_permissions(role, view_channel=False, connect=False)
                    await private.set_permissions(
                        new_dm,
                        view_channel=True,
                        connect=True,
                        speak=True,
                        use_voice_activation=True,
                        move_members=True,
                    )
                if role and role not in new_dm.roles:
                    await new_dm.add_roles(role)
            # DB: add old DM as player, remove new DM from players if present, update dm_user_id
            async with async_session_factory() as session:
                old_dm_player = await session.execute(
                    select(Player).where(Player.game_id == game.id, Player.user_id == old_dm_id)
                )
                if not old_dm_player.scalars().one_or_none():
                    session.add(Player(game_id=game.id, user_id=old_dm_id))
                new_dm_player = await session.execute(
                    select(Player).where(Player.game_id == game.id, Player.user_id == new_dm.id)
                )
                p = new_dm_player.scalars().one_or_none()
                if p:
                    await session.delete(p)
                game_record = await session.get(Game, game.id)
                if game_record:
                    game_record.dm_user_id = new_dm.id
                await session.commit()
            await self._sync_dm_resource_role(guild, new_dm.id)
            await self._sync_dm_resource_role(guild, old_dm_id)
            await view.message.edit(
                content=f"Ownership of **{game.name}** has been transferred to {new_dm.mention}. You are now a player.",
                view=None,
            )
        except discord.Forbidden:
            await view.message.edit(content="I don't have permission to update channel permissions.", view=None)
        except Exception as e:
            await view.message.edit(content=f"Something went wrong: {e}", view=None)

    async def add_player(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        async with async_session_factory() as session:
            game = await get_game_by_channel(session, interaction.guild.id, interaction.channel_id)
            if not game:
                await interaction.response.send_message(
                    "Run this command in one of the game's text channels (important, scheduling, or general).",
                    ephemeral=True,
                )
                return
            if game.dm_user_id != interaction.user.id:
                await interaction.response.send_message("Only the DM can add players.", ephemeral=True)
                return
            if user.id == game.dm_user_id:
                await interaction.response.send_message("The DM is already in the game.", ephemeral=True)
                return
            existing = await session.execute(select(Player).where(Player.game_id == game.id, Player.user_id == user.id))
            if existing.scalars().one_or_none():
                await interaction.response.send_message(f"{user.display_name} is already in the game.", ephemeral=True)
                return
            session.add(Player(game_id=game.id, user_id=user.id))
            await session.commit()

        role = interaction.guild.get_role(game.game_role_id)
        if role:
            await user.add_roles(role)
        await interaction.response.send_message(f"Added {user.mention} to the game.", ephemeral=True)

    async def remove_player(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        async with async_session_factory() as session:
            game = await get_game_by_channel(session, interaction.guild.id, interaction.channel_id)
            if not game:
                await interaction.response.send_message(
                    "Run this command in one of the game's text channels (important, scheduling, or general).",
                    ephemeral=True,
                )
                return
            if game.dm_user_id != interaction.user.id:
                await interaction.response.send_message("Only the DM can remove players.", ephemeral=True)
                return
            if user.id == game.dm_user_id:
                await interaction.response.send_message("You cannot remove the DM from the game.", ephemeral=True)
                return
            result = await session.execute(select(Player).where(Player.game_id == game.id, Player.user_id == user.id))
            player = result.scalars().one_or_none()
            if not player:
                await interaction.response.send_message("That user is not in this game.", ephemeral=True)
                return
            await session.delete(player)
            await session.commit()

        role = interaction.guild.get_role(game.game_role_id)
        if role and role in user.roles:
            await user.remove_roles(role)
        await interaction.response.send_message(f"Removed {user.mention} from the game.", ephemeral=True)


    DEFAULT_REBUILD_IGNORE = "General, Archives, DM Tools"

    async def game_rebuild(
        self,
        interaction: discord.Interaction,
        ignore: str = DEFAULT_REBUILD_IGNORE,
        create_missing: bool = True,
    ):
        """
        Reconstruct Game/Player rows by scanning the guild.

        Every category is treated as a game except the ignored ones, because a
        game's channels drift over time — renamed, deleted, moved. Missing
        channels are recreated so the row can be written and the game works
        again; existing channels are left exactly as they are.
        """
        if not interaction.guild:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        perms = interaction.user.guild_permissions
        if not (perms.administrator or perms.manage_guild):
            await interaction.response.send_message(
                "You need Manage Server to rebuild the game database.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        ignored = {n.strip().lower() for n in ignore.split(",") if n.strip()}

        rebuilt: list[str] = []
        repaired: list[str] = []
        skipped: list[str] = []
        problems: list[str] = []

        async with async_session_factory() as session:
            existing = await session.execute(select(Game).where(Game.guild_id == guild.id))
            known_categories = {g.category_id for g in existing.scalars().all()}

            for category in guild.categories:
                if category.name.strip().lower() in ignored:
                    continue
                if category.id in known_categories:
                    skipped.append(category.name)
                    continue

                try:
                    result = await self._rebuild_one_game(
                        guild, category, interaction.user, session, create_missing
                    )
                except discord.Forbidden:
                    problems.append(f"**{category.name}** — missing permissions to repair it")
                    continue
                except Exception as exc:
                    log.exception("rebuild failed for category %s", category.name)
                    problems.append(f"**{category.name}** — {type(exc).__name__}: {exc}")
                    continue

                if result is None:
                    problems.append(
                        f"**{category.name}** — no channels matched; "
                        f"add it to `ignore` if it is not a game"
                    )
                    continue

                line, created = result
                rebuilt.append(line)
                if created:
                    repaired.append(f"**{category.name}** — recreated {', '.join(created)}")

            await session.commit()

        embed = discord.Embed(
            title="Game database rebuild",
            color=discord.Color.green() if rebuilt else discord.Color.orange(),
        )
        embed.description = (
            "\n".join(f"✅ {line}" for line in rebuilt) if rebuilt
            else "No new games were found to rebuild."
        )
        if repaired:
            embed.add_field(name="Channels recreated", value="\n".join(repaired)[:1024], inline=False)
        if skipped:
            embed.add_field(name="Already in the database", value=", ".join(skipped)[:1024], inline=False)
        if problems:
            embed.add_field(name="Needs attention", value="\n".join(problems)[:1024], inline=False)
        if ignored:
            embed.set_footer(
                text=f"Ignored categories: {', '.join(sorted(ignored))} · "
                     f"character names cannot be recovered (/game set-nickname)"
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _rebuild_one_game(
        self,
        guild: discord.Guild,
        category: discord.CategoryChannel,
        invoker: discord.Member,
        session,
        create_missing: bool,
    ) -> tuple[str, list[str]] | None:
        """Rebuild one category into a Game row. Returns (summary, created_channels)."""
        wanted = dict(CHANNEL_ORDER)

        found: dict[str, discord.abc.GuildChannel] = {}
        for ch in category.channels:
            kind = (
                discord.ChannelType.voice if isinstance(ch, discord.VoiceChannel)
                else discord.ChannelType.text if isinstance(ch, discord.TextChannel)
                else None
            )
            if ch.name in wanted and kind == wanted[ch.name] and ch.name not in found:
                found[ch.name] = ch

        missing = [name for name in wanted if name not in found]
        if len(missing) == len(wanted) and not create_missing:
            return None

        # Roles: reuse what is there, create what is not.
        want_game = f"game: {category.name}".lower()
        want_dm = f"dm: {category.name}".lower()
        game_role = discord.utils.find(lambda r: r.name.lower() == want_game, guild.roles)
        dm_role = discord.utils.find(lambda r: r.name.lower() == want_dm, guild.roles)

        if game_role is None:
            game_role = await guild.create_role(name=f"Game: {category.name}", mentionable=False)
        if dm_role is None:
            dm_role = await guild.create_role(
                name=f"DM: {category.name}",
                mentionable=False,
                permissions=discord.Permissions(move_members=True),
            )

        dm_members = [m for m in dm_role.members if not m.bot]
        dm = dm_members[0] if dm_members else invoker
        if not dm_members:
            await dm.add_roles(dm_role)

        created: list[str] = []
        if create_missing:
            for name in missing:
                if wanted[name] == discord.ChannelType.text:
                    ch = await guild.create_text_channel(name, category=category)
                else:
                    ch = await guild.create_voice_channel(name, category=category)
                found[name] = ch
                created.append(name)
                # Only the channels we just made get permissions applied; the
                # ones that already existed are left untouched on purpose.
                await self._apply_game_channel_permissions(guild, game_role, dm_role, {name: ch})

        if any(name not in found for name in wanted):
            return None

        game = Game(
            guild_id=guild.id,
            name=category.name,
            dm_user_id=dm.id,
            category_id=category.id,
            game_role_id=game_role.id,
            dm_role_id=dm_role.id,
            text_important_id=found["important"].id,
            text_scheduling_id=found["scheduling"].id,
            text_general_id=found["general"].id,
            voice_game_id=found["game"].id,
            voice_private_id=found["private"].id,
        )
        session.add(game)
        await session.flush()

        players = [m for m in game_role.members if not m.bot and m.id != dm.id]
        for member in players:
            session.add(Player(game_id=game.id, user_id=member.id))

        return (
            f"**{category.name}** — DM {dm.display_name}, {len(players)} player(s)",
            created,
        )

    async def game_forget(self, interaction: discord.Interaction, name: str):
        """
        Drop a game's database rows and leave Discord untouched.

        The counterpart to /delete-game: that one tears down the category and
        channels, which is the wrong tool when a category was registered by
        mistake and you just want the bot to stop treating it as a game.
        """
        if not interaction.guild:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        async with async_session_factory() as session:
            game = await get_game_by_name(session, interaction.guild.id, name)
            if not game:
                result = await session.execute(select(Game).where(Game.guild_id == interaction.guild.id))
                names = [g.name for g in result.scalars().all()]
                await interaction.response.send_message(
                    f"No game named **{name}**."
                    + (f"\nKnown games: {', '.join(names)}" if names else " No games are registered."),
                    ephemeral=True,
                )
                return

            perms = interaction.user.guild_permissions
            if not (perms.administrator or perms.manage_guild or game.dm_user_id == interaction.user.id):
                await interaction.response.send_message(
                    "Only the DM of that game or someone with Manage Server can unregister it.",
                    ephemeral=True,
                )
                return

            game_name = game.name
            player_count = len(
                (await session.execute(select(Player).where(Player.game_id == game.id))).scalars().all()
            )
            await session.delete(game)   # players and schedule polls cascade
            await session.commit()

        await interaction.response.send_message(
            f"Removed **{game_name}** from the database ({player_count} player record(s)).\n"
            f"Its category, channels, and roles were left untouched.\n"
            f"Add it to the ignore list next time: `/game rebuild ignore: {game_name}`",
            ephemeral=True,
        )
