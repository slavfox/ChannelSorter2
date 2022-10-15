# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from io import BytesIO

import discord


def write_message(message: discord.Message, buffer: BytesIO):
    buffer.write(
        f"[{message.created_at.isoformat(sep=' ', timespec='seconds')}] "
        f"{message.author}: "
        f"{message.clean_content}\n".encode()
    )
    if message.attachments:
        buffer.write(f"[attachments]:\n".encode())
        for a in message.attachments:
            buffer.write(f"{a.url}\n".encode())


async def dump_channel_contents(channel: discord.TextChannel, buffer: BytesIO):
    buffer.write(
        f"Channel: #{channel.name}\n"
        f"Topic: {channel.topic}\n".encode()
    )
    message: discord.Message
    pins = await channel.pins()
    if pins:
        buffer.write(b"\nPins:\n\n")

    for message in pins:
        buffer.write(f"[PINNED]".encode())
        write_message(message, buffer)

    buffer.write(b"\nChannel history:\n\n")

    async for message in channel.history(
        limit=None,
        oldest_first=True,
    ):
        write_message(message, buffer)
