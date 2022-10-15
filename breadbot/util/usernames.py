# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import unicodedata

import discord

from breadbot.models import Guild
from breadbot.util.discord_objects import get_log_channel


def normalized_username(member: discord.Member) -> str:
    """Normalize a member's username."""
    # Strip out RTL characters
    invalid_directionalities = ["R", "AL", "RLE", "RLO", "RLI"]
    normalized = unicodedata.normalize("NFKC", member.display_name)
    return (
        "".join(
            ch
            for ch in normalized
            if unicodedata.combining(ch) == 0
            and unicodedata.bidirectional(ch) not in invalid_directionalities
        ).strip()
        or f"User{member.discriminator}"
    )


async def maybe_normalize_nickname(member: discord.Member):
    """Maybe normalize a member's nickname."""
    normalized = normalized_username(member)
    if normalized != member.display_name:
        log_channel = get_log_channel(
            member.guild, await Guild.get(id=member.guild.id)
        )
        if log_channel:
            await log_channel.send(
                f"Renaming {member.mention}: {member.display_name} -> {normalized}"
            )
        await member.edit(nick=normalized_username(member))
