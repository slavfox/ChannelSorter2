import discord
import logging

logger = logging.getLogger()

BOOKMARK_EMOJI = '🔖'
MAX_EXCERPT_LENGTH = 200

async def maybe_serve_bookmark_request(reaction: discord.RawReactionActionEvent):
    """
    Check if a message reaction is a bookmark (🔖) and DM the reactor
    an excerpt of the message if so.
    """

    # Check if no member is associated with the reaction (this would be the case
    # when the reaction is made on a message outside the guild, eg: in DMs) and
    # also ensure that the member is not a bot
    if reaction.member is None or reaction.member.bot:
        return

    # Check if the reaction was made with the unicode bookmark emoji
    if not reaction.emoji.is_unicode_emoji() or reaction.emoji.name != BOOKMARK_EMOJI:
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
        logger.error("Failed to fetch message to serve bookmark request.", exc_info=e)
        return

    author_line = f"Author: {member.mention}"
    channel_line = f"Channel: {channel_or_thread.jump_url}"
    link_line = f"Message Link: {message.jump_url}"
    if len(message.content) <= MAX_EXCERPT_LENGTH:
        content = message.content
    else:
        content = f"{message.content[:MAX_EXCERPT_LENGTH]}..."

    embed = discord.Embed(title=f"Bookmark")
    embed.add_field(name="Details", value=f"{author_line}\n{channel_line}\n{link_line}", inline=False)
    embed.add_field(name="Excerpt", value=content, inline=False)

    try:
        await member.send(embed=embed)
    except Exception as e:
        logger.error("Failed DM-ing bookmark to member", exc_info=e)
