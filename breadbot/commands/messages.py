# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import discord
from discord.ext import commands
from discord.ext.commands import check

from breadbot.bot import bot
from breadbot.util.checks import (
    guild_supports_project_channels,
    is_admin_or_channel_owner,
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
