# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import discord
from discord import Guild as DiscordGuild

from breadbot.models import Guild, ProjectChannel


def get_log_channel(
    discord_guild: DiscordGuild, guild: Guild
) -> discord.TextChannel | None:
    """Get the log channel for a guild."""
    return discord_guild.get_channel(guild.log_channel_id)  # type: ignore


def get_archive_channel(
    discord_guild: DiscordGuild, guild: Guild
) -> discord.TextChannel | None:
    """Get the archive channel for a guild."""
    return discord_guild.get_channel(guild.archive_channel_id)  # type: ignore


def get_archive_category(
    discord_guild: DiscordGuild, guild: Guild
) -> discord.CategoryChannel | None:
    """Get the archive category for a guild."""
    return discord_guild.get_channel(guild.archive_category_id)  # type: ignore


def get_project_categories(
    discord_guild: DiscordGuild, guild: Guild
) -> list[discord.CategoryChannel]:
    """Get the project categories for a guild."""
    return sorted(
        [
            discord_guild.get_channel(category.id)
            for category in guild.project_categories
        ],
        key=lambda c: c.name,
    )


async def clean_get_project_role(
    discord_guild: DiscordGuild,
    project_channel: ProjectChannel,
    log_callback,
) -> discord.Role | None:
    """
    Get the project role for a project channel, delete the
    ProjectChannel if the role doesn't exist.
    """
    role = discord_guild.get_role(project_channel.owner_role)
    if role is None:
        await project_channel.delete()
        await log_callback(
            f"Could not find role for channel, unregistering as project."
        )
    return role
