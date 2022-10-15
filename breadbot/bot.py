# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""/r/ProgrammingLanguages discord channel management bot."""
import sys
import traceback
from pathlib import Path

import discord
from discord.ext import commands, tasks
from tortoise import Tortoise

from breadbot import BASE_DIR
from breadbot.models import Guild
from breadbot.util.channel_sorting import reposition_channel
from breadbot.util.discord_objects import (
    get_log_channel,
    get_project_categories,
)
from breadbot.util.random import get_random_top100_steam_game
from breadbot.util.usernames import maybe_normalize_nickname

channels_path = Path(__file__).parent / "categories.txt"
notifs_path = Path(__file__).parent / "notify.json"
channel_sars = Path(__file__).parent / "channel_roles.json"


class ChannelBot(commands.Bot):
    """Discordpy bot subclass with convenience methods we need."""

    @tasks.loop(hours=1)
    async def hourly_update(self):
        """Clean up channel list and cycle presence."""
        from breadbot.util.channel_sorting import sort_inner
        from breadbot.util.periodic_tasks import (
            archive_inactive_inner,
            cleanup_db,
            delete_dead_channels,
        )
        from breadbot.util.usernames import maybe_normalize_nickname

        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="over the project channels",
            )
        )
        try:
            for guild in self.guilds:
                guild_obj = await Guild.get_or_none(
                    id=guild.id
                ).prefetch_related("project_channels", "project_categories")
                if not guild_obj:
                    continue
                log_channel = get_log_channel(guild, guild_obj)
                if log_channel is None:
                    continue
                print(f"Running hourly update in {guild.name}")
                print(f"Archiving inactive channels")
                await archive_inactive_inner(
                    guild, guild_obj, log_channel, verbose=False
                )
                print(f"Deleting dead channels")
                await delete_dead_channels(
                    guild, guild_obj, log_channel, verbose=False
                )
                print(f"Sorting channels")
                await sort_inner(guild, guild_obj, log_channel, verbose=True)
                print(f"Cleaning db")
                await cleanup_db(guild, guild_obj, log_channel)
                print(f"Normalizing usernames")
                for member in guild.members:
                    await maybe_normalize_nickname(member)
        finally:
            await self.change_presence(
                activity=discord.Game(name=get_random_top100_steam_game())
            )
            print(f"Done!")

    async def on_ready(self):
        """Set initial presence."""
        await Tortoise.init(
            db_url=f"sqlite://{BASE_DIR / 'db.sqlite3'}",
            modules={"models": ["breadbot.models"]},
        )
        await Tortoise.generate_schemas()
        print(f"Successfully logged in as {self.user}")
        self.hourly_update.start()


bot = ChannelBot(
    command_prefix="./",
    description="/r/proglangs discord helper bot",
    intents=discord.Intents.all(),
)

CHANNEL_OWNER_PERMS = discord.PermissionOverwrite(
    send_messages=True,
    read_messages=True,
    view_channel=True,
    manage_channels=True,
    manage_webhooks=True,
    # manage_threads=True,
    manage_messages=True,
)


@bot.event
async def on_member_join(member: discord.Member) -> None:
    """Normalize usernames for new members."""
    await maybe_normalize_nickname(member)


@bot.event
async def on_member_update(
    before: discord.Member, after: discord.Member
) -> None:
    """Normalize usernames on update."""
    await maybe_normalize_nickname(after)


@bot.event
async def on_command_error(ctx, exception):
    """Handle command errors by sending the stringified exception back."""
    await ctx.reply(str(exception))
    traceback.print_exception(
        type(exception), exception, exception.__traceback__, file=sys.stderr
    )


@bot.event
async def on_guild_channel_update(before, after):
    """Move channels to the correct position if they got renamed."""
    if not isinstance(after, discord.TextChannel):
        return
    guild = await Guild.get_or_none(id=after.guild.id).prefetch_related(
        "project_channels", "project_categories"
    )
    if not guild:
        return
    categories = get_project_categories(before.guild, guild)
    if not (after.category in categories and after.name != before.name):
        return
    await get_log_channel(before.guild, guild).send(
        f"Channel {before.mention} was renamed: {before.name} -> {after.name}"
    )
    await reposition_channel(after, categories)
