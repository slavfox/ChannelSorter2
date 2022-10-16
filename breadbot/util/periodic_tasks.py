# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from datetime import datetime, timedelta
from io import BytesIO
from itertools import chain

import discord

from breadbot.models import Guild, ProjectChannel
from breadbot.util.discord_objects import (
    clean_get_project_role,
    get_archive_category,
    get_archive_channel,
    get_project_categories,
)
from breadbot.util.export import dump_channel_contents


class MessageFound(Exception):
    pass


async def archive_inactive_inner(
    discord_guild: discord.Guild,
    guild: Guild,
    log_channel: discord.TextChannel,
    verbose: bool = True,
):
    """Archive project channels that have been inactive for over 90 days."""
    archive_category = get_archive_category(discord_guild, guild)
    if archive_category is None:
        return

    if verbose:
        await log_channel.send("Archiving inactive project channels.")
    archived = 0
    for channel in chain.from_iterable(
        c.channels for c in get_project_categories(discord_guild, guild)
    ):
        if not isinstance(channel, discord.TextChannel):
            continue

        # Skip new channels
        if channel.created_at > discord.utils.utcnow() - timedelta(days=30):
            continue

        try:
            async for message in channel.history(
                limit=None,
                after=datetime.now() - timedelta(days=90),
                oldest_first=True,
            ):
                if not message.author.bot:
                    raise MessageFound("Found a non-bot message!")
        except MessageFound:
            continue

        await log_channel.send(
            f"Archiving {channel.mention} due to inactivity."
        )
        await channel.send(
            "Archiving channel due to inactivity. "
            "If you're the channel owner, send a message here to unarchive."
        )
        await channel.edit(category=archive_category)
        everyone = discord.utils.get(discord_guild.roles, name="@everyone")
        assert everyone is not None
        await channel.set_permissions(everyone, send_messages=False)

        project_channel = await ProjectChannel.get_or_none(id=channel.id)
        if project_channel is None:
            await channel.send(
                "This channel was not set up with BreadBot. "
                "Please contact an administrator to unarchive."
            )
        else:
            await channel.set_permissions(
                await clean_get_project_role(
                    discord_guild, project_channel, channel.send
                ),
                send_messages=True,
            )
        archived += 1

    if verbose or archived > 0:
        await log_channel.send(f"Archived {archived} inactive channels.")


async def delete_channel_inner(
    channel: discord.TextChannel,
    discord_guild: discord.Guild,
    guild: Guild,
):
    """Handle deleting a channel."""
    pings = []
    archive_channel = get_archive_channel(discord_guild, guild)
    if archive_channel is None:
        await channel.send(
            "Archive channel not found. Delete this channel manually."
        )
        return

    lang_owner_role = discord_guild.get_role(guild.channel_owner_role_id)
    project_channel = await ProjectChannel.get_or_none(id=channel.id)
    if project_channel:
        owner_role = discord.utils.get(
            discord_guild.roles, id=project_channel.owner_role
        )
        if owner_role:
            roles_to_remove = [owner_role]
            if lang_owner_role is not None:
                roles_to_remove.append(lang_owner_role)
            for user in discord_guild.members:
                if owner_role in user.roles:
                    await user.remove_roles(
                        *roles_to_remove,
                        reason="Deleting dead channel",
                    )
                    pings.append(user)
    await project_channel.delete()
    io = BytesIO()
    await dump_channel_contents(channel, io)
    io.seek(0)
    await archive_channel.send(
        f"Log for {channel.name} "
        f""
        f"({', '.join(user.mention for user in pings)}):",
        file=discord.File(io, filename=f"history_{channel.name}.txt"),
    )
    await channel.delete(reason="Deleting dead channel.")


async def delete_dead_channels(
    discord_guild: discord.Guild,
    guild: Guild,
    log_channel: discord.TextChannel,
    verbose: bool = True,
):
    """Archive project channels that have been inactive for over 90 days."""
    archive_category = get_archive_category(discord_guild, guild)
    if archive_category is None:
        return
    archive_channel = get_archive_channel(discord_guild, guild)
    if archive_channel is None:
        return
    if verbose:
        await log_channel.send("Deleting dead project channels.")
    archived = 0
    for channel in archive_category.channels:
        if not isinstance(channel, discord.TextChannel):
            continue
        if channel.created_at > discord.utils.utcnow() - timedelta(days=30):
            continue
        try:
            async for message in channel.history(
                limit=None,
                after=discord.utils.utcnow() - timedelta(days=30 * 6),
                oldest_first=True,
            ):
                if not message.author.bot:
                    raise MessageFound("Found a non-bot message!")
        except MessageFound:
            continue

        await archive_channel.send(
            f"{channel.name} has had no activity in over three months. "
            f"Deleting..."
        )
        await delete_channel_inner(channel, discord_guild, guild)
        archived += 1

    if verbose or archived > 0:
        await log_channel.send(f"Deleted {archived} dead channels.")


async def cleanup_db(
    discord_guild: discord.Guild,
    guild: Guild,
    log_channel: discord.TextChannel,
):
    """Remove entries from the database that no longer exist."""
    async for channel in ProjectChannel.filter(guild=guild):
        if (
            discord_guild.get_channel(channel.id) is None
            or discord_guild.get_role(channel.owner_role) is None
        ):
            await channel.delete()
            await log_channel.send(
                f"Removed channel {channel.id} from the database."
            )
