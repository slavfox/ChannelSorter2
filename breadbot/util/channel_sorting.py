# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from itertools import chain, combinations
from typing import Dict, List

import discord

from breadbot.models import Guild
from breadbot.util.discord_objects import (
    get_archive_category,
    get_project_categories,
)


def unbalancedness(separator_idxs: list[int]) -> int:
    """
    Return the sum of squares of differences between sublist lengths given a
    list of indices of sublist "borders".
    """
    score = 0
    for prev, nxt in zip(separator_idxs[:-1], separator_idxs[1:]):
        score += (nxt - prev) ** 2
    return score


def balanced_categories(
    categories: list[discord.CategoryChannel],
    channels: list[discord.TextChannel],
) -> dict[int, list[discord.TextChannel]]:
    """
    Given a list of categories and channels, return a dict mapping category
    ID to a list of channels in that category so that the channels are
    sorted alphabetically, every starting letter is contained entirely
    within a single category, and each category has a similar number of
    channels.
    """
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
            key=lambda partition: unbalancedness(
                [0, *partition, len(channels)]
            ),
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


async def reposition_channel(channel, project_categories):
    """
    Try to position a channel where it should be in the projects
    categories without resorting everything.
    """
    channels = sorted(
        (
            ch
            for c in project_categories
            for ch in c.channels
            if ch.id != channel.id
        ),
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


async def sort_inner(
    discord_guild: discord.Guild,
    guild: Guild,
    log_channel: discord.TextChannel,
    verbose: bool = True,
):
    """Channel sorting logic."""
    moves_made = 0
    renames_made = 0

    categories = get_project_categories(discord_guild, guild)
    channels = sorted(
        chain.from_iterable(c.channels for c in categories),
        key=lambda ch: ch.name,
    )
    category_channels = balanced_categories(categories, channels)
    archive_category = get_archive_category(discord_guild, guild)
    # rename project categories
    for cat_id, cat_channels in category_channels.items():
        category = discord.utils.get(discord_guild.categories, id=cat_id)
        assert category is not None
        start_letter = cat_channels[0].name.upper()[0]
        end_letter = cat_channels[-1].name.upper()[0]
        # Rename category if necessary
        new_cat_name = f"Projects {start_letter}-{end_letter}"
        if category.name != new_cat_name:
            renames_made += 1
            if verbose:
                await log_channel.send(
                    f"Renaming {category.name} to {new_cat_name}"
                )
            await category.edit(name=new_cat_name)

    if archive_category is not None:
        category_channels[archive_category.id] = sorted(
            archive_category.channels, key=lambda ch: ch.name
        )
        categories.append(archive_category)
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
                _old_pos_for_logs = channel.position
                channel.position = new_pos
                if verbose:
                    await log_channel.send(
                        f"Moving channel {channel.name}.\n"
                        f"Old position: {_old_pos_for_logs}\n"
                        f"New channel.position: {new_pos}\n"
                        f"New position: {category.channels[i].position}.\n"
                    )
                await channel.edit(
                    category=category, position=category.channels[i].position
                )

    if renames_made > 0 or moves_made > 0:
        await log_channel.send(
            f"Channels sorted! Renamed {renames_made} categories and "
            f"moved {moves_made} channels."
        )
