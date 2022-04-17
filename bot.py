# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import os
import traceback
from datetime import datetime
from itertools import chain
from pathlib import Path
import re
from contextlib import redirect_stdout
from io import StringIO
from typing import List, Dict
from itertools import combinations

import discord
from discord.ext import commands

channels_path = Path(__file__).parent / "categories.txt"

bot = commands.Bot(
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


def get_project_categories(guild):
    with channels_path.open() as f:
        return [discord.utils.get(guild.categories, id=int(line.strip())) for line in f]


def get_archive_category(guild):
    return discord.utils.get(guild.categories, name="Archive")


def unbalancedness(separator_idxs: List[int]) -> int:
    score = 0
    for prev, nxt in zip(separator_idxs[:-1], separator_idxs[1:]):
        score += (nxt - prev) ** 2
    return score


def balanced_categories(
    categories: List[discord.CategoryChannel], channels: List[discord.TextChannel]
) -> Dict[int, List[discord.TextChannel]]:
    prev_letter = channels[0].name.upper()[0]
    letter_change_idxs = [0]
    # Save indices with letter changes
    for i, channel in enumerate(channels):
        if channel.name.upper()[0] != prev_letter:
            prev_letter = channel.name.upper()[0]
            letter_change_idxs.append(i)

    best_partition = [
        0,
        # Find the partition with the smallest unbalancedness
        *min(
            combinations(letter_change_idxs, len(categories) - 1),
            key=lambda partition: unbalancedness([0, *partition, len(channels)]),
        ),
    ]
    assert len(best_partition) == len(categories)

    category_channels = {}
    # Map categories to their channels
    for start_idx, category in reversed(list(zip(best_partition, categories))):
        category_channels[category.id] = channels[start_idx:]
        channels = channels[:start_idx]

    assert all(category.id in category_channels for category in categories)
    return category_channels


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
    category_channels = balanced_categories(categories, channels)
    # rename project categories
    for cat_id, cat_channels in category_channels.items():
        category = discord.utils.get(ctx.guild.categories, id=cat_id)
        start_letter = cat_channels[0].name.upper()[0]
        end_letter = cat_channels[-1].name.upper()[0]
        # Rename category if necessary
        new_cat_name = f"Projects {start_letter}-{end_letter}"
        print(
            f"{new_cat_name}: "
            f"channels {cat_channels[0].name}:{cat_channels[-1].name}"
        )
        if category.name != new_cat_name:
            renames_made += 1
            print(f"Renaming {category.name} to {new_cat_name}")
            await category.edit(name=new_cat_name)

    # Shuffle channels around
    for category in categories:
        for i, channel in enumerate(category_channels[category.id]):
            cat_channels = category.channels
            if len(cat_channels) > i:
                target_channel = cat_channels[i]
                new_pos = target_channel.position
                needs_move = target_channel != channel
            else:
                new_pos = cat_channels[-1].position + 1
                needs_move = cat_channels[-1] != channel
            if channel.category_id != category.id or needs_move:
                old_pos = channel.position
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
        name=f"lang: {name.capitalize()}",
        colour=discord.Colour.default(),
        mentionable=True,
    )
    lang_owner_role = discord.utils.get(ctx.guild.roles, name="Lang Channel Owner")
    await ctx.send(f"Created and assigned role {role.mention}.")
    await owner.add_roles(role, lang_owner_role)
    channelbot_role = discord.utils.get(ctx.guild.roles, name="Channel Bot")
    muted_role = discord.utils.get(ctx.guild.roles, name="muted")
    overwrites = {
        role: CHANNEL_OWNER_PERMS,
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
    everyone = discord.utils.get(ctx.guild.roles, name="@everyone")
    await ctx.channel.set_permissions(everyone, send_messages=False)
    for role in ctx.channel.overwrites:
        if role.name.startswith("lang: "):
            await ctx.channel.set_permissions(role, overwrite=CHANNEL_OWNER_PERMS)
            break


@bot.command()
@commands.has_permissions(administrator=True)
async def inactive(ctx):
    """Print inactive channels."""
    await ctx.send(f"Looking for inactive project channels.")
    inactive_channels = 0
    channel: discord.TextChannel
    for channel in chain.from_iterable(
        c.channels for c in get_project_categories(ctx.guild)
    ):
        try:
            last_message, *_ = await channel.history(limit=1).flatten()
        except IndexError:
            continue
        time_since = datetime.now() - last_message.created_at
        if time_since.days > 90:
            await ctx.send(
                f"{channel.mention} is inactive, last message "
                f"{time_since.days} days ago."
            )
            inactive_channels += 1

    await ctx.send(f"Found {inactive_channels} inactive channels.")


@bot.command()
@commands.has_permissions(administrator=True)
async def archive_inactive(ctx):
    """Archive inactive channels."""
    await ctx.send(f"Archiving inactive project channels.")
    archived = 0
    channel: discord.TextChannel
    for channel in chain.from_iterable(
        c.channels for c in get_project_categories(ctx.guild)
    ):
        try:
            last_message, *_ = await channel.history(limit=1).flatten()
        except IndexError:
            continue
        time_since = datetime.now() - last_message.created_at
        if time_since.days <= 90:
            continue
        await channel.send(
            "Archiving channel due to inactivity. "
            "If you're the channel owner, send a message here to unarchive."
        )
        await channel.edit(category=get_archive_category(ctx.guild))
        everyone = discord.utils.get(ctx.guild.roles, name="@everyone")
        await channel.set_permissions(everyone, send_messages=False)
        for role in channel.overwrites:
            if role.name.startswith("lang: "):
                await channel.set_permissions(role, overwrite=CHANNEL_OWNER_PERMS)
                break
        archived += 1

    await ctx.send(f"Archived {archived} inactive channels.")


@bot.command()
@commands.is_owner()
async def run_python(ctx, *, code):
    """Run arbitrary Python."""

    async def aexec(code, globals_, locals_):
        exec(
            f"async def __ex(ctx, globals, locals): "
            + "".join(f"\n {l}" for l in code.split("\n")),
            globals_,
            locals_,
        )
        return await locals_["__ex"](ctx, globals_, locals_)

    code = re.match("```(python)?(.*?)```", code, flags=re.DOTALL).group(2)
    print(f"Running ```{code}```")
    stdout = StringIO()
    with redirect_stdout(stdout):
        await aexec(code, globals(), locals())
    await ctx.send(f"```\n{stdout.getvalue()}\n```")


@bot.listen("on_message")
async def on_message(message: discord.Message):
    """Listen for messages in archived channels to unarchive them."""
    if (
        message.guild is None
        or message.channel.category is None
        or message.channel.category != get_archive_category(message.guild)
    ):
        return
    everyone = discord.utils.get(message.guild.roles, name="@everyone")
    await message.channel.set_permissions(everyone, overwrite=None)
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
    traceback.print_exception(error)
    await ctx.reply(str(error))


@bot.event
async def on_guild_channel_update(before, after):
    """Move channels to the correct position if they got renamed."""
    if not isinstance(after, discord.TextChannel):
        return
    categories = get_project_categories(before.guild)
    if not (after.category in categories and after.name != before.name):
        return
    await reposition_channel(after, categories)


bot.run(os.getenv("CHANNELSORTER_TOKEN"))
