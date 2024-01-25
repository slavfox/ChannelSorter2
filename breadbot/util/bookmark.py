from typing import Optional

import discord
import logging

logger = logging.getLogger()

BOOKMARK_EMOJI = "🔖"
BOOKMARK_EMBED_TITLE = "Bookmark"
MAX_EXCERPT_LENGTH = 200
WASTEBASKET_EMOJI = "🗑️"


async def maybe_serve_bookmark_request(
    reaction: discord.RawReactionActionEvent,
):
    """
    Check if a message reaction is a bookmark (🔖) and DM the reactor
    an excerpt of the message if so.
    """

    # Check if the reaction was made with the unicode bookmark emoji
    if (
        not reaction.emoji.is_unicode_emoji()
        or reaction.emoji.name != BOOKMARK_EMOJI
    ):
        return

    # Check if no member is associated with the reaction (this would be the case
    # when the reaction is made on a message outside the guild, eg: in DMs) and
    # also ensure that the member is not a bot
    if reaction.member is None or reaction.member.bot:
        return

    member = reaction.member
    guild = member.guild
    channel_or_thread = guild.get_channel_or_thread(reaction.channel_id)
    if channel_or_thread is None:
        return

    try:
        # this is a safe method to call since every type of channel (Thread, TextChannel,
        # VoiceChannel, StageChannel) that can have a reaction event triggered supports
        # this method.
        message = await channel_or_thread.fetch_message(reaction.message_id)
    except Exception as e:
        logger.error(
            "Failed to fetch message to serve bookmark request.", exc_info=e
        )
        return

    author_line = f"Author: {message.author.mention}"
    channel_line = f"Channel: {channel_or_thread.jump_url}"
    link_line = f"Message Link: {message.jump_url}"
    if len(message.content) <= MAX_EXCERPT_LENGTH:
        content = message.content
    else:
        content = f"{message.content[:MAX_EXCERPT_LENGTH]}..."

    embed = discord.Embed(title=BOOKMARK_EMBED_TITLE)
    embed.add_field(
        name="Details",
        value=f"{author_line}\n{channel_line}\n{link_line}",
        inline=False,
    )
    embed.add_field(name="Excerpt", value=content, inline=False)

    try:
        message = await member.send(embed=embed)
    except Exception as e:
        logger.error("Failed DM-ing bookmark to member.", exc_info=e)

    try:
        # Add wastebasket reaction for better UX for deleting the bookmark.
        await message.add_reaction(WASTEBASKET_EMOJI)
    except Exception as e:
        logger.error(
            "Failed adding wastebasket reaction on bookmark.", exc_info=e
        )


async def maybe_delete_bookmark(
    bot: discord.Client,
    reaction: discord.RawReactionActionEvent,
):
    """
    Check if the reaction is the wastebasket emoji (🗑️) on a DM bookmark
    and delete the bookmark if so.
    """

    # Check if the reaction is the wastebasket emoji. Return if not.
    if (
        not reaction.emoji.is_unicode_emoji()
        or reaction.emoji.name != WASTEBASKET_EMOJI
    ):
        return

    # Check if the reaction has a member associated with it. If yes, it was added
    # in a guild i.e. not in DMs with the bot, so return.
    if reaction.member is not None:
        return

    # If the reaction was added by the bot, return.
    if bot.user is None or reaction.user_id == bot.user.id:
        return

    try:
        dm_channel = await bot.fetch_channel(reaction.channel_id)
    except Exception as e:
        logger.error(
            "Failed to fetch DM channel for serving a bookmark delete request.",
            exc_info=e,
        )
        return

    # If the channel is not a private DM, return.
    if not isinstance(dm_channel, discord.DMChannel):
        return

    try:
        message = await dm_channel.fetch_message(reaction.message_id)
    except Exception as e:
        logger.error(
            "Failed to fetch message for serving a bookmark delete request.",
            exc_info=e,
        )
        return

    # If the message wasn't set by the bot, or if it has less than or more than
    # 1 embeds i.e. it's potentially not a bookmark, return.
    if (
        not message.author.bot
        or message.author.id != bot.user.id
        or len(message.embeds) != 1
    ):
        return

    # If the embed is not a bookmark embed, return.
    if message.embeds[0].title != BOOKMARK_EMBED_TITLE:
        return

    try:
        # We have confirmed this is indeed a bookmark message by the bot, so delete it.
        await message.delete()
    except Exception as e:
        logger.error(
            "Error deleting the bookmark message when serving a delete request.",
            exc_info=e,
        )
