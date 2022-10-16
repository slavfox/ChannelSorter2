# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import discord
from discord.ext import commands
from discord.ext.commands import check
from models import AutoThreadChannel, Guild
from util.channel_sorting import reposition_channel
from util.discord_objects import (
    get_archive_category,
    get_log_channel,
    get_project_categories,
)

from breadbot.bot import bot
from breadbot.util.checks import (
    guild_supports_project_channels,
    is_admin_or_channel_owner,
    is_thread_op,
)


@bot.command()
@commands.guild_only()
@check(guild_supports_project_channels)
@check(is_admin_or_channel_owner)
async def pin(ctx: discord.ext.commands.Context):
    """Pin a message in the current channel."""
    if not ctx.message.reference:
        await ctx.send("You must reply to a message to pin it.")
        return

    message = ctx.message.reference.resolved
    if not message:
        await ctx.send("You must reply to a message to pin it.")
        return

    await message.pin()
    await ctx.message.delete()


@bot.command()
@commands.guild_only()
@check(guild_supports_project_channels)
@check(is_admin_or_channel_owner)
async def unpin(ctx: discord.ext.commands.Context):
    """Unpin a message in the current channel."""
    if not ctx.message.reference:
        await ctx.send("You must reply to a message to unpin it.")
        return

    message = ctx.message.reference.resolved
    if not message:
        await ctx.send("You must reply to a message to unpin it.")
        return

    await message.unpin()
    await ctx.message.delete()


@bot.command()
@commands.guild_only()
@check(guild_supports_project_channels)
@check(is_admin_or_channel_owner)
async def delete(ctx: discord.ext.commands.Context):
    """Delete a message in the current channel."""
    if not ctx.message.reference:
        await ctx.send("You must reply to a message to delete it.")
        return

    message = ctx.message.reference.resolved
    if not message:
        await ctx.send("You must reply to a message to delete it.")
        return

    await message.delete()
    await ctx.message.delete()


@bot.command()
@commands.guild_only()
@check(is_thread_op)
async def rename_thread(ctx: discord.ext.commands.Context, *, name: str):
    """Rename a thread."""
    await ctx.channel.edit(name=name)
    await ctx.message.delete()


@bot.command()
@commands.guild_only()
@check(is_thread_op)
async def archive_thread(ctx: discord.ext.commands.Context):
    """Archive a thread."""
    await ctx.channel.edit(archived=True)
    await ctx.message.delete()


@bot.listen("on_message")
async def on_message(message: discord.Message) -> None:
    """Listen for messages in archived channels to unarchive them."""
    if (not isinstance(message.guild, discord.Guild)) or message.author.bot:
        return

    if not isinstance(message.channel, discord.TextChannel):
        return

    guild = await Guild.get_or_none(id=message.guild.id).prefetch_related(
        "project_channels", "project_categories"
    )
    if not guild:
        return

    autothread_channel = await AutoThreadChannel.get_or_none(
        id=message.channel.id,
        guild=guild,
    )
    if autothread_channel:
        await message.create_thread(
            name="Discussion thread", auto_archive_duration=1440
        )

    archive_category = get_archive_category(message.guild, guild)
    if not archive_category:
        return

    if message.channel.category == archive_category:
        everyone = discord.utils.get(message.guild.roles, name="@everyone")
        assert everyone is not None
        await message.channel.set_permissions(everyone, overwrite=None)
        await reposition_channel(
            message.channel, get_project_categories(message.guild, guild)
        )
        log_channel = get_log_channel(message.guild, guild)
        if log_channel:
            await log_channel.send(
                f"Channel {message.channel.mention} unarchived."
            )
        await message.channel.send("Channel unarchived!")
