# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from discord.ext.commands import Bot, CheckFailure, Context

from breadbot.models import Guild, ProjectChannel


async def guild_supports_project_channels(ctx: Context[Bot]) -> bool:
    """Check if the guild supports project channels."""
    guild = await Guild.get_or_none(id=ctx.guild.id).prefetch_related(
        "project_categories"
    )
    if (
        guild is None
        or len(guild.project_categories) == 0
        or guild.channel_owner_role_id is None
    ):
        raise CheckFailure(
            "This guild has not been set up for use with BreadBot."
        )
    return True


async def guild_fully_set_up(ctx: Context[Bot]) -> bool:
    """Check if the guild supports project channels."""
    guild = await Guild.get_or_none(id=ctx.guild.id).prefetch_related(
        "project_categories"
    )
    if (
        guild is None
        or len(guild.project_categories) == 0
        or guild.channel_owner_role_id is None
        or guild.archive_category_id is None
        or guild.archive_channel_id is None
    ):
        raise CheckFailure(
            "This guild is not fully set up for project "
            "channels. Contact an admin."
        )
    return True


async def is_admin_or_channel_owner(ctx: Context[Bot]) -> bool:
    """Check if the user is an admin or channel owner."""
    if ctx.author.guild_permissions.administrator:
        return True

    project_channel = await ProjectChannel.get_or_none(id=ctx.channel.id)
    if project_channel is None:
        raise CheckFailure("This channel is not a project channel.")
    if project_channel.owner_role not in [
        role.id for role in ctx.author.roles
    ]:
        raise CheckFailure("You are not the owner of this channel.")
    return True
