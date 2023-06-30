# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import discord
from discord.ext import commands
from discord.ext.commands import check

from breadbot.bot import bot
from breadbot.models import AutoThreadChannel, Guild
from breadbot.util.channel_sorting import reposition_channel
from breadbot.util.checks import (
    guild_supports_project_channels,
    is_admin_or_channel_owner,
    is_thread_op_or_admin,
)
from breadbot.util.discord_objects import (
    get_archive_category,
    get_log_channel,
    get_project_categories,
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
@check(is_thread_op_or_admin)
async def rename_thread(ctx: discord.ext.commands.Context, *, name: str):
    """Rename a thread."""
    await ctx.channel.edit(name=name)
    await ctx.message.delete()


@bot.command()
@commands.guild_only()
@check(is_thread_op_or_admin)
async def archive_thread(ctx: discord.ext.commands.Context):
    """Archive a thread."""
    await ctx.message.delete()
    await ctx.channel.edit(archived=True)


@bot.command(aliases=["portal"])
@commands.guild_only()
async def goto(
    ctx: discord.ext.commands.Context,
    channel: discord.TextChannel | discord.Thread,
):
    """Redirect conversation to a different channel."""
    assert channel != ctx.channel
    target_embed = discord.Embed(
        title=f"COMEFROM {ctx.channel.mention}",
        description=f"{ctx.author.mention} redirected conversation from "
        f"{ctx.channel.mention} here.\nClick the title of this embed to "
        f"see the previous messages in this topic.",
        url=ctx.message.jump_url,
        color=discord.Color.random(),
    )
    target_msg = await channel.send(embed=target_embed)
    source_embed = discord.Embed(
        title=f"GOTO {channel.mention}",
        description=f"{ctx.author.mention} redirected conversation to "
        f"{channel.mention}.\nClick the title of this embed to proceed to "
        f"the continuation of this topic.",
        url=target_msg.jump_url,
        color=discord.Color.random(),
    )
    await ctx.send(embed=source_embed)


@bot.listen("on_message")
async def on_message(message: discord.Message) -> None:
    """Listen for messages in archived channels to unarchive them."""
    if (not isinstance(message.guild, discord.Guild)) or message.author.bot:
        return

    print(
        f"{message.created_at} "
        f"{message.author.name}#{message.author.discriminator} "
        f"[#{message.channel.name}]: "
        f"{message.content}"
    )

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
        thread_name = (
            message.clean_content.split("\n")[0].split("```")[0][:100]
            or f"{message.author.display_name} discussion thread"
        )
        thread = await message.create_thread(
            name=thread_name,
            auto_archive_duration=1440,
        )
        await thread.send(
            "If you're the OP, send `./rename_thread <new name>` to rename "
            "this thread, or `./archive_thread` to archive it."
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
