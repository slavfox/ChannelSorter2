# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import asyncio
from io import BytesIO

import discord
from discord.ext import commands
from discord.ext.commands import check

from breadbot.bot import bot
from breadbot.models import Guild, ProjectChannel
from breadbot.util.channel_sorting import reposition_channel, sort_inner
from breadbot.util.checks import (
    guild_supports_project_channels,
    is_admin_or_channel_owner,
)
from breadbot.util.discord_objects import (
    get_archive_category,
    get_log_channel,
    get_project_categories,
)
from breadbot.util.export import dump_channel_contents
from breadbot.util.periodic_tasks import delete_channel_inner


@bot.command()
@commands.has_permissions(administrator=True)
@commands.guild_only()
@check(guild_supports_project_channels)
async def make_channel(ctx, owner: discord.Member, name: str):
    """Create a new project channel and role."""
    # Fetch the guild from the database
    guild = await Guild.get(id=ctx.guild.id).prefetch_related(
        "project_categories"
    )

    await ctx.send(f"Creating channel {name} for {owner.mention}...")

    # Create the role and channel
    role = await ctx.guild.create_role(
        name=f"lang: {name.capitalize()}",
        colour=discord.Colour.default(),
        mentionable=True,
    )

    overwrites = {}
    channelbot_role = discord.utils.get(ctx.guild.roles, name="Channel Bot")
    if channelbot_role:
        overwrites[channelbot_role] = discord.PermissionOverwrite(
            view_channel=False
        )

    muted_role = discord.utils.get(ctx.guild.roles, name="muted")
    if muted_role:
        overwrites[muted_role] = discord.PermissionOverwrite(
            send_messages=False, add_reactions=False
        )

    new_channel = await ctx.guild.create_text_channel(
        name=name, overwrites=overwrites
    )
    await ProjectChannel.create(
        id=new_channel.id,
        guild=guild,
        owner_role=role.id,
    )

    await reposition_channel(
        new_channel,
        get_project_categories(ctx.guild, guild),
    )
    await ctx.send(f"Created channel {new_channel.mention}.")

    lang_owner_role = ctx.guild.get_role(guild.channel_owner_role_id)
    await owner.add_roles(role, lang_owner_role)
    await ctx.send(f"Created and assigned role {role.mention}.")

    await sort_inner(ctx.guild, guild, ctx.channel, verbose=True)
    await ctx.send(f"✅ Done!")


@bot.command()
@commands.guild_only()
@check(is_admin_or_channel_owner)
async def rename_channel(ctx, *, name: str):
    """Rename a channel."""
    prev_name = ctx.channel.name
    await ctx.channel.edit(name=name)
    await ctx.send(f"Renamed channel {prev_name} -> {ctx.channel.mention}.")
    pc = await ProjectChannel.get_or_none(id=ctx.channel.id)
    if pc:
        role = ctx.guild.get_role(pc.owner_role)
        if role:
            await role.edit(name=f"lang: {name}")
            await ctx.send(f"Renamed role {role.mention} -> {name}.")


@bot.command()
@commands.guild_only()
@commands.has_permissions(administrator=True)
async def set_project_role(ctx, role: discord.Role):
    """Assign a role to the current channel."""
    guild = await Guild.get(id=ctx.guild.id)
    pc, _ = await ProjectChannel.get_or_create(
        id=ctx.channel.id,
        defaults={"guild": guild, "owner_role": role.id},
    )
    pc.owner_role = role.id
    await pc.save()
    await ctx.send(f"Assigned role {role.mention} to {ctx.channel.mention}.")


@bot.command()
@commands.guild_only()
@check(is_admin_or_channel_owner)
async def archive(ctx):
    """Archive a channel."""
    guild = await Guild.get(id=ctx.guild.id)
    await ctx.send("Archiving channel.")
    await get_log_channel(ctx.guild, guild).send(
        f"Channel {ctx.channel.mention} archived manually by owner."
    )
    await ctx.channel.edit(category=get_archive_category(ctx.guild, guild))
    everyone = discord.utils.get(ctx.guild.roles, name="@everyone")
    await ctx.channel.set_permissions(everyone, send_messages=False)
    pc = await ProjectChannel.get(id=ctx.channel.id)
    owner_role = discord.utils.get(ctx.guild.roles, id=pc.owner_role)
    await ctx.channel.set_permissions(owner_role, send_messages=True)


