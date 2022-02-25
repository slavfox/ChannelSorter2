# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import os
from itertools import chain
from pathlib import Path

import discord
from discord.ext import commands

channels_path = Path(__file__).parent / "categories.txt"

bot = commands.Bot(command_prefix="./", description="/r/proglangs discord helper bot")


def get_project_categories(guild):
    with channels_path.open() as f:
        return [discord.utils.get(guild.categories, id=int(line.strip())) for line in f]


def get_archive_category(guild):
    return discord.utils.get(guild.categories, name="Archive")


def get_position_in_category(
    channel: discord.TextChannel, category: discord.CategoryChannel
):
    for i, ch in enumerate(category.channels):
        if ch.id == channel.id:
            return i
    return None


@bot.command()
@commands.has_permissions(administrator=True)
async def get_categories(ctx):
    await ctx.send(
        f"Project categories: " f"{[c.name for c in get_project_categories(ctx.guild)]}"
    )


@bot.command()
@commands.has_permissions(administrator=True)
async def set_categories(ctx, *categories: discord.CategoryChannel):
    with channels_path.open("w") as f:
        for category in categories:
            f.write(str(category.id) + "\n")
    await ctx.send(f"New project categories: {[c.name for c in categories]}")


@bot.command()
@commands.has_permissions(administrator=True)
async def sort(ctx: discord.ext.commands.Context):
    await ctx.send("Sorting channels!")
    moves_made = 0
    renames_made = 0

    categories = get_project_categories(ctx.guild)
    channels = sorted(
        chain.from_iterable(c.channels for c in categories), key=lambda ch: ch.name
    )
    category_channels = {}

    # rename project categories
    end_idx = 0
    for cat in categories:
        # Find starting letter ranges
        start_idx = end_idx
        start_letter = channels[start_idx].name[0].upper()
        end_idx = start_idx + (len(channels) // len(categories))
        if end_idx >= len(channels):
            end_letter = channels[-1].name[0].upper()
        else:
            end_letter = channels[end_idx].name[0].upper()
            while channels[end_idx].name[0].upper() == end_letter:
                end_idx += 1

        # Rename category if necessary
        new_cat_name = f"Projects {start_letter}-{end_letter}"
        if cat.name != new_cat_name:
            renames_made += 1
            print(f"Renaming {cat.name} to {new_cat_name}")
            await cat.edit(name=new_cat_name)

        # Save channels that should be in the category at the end of the run
        category_channels[cat.id] = channels[start_idx:end_idx]

    # Shuffle channels around
    for category in categories:
        for i, channel in enumerate(category_channels[category.id]):
            if channel.category_id != category.id or category.channels[i] != channel:
                old_pos = channel.position
                new_pos = category.channels[i].position
                if old_pos > new_pos:
                    # moving channel up
                    for other_channel in channels:
                        if new_pos <= other_channel.position < old_pos:
                            other_channel.position += 1
                else:
                    # moving channel down
                    for other_channel in channels:
                        if old_pos < other_channel.position <= new_pos:
                            other_channel.position -= 1
                moves_made += 1
                channel.category_id = category.id
                channel.position = new_pos
                print(f"Moving channel {channel.name}.")
                await channel.edit(
                    category=category, position=category.channels[i].position
                )

    await ctx.send(
        f"Channels sorted! Renamed {renames_made} categories and "
        f"moved {moves_made} channels."
    )


@bot.command()
@commands.has_permissions(administrator=True)
async def make_channel(ctx, owner: discord.Member, name: str):
    new_channel = await ctx.guild.create_text_channel(name=name)
    await ctx.send(f"Created channel {new_channel.mention}.")
    role = await ctx.guild.create_role(
        name=f"lang: {name.capitalize()}", colour=discord.Colour.from_rgb(155, 89, 182)
    )
    await owner.add_roles(role)
    await ctx.send(f"Created role {role.mention}.")
    channelbot_role = discord.utils.get(ctx.guild.roles, name="Channel Bot")
    muted_role = discord.utils.get(ctx.guild.roles, name="muted")
    overwrites = {
        role: discord.PermissionOverwrite(
            manage_channels=True,
            manage_permissions=True,
            manage_webhooks=True,
            # Added in pycord 2.0
            # manage_threads=True,
            manage_messages=True,
        ),
        channelbot_role: discord.PermissionOverwrite(view_channel=False),
        muted_role: discord.PermissionOverwrite(
            send_messages=False, add_reactions=False
        ),
    }
    categories = get_project_categories(ctx.guild)
    channels = []
    for cat in categories:
        channels.extend(cat.channels)
    channels = sorted(channels, key=lambda channel: channel.name)
    position = len(categories[-1].channels)
    category = categories[-1]
    for channel in channels:
        if channel.name.lower() > name.lower():
            position = channel.position
            category = channel.category
            break
    await new_channel.edit(category=category, position=position, overwrites=overwrites)
    await ctx.send(f"Set appropriate permissions for {new_channel.mention}. Done!")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def archive(ctx):
    """Archive a channel."""
    await ctx.send("Archiving channel.")
    await ctx.channel.edit(category=get_archive_category(ctx.guild))


@bot.listen("on_message")
async def on_message(message: discord.Message):
    """Listen for messages in archived channels to unarchive them."""
    if (
        message.guild is None
        or message.channel.category is None
        or message.channel.category != get_archive_category(message.guild)
    ):
        return
    await reposition_channel(message.channel, get_project_categories(message.guild))
    await message.channel.send("Channel unarchived!")


async def reposition_channel(channel, project_categories):
    channels = sorted(
        (ch for c in project_categories for ch in c.channels if ch.id != channel.id),
        key=lambda ch: ch.name,
    )
    category = None
    position = 0
    for c in channels:
        position = c.position
        if c.name > channel.name:
            if not category:
                category = c.category
            break
        category = c.category
    else:
        # Channel should be sorted last
        position += 1
    await channel.edit(category=category, position=position)
    print(f"Moved channel {channel.name}")


@bot.event
async def on_command_error(ctx, error):
    await ctx.send(str(error))


@bot.event
async def on_guild_channel_update(before, after):
    """Move channels to the correct position if they got renamed."""
    if not isinstance(after, discord.TextChannel):
        print(type(after))
        return
    categories = get_project_categories(before.guild)
    if not (after.category in categories and after.name != before.name):
        return
    await reposition_channel(after, categories)


bot.run(os.getenv("CHANNELSORTER_TOKEN"))
