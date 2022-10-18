# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import discord
from discord.ext import commands

from breadbot.bot import bot
from breadbot.models import AutoThreadChannel, Guild, ProjectCategory


@bot.command()
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def get_categories(ctx):
    """Get the names of the project categories."""
    guild = await Guild.get_or_none(id=ctx.guild.id).prefetch_related(
        "project_categories"
    )
    project_categories = []
    if guild is not None:
        for category in guild.project_categories:
            category_channel = ctx.guild.get_channel(category.id)
            if category_channel is None:
                await category.delete()
                continue
            project_categories.append(category_channel.name)
    await ctx.send(f"Project categories: {project_categories}")


@bot.command()
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def set_log_channel(ctx, channel: discord.TextChannel):
    """Set the log channel."""
    guild, _ = await Guild.get_or_create(id=ctx.guild.id)
    guild.log_channel_id = channel.id
    await guild.save()
    await ctx.send(f"Log channel set to {channel.mention}.")


@bot.command()
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def set_archive_channel(ctx, channel: discord.TextChannel):
    """Set the archive channel."""
    guild, _ = await Guild.get_or_create(id=ctx.guild.id)
    guild.archive_channel_id = channel.id
    await guild.save()
    await ctx.send(f"Archive channel set to {channel.mention}.")


@bot.command()
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def unset_archive_channel(ctx):
    """Unset the archive channel."""
    guild = await Guild.get_or_none(id=ctx.guild.id)
    if guild is None:
        await ctx.send("Archive channel is not set.")
        return
    guild.archive_channel_id = None
    await guild.save()
    await ctx.send("Archive channel unset.")


@bot.command()
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def set_archive_category(ctx, category: discord.CategoryChannel):
    """Set the archive category."""
    guild, _ = await Guild.get_or_create(id=ctx.guild.id)
    guild.archive_category_id = category.id
    await guild.save()
    await ctx.send(f"Archive category set to {category.mention}.")


@bot.command()
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def unset_archive_category(ctx):
    """Unset the archive category."""
    guild = await Guild.get_or_none(id=ctx.guild.id)
    if guild is None:
        await ctx.send("Archive category is not set.")
        return
    guild.archive_category_id = None
    await guild.save()
    await ctx.send("Archive category unset.")


@bot.command()
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def set_channel_owner_role(ctx, role: discord.Role):
    """Set the channel owner role."""
    guild, _ = await Guild.get_or_create(id=ctx.guild.id)
    guild.channel_owner_role_id = role.id
    await guild.save()
    await ctx.send(f"Channel owner role set to {role.mention}.")


@bot.command()
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def unset_channel_owner_role(ctx):
    """Unset the channel owner role."""
    guild = await Guild.get_or_none(id=ctx.guild.id)
    if guild is None:
        await ctx.send("Channel owner role is not set.")
        return
    guild.channel_owner_role_id = None
    await guild.save()
    await ctx.send("Channel owner role unset.")


@bot.command()
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def set_project_categories(ctx, *categories: discord.CategoryChannel):
    """Set the ids of the project categories."""
    guild = await Guild.get_or_none(id=ctx.guild.id)
    if guild is None:
        await ctx.send(
            "This server is not registered. Please register a log channel "
            "first."
        )
        return
    for category in categories:
        _, created = await ProjectCategory.get_or_create(
            id=category.id, guild=guild
        )
        if not created:
            await ctx.send(f"{category.name} is already a project category.")
    await ctx.send(f"Done!")


@bot.command()
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def unset_project_categories(ctx, *categories: discord.CategoryChannel):
    """Unregister project categories."""
    guild = await Guild.get_or_none(id=ctx.guild.id)
    if guild is None:
        await ctx.send(
            "This server is not registered. Please register a log channel "
            "first."
        )
        return
    for category in categories:
        cat = await ProjectCategory.get_or_none(id=category.id, guild=guild)
        if not cat:
            await ctx.send(f"{category.name} is not a project category.")
            continue
        await cat.delete()
    await ctx.send(f"Done!")


@bot.command()
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def enable_autothreading(ctx, *channels: discord.TextChannel):
    """Enable autothreading in the given channels."""
    guild = await Guild.get_or_none(id=ctx.guild.id)
    if guild is None:
        await ctx.send(
            "This server is not registered. Please register a log channel "
            "first."
        )
        return
    for channel in channels:
        _, created = await AutoThreadChannel.get_or_create(
            id=channel.id, guild=guild
        )
        if not created:
            await ctx.send(f"{channel.name} is already autothreading.")
    await ctx.send(f"Done!")


@bot.command()
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def disable_autothreading(ctx, *channels: discord.TextChannel):
    """Disable autothreading in the given channels."""
    guild = await Guild.get_or_none(id=ctx.guild.id)
    if guild is None:
        await ctx.send(
            "This server is not registered. Please register a log channel "
            "first."
        )
        return
    for channel in channels:
        cat = await AutoThreadChannel.get_or_none(id=channel.id, guild=guild)
        if not cat:
            await ctx.send(f"{channel.name} is not autothreading.")
            continue
        await cat.delete()
    await ctx.send(f"Done!")