@bot.command()
@commands.guild_only()
@check(is_admin_or_channel_owner)
async def delete_channel(ctx: discord.ext.commands.Context):
    """Delete the channel and export its history."""
    confirm_msg = await ctx.send(
        "Are you sure you want to delete this channel forever? "
        "React with 👍 within 30 seconds to confirm."
    )

    def check(reaction, user):
        return (
            user == ctx.author
            and reaction.message.id == confirm_msg.id
            and str(reaction.emoji) == "👍"
        )

    try:
        await bot.wait_for("reaction_add", timeout=30.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send("Timed out. Cancelling.")
        return

    await ctx.send("Exporting channel history. This may take a while...")
    await delete_channel_inner(
        ctx.channel, ctx.guild, await Guild.get(id=ctx.guild.id)
    )


@bot.command()
@commands.guild_only()
@check(is_admin_or_channel_owner)
async def export(ctx: discord.ext.commands.Context):
    """Upload a file with the full history of the channel."""
    await ctx.send("Exporting channel history. This may take a while...")
    io = BytesIO()
    await dump_channel_contents(ctx.channel, io)
    io.seek(0)
    await ctx.send(
        "✅ Done!",
        file=discord.File(io, filename=f"history.txt"),
    )


def get_langbot(guild: discord.Guild) -> discord.Member:
    """Get a reference to LangBot."""
    langbot = discord.utils.get(guild.members, id=969984431693627533)
    if langbot is None:
        raise discord.ext.commands.MemberNotFound("LangBot")
    return langbot


@bot.command()
@commands.guild_only()
@check(is_admin_or_channel_owner)
async def enable_langbot(ctx):
    """Enable Langbot to view this channel."""
    langbot = get_langbot(ctx.guild)
    if langbot in ctx.channel.overwrites:
        if ctx.channel.overwrites[langbot].view_channel:
            await ctx.send("✅ Langbot is already enabled in this channel.")
            return
    await ctx.channel.set_permissions(langbot, view_channel=True)
    await ctx.send("✅ Langbot enabled.")


@bot.command()
@commands.guild_only()
@check(is_admin_or_channel_owner)
async def disable_langbot(ctx):
    """Prevent Langbot from viewing this channel."""
    langbot = get_langbot(ctx.guild)
    if (
        langbot not in ctx.channel.overwrites
        or not ctx.channel.overwrites[langbot].view_channel
    ):
        await ctx.send("✅ Langbot is already disabled in this channel.")
        return
    await ctx.channel.set_permissions(langbot, overwrite=None)
    await ctx.send("✅ Langbot disabled.")


@bot.command()
@commands.guild_only()
@commands.has_permissions(administrator=True)
@check(guild_supports_project_channels)
async def sort(ctx: discord.ext.commands.Context):
    """Sort project channels."""
    await ctx.send("Sorting project channels...")
    guild = await Guild.get(id=ctx.guild.id).prefetch_related(
        "project_channels", "project_categories"
    )
    await sort_inner(ctx.guild, guild, ctx.channel)
    await ctx.send("Done!")


@bot.command()
@commands.guild_only()
@check(is_admin_or_channel_owner)
async def enable_full_perms(ctx: discord.ext.commands.Context):
    """Opt into full permissions for this channel. Requires 2FA."""
    project_channel = await ProjectChannel.get_or_none(id=ctx.channel.id)
    if project_channel is None:
        await ctx.send("This channel is not a project channel.")
        return

    role = ctx.guild.get_role(project_channel.owner_role)
    if role is None:
        await ctx.send("Project role not found, contact an admin.")
        return

    await ctx.channel.set_permissions(
        role,
        manage_messages=True,
        manage_channels=True,
        manage_threads=True,
        manage_webhooks=True,
    )
    await ctx.send("Done!")


@bot.command()
@commands.guild_only()
@check(is_admin_or_channel_owner)
async def disable_full_perms(ctx: discord.ext.commands.Context):
    """Opt out of full permissions and the 2FA requirement for this channel."""
    project_channel = await ProjectChannel.get_or_none(id=ctx.channel.id)
    if project_channel is None:
        await ctx.send("This channel is not a project channel.")
        return

    role = ctx.guild.get_role(project_channel.owner_role)
    if role is None:
        await ctx.send("Project role not found, contact an admin.")
        return

    await ctx.channel.set_permissions(
        role,
        manage_messages=False,
        manage_channels=False,
        manage_threads=False,
        manage_webhooks=False,
    )
    await ctx.send("Done!")


@bot.command()
@commands.guild_only()
@check(is_admin_or_channel_owner)
async def set_topic(ctx: discord.ext.commands.Context, *, topic: str):
    """Set the topic of the channel."""
    await ctx.channel.edit(topic=topic)
    await ctx.send("Done!")
