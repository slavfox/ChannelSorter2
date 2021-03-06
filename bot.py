# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""/r/ProgrammingLanguages discord channel management bot."""
import json
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import time
import traceback
import unicodedata
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from itertools import chain, combinations
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict, List, Tuple
from urllib.request import urlopen

import discord
import psutil as psutil
from discord.ext import commands, tasks

channels_path = Path(__file__).parent / "categories.txt"
notifs_path = Path(__file__).parent / "notify.json"

GiB = 1024**3


def get_notifies() -> Dict[str, List[int]]:
    """Get a dict mapping guild ID to a list of channel IDs to notify."""
    try:
        with notifs_path.open() as f:
            return json.load(f)
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        return {}


def save_notifies(notifies: Dict[str, List[int]]):
    """Save a dict mapping guild ID to a list of channel IDs to notify."""
    with NamedTemporaryFile(mode="w", delete=False) as f:
        json.dump(notifies, f)
    shutil.move(f.name, notifs_path)


class ChannelBot(commands.Bot):
    """Discordpy bot subclass with convenience methods we need."""

    @tasks.loop(hours=1)
    async def hourly_update(self):
        """Clean up channel list and cycle presence."""
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="over the project channels",
            )
        )
        try:
            for guild in self.guilds:
                log_channel = get_log_channel(guild)
                if log_channel is None:
                    continue
                print(f"Running hourly update in {guild.name}")
                print(f"Archiving inactive channels")
                await archive_inactive_inner(guild, log_channel, verbose=False)
                print(f"Deleting dead channels")
                await delete_dead_channels(guild, log_channel, verbose=False)
                print(f"Sorting channels")
                await sort_inner(guild, log_channel, verbose=True)
                print(f"Normalizing usernames")
                for member in guild.members:
                    await maybe_normalize_nickname(member)
        finally:
            await self.change_presence(
                activity=discord.Game(name=get_random_top100_steam_game())
            )
            print(f"Done!")

    async def on_ready(self):
        """Set initial presence."""
        print(f"Successfully logged in as {self.user}")
        self.hourly_update.start()


bot = ChannelBot(
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


def get_project_categories(guild) -> List[discord.CategoryChannel]:
    """Get a list of project categories in the server from the config file."""
    with channels_path.open() as f:
        return [
            discord.utils.get(guild.categories, id=int(line.strip()))
            for line in f
        ]


def get_archive_category(guild: discord.Guild) -> discord.CategoryChannel:
    """Get the archive category for the guild."""
    return discord.utils.get(guild.categories, name="Archive")


def get_log_channel(guild: discord.Guild) -> discord.TextChannel:
    """Return the log channel for the guild."""
    return discord.utils.get(guild.channels, name="channelbot-logs")


def get_langbot(guild: discord.Guild) -> discord.Member:
    """Get a reference to LangBot."""
    langbot = discord.utils.get(guild.members, id=969984431693627533)
    if langbot is None:
        raise discord.ext.commands.MemberNotFound("LangBot")
    return langbot


def unbalancedness(separator_idxs: List[int]) -> int:
    """
    Return the sum of squares of differences between sublist lengths given a
    list of indices of sublist "borders".
    """
    score = 0
    for prev, nxt in zip(separator_idxs[:-1], separator_idxs[1:]):
        score += (nxt - prev) ** 2
    return score


def balanced_categories(
    categories: List[discord.CategoryChannel],
    channels: List[discord.TextChannel],
) -> Dict[int, List[discord.TextChannel]]:
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


def write_message(message: discord.Message, buffer: StringIO):
    buffer.write(
        f"[{message.created_at.isoformat(sep=' ', timespec='seconds')}] "
        f"{message.author}: "
        f"{message.clean_content}\n"
    )
    if message.attachments:
        buffer.write(f"[attachments]:\n")
        for a in message.attachments:
            buffer.write(f"{a.url}\n")


async def dump_channel_contents(
    channel: discord.TextChannel, buffer: StringIO
):
    buffer.write(f"Channel: #{channel.name}\n" f"Topic: {channel.topic}\n")
    message: discord.Message
    pins = await channel.pins()
    if pins:
        buffer.write("\nPins:\n\n")

    for message in pins:
        buffer.write(f"[PINNED]")
        write_message(message, buffer)

    buffer.write("\nChannel history:\n\n")

    async for message in channel.history(
        limit=None,
        oldest_first=True,
    ):
        write_message(message, buffer)


@bot.command()
@commands.has_permissions(administrator=True)
async def get_categories(ctx):
    """Get the names of the project categories."""
    await ctx.send(
        f"Project categories: "
        f"{[c.name for c in get_project_categories(ctx.guild)]}"
    )


@bot.command()
@commands.is_owner()
async def set_categories(ctx, *categories: discord.CategoryChannel):
    """Set the ids of the project categories."""
    with channels_path.open("w") as f:
        for category in categories:
            f.write(str(category.id) + "\n")
    await ctx.send(f"New project categories: {[c.name for c in categories]}")


@bot.command()
@commands.has_permissions(administrator=True)
async def sort(ctx: discord.ext.commands.Context):
    """Sort project channels."""
    await ctx.send("Sorting project channels...")
    await sort_inner(ctx.guild, ctx.channel)
    await ctx.send("Done!")


async def sort_inner(
    guild: discord.Guild,
    log_channel: discord.TextChannel,
    verbose: bool = True,
):
    """Channel sorting logic."""
    moves_made = 0
    renames_made = 0

    categories = get_project_categories(guild)
    channels = sorted(
        chain.from_iterable(c.channels for c in categories),
        key=lambda ch: ch.name,
    )
    category_channels = balanced_categories(categories, channels)
    archive_category = get_archive_category(guild)
    # rename project categories
    for cat_id, cat_channels in category_channels.items():
        category = discord.utils.get(guild.categories, id=cat_id)
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


@bot.command()
@commands.has_permissions(administrator=True)
async def make_channel(ctx, owner: discord.Member, name: str):
    """Create a new project channel and role."""
    new_channel = await ctx.guild.create_text_channel(name=name)
    await reposition_channel(new_channel, get_project_categories(ctx.guild))
    await ctx.send(f"Created channel {new_channel.mention}.")
    role = await ctx.guild.create_role(
        name=f"lang: {name.capitalize()}",
        colour=discord.Colour.default(),
        mentionable=True,
    )
    lang_owner_role = discord.utils.get(
        ctx.guild.roles, name="Lang Channel Owner"
    )
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
    await new_channel.edit(overwrites=overwrites)
    await ctx.send(f"Set appropriate permissions for {new_channel.mention}.")
    await sort_inner(ctx.guild, ctx.channel, verbose=True)
    await ctx.send(f"??? Done!")


@bot.command()
@commands.has_permissions(manage_roles=True)
async def rename_role(ctx, role: discord.Role, *, name: str):
    """Rename a role."""
    prev_name = role.name
    await role.edit(name=name)
    await ctx.send(f"Renamed role {prev_name} -> {role.mention}.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def rename_channel(ctx, *, name: str):
    """Rename a channel."""
    prev_name = ctx.channel.name
    await ctx.channel.edit(name=name)
    await ctx.send(f"Renamed channel {prev_name} -> {ctx.channel.mention}.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def archive(ctx):
    """Archive a channel."""
    await ctx.send("Archiving channel.")
    await get_log_channel(ctx.guild).send(
        f"Channel {ctx.channel.mention} archived manually by owner."
    )
    await ctx.channel.edit(category=get_archive_category(ctx.guild))
    everyone = discord.utils.get(ctx.guild.roles, name="@everyone")
    await ctx.channel.set_permissions(everyone, send_messages=False)
    for role in ctx.channel.overwrites:
        if role.name.startswith("lang: "):
            await ctx.channel.set_permissions(
                role, overwrite=CHANNEL_OWNER_PERMS
            )
            break


@bot.command()
@commands.has_permissions(manage_channels=True)
async def enable_langbot(ctx):
    """Enable Langbot to view this channel."""
    langbot = get_langbot(ctx.guild)
    if langbot in ctx.channel.overwrites:
        if ctx.channel.overwrites[langbot].view_channel:
            await ctx.send("??? Langbot is already enabled in this channel.")
            return
    await ctx.channel.set_permissions(langbot, view_channel=True)
    await ctx.send("??? Langbot enabled.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def disable_langbot(ctx):
    """Prevent Langbot from viewing this channel."""
    langbot = get_langbot(ctx.guild)
    if (
        langbot not in ctx.channel.overwrites
        or not ctx.channel.overwrites[langbot].view_channel
    ):
        await ctx.send("??? Langbot is already disabled in this channel.")
        return
    await ctx.channel.set_permissions(langbot, overwrite=None)
    await ctx.send("??? Langbot disabled.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def export(ctx: discord.ext.commands.Context):
    """Upload a file with the full history of the channel."""
    await ctx.send("Exporting channel history. This may take a while...")
    io = StringIO()
    await dump_channel_contents(ctx.channel, io)
    io.seek(0)
    await ctx.send(
        "??? Done!",
        file=discord.File(io, filename=f"history.txt"),
    )


@bot.command()
@commands.has_permissions(manage_channels=True)
async def delete_channel(ctx: discord.ext.commands.Context):
    """Delete the channel"""
    await ctx.send("Exporting channel history. This may take a while...")
    await delete_channel_inner(ctx.channel, ctx.guild)


async def delete_channel_inner(
    channel: discord.TextChannel, guild: discord.Guild
):
    """Handle deleting a channel."""
    pings = []
    archive_channel = discord.utils.get(guild.channels, name="archive")
    lang_owner_role = discord.utils.get(guild.roles, name="Lang Channel Owner")

    for role in channel.overwrites:
        if role.name.startswith("lang: "):
            for user in guild.members:
                if role in user.roles:
                    await user.remove_roles(
                        role,
                        lang_owner_role,
                        reason="Deleting dead channel",
                    )
                    pings.append(user)
            break
    io = StringIO()
    await dump_channel_contents(channel, io)
    io.seek(0)
    await archive_channel.send(
        f"Log for {channel.name} "
        f"({', '.join(user.mention for user in pings)}):",
        file=discord.File(io, filename=f"history_{channel.name}.txt"),
    )
    await channel.delete(reason="Deleting dead channel.")


@bot.command()
@commands.has_permissions(administrator=True)
async def archive_inactive(ctx):
    """Archive inactive channels."""
    return await archive_inactive_inner(ctx.guild, ctx.channel)


@bot.command()
async def notify(ctx):
    """Toggle pinging user for every message in this channel."""
    notifies = get_notifies()
    channel_id = str(ctx.channel.id)
    if channel_id not in notifies:
        notifies[channel_id] = []

    if ctx.author.id in notifies[channel_id]:
        notifies[channel_id].remove(ctx.author.id)
        await ctx.send(
            "??? You will no longer be pinged about messages in this channel."
        )
    else:
        notifies[channel_id].append(ctx.author.id)
        await ctx.send(
            "??? You will now be pinged about messages in this channel."
        )

    save_notifies(notifies)
    return


class MessageFound(Exception):
    pass


async def archive_inactive_inner(
    guild: discord.Guild,
    log_channel: discord.TextChannel,
    verbose: bool = True,
):
    """Archive project channels that have been inactive for over 90 days."""
    if verbose:
        await log_channel.send("Archiving inactive project channels.")
    archived = 0
    channel: discord.TextChannel
    for channel in chain.from_iterable(
        c.channels for c in get_project_categories(guild)
    ):
        try:
            async for message in channel.history(
                limit=None,
                after=datetime.now() - timedelta(days=90),
                oldest_first=True,
            ):
                if not message.author.bot:
                    raise MessageFound("Found a non-bot message!")
        except MessageFound:
            continue

        await log_channel.send(
            f"Archiving {channel.mention} due to inactivity."
        )
        await channel.send(
            "Archiving channel due to inactivity. "
            "If you're the channel owner, send a message here to unarchive."
        )
        await channel.edit(category=get_archive_category(guild))
        everyone = discord.utils.get(guild.roles, name="@everyone")
        await channel.set_permissions(everyone, send_messages=False)
        for role in channel.overwrites:
            if role.name.startswith("lang: "):
                await channel.set_permissions(
                    role, overwrite=CHANNEL_OWNER_PERMS
                )
                break
        archived += 1

    if verbose or archived > 0:
        await log_channel.send(f"Archived {archived} inactive channels.")


async def delete_dead_channels(
    guild: discord.Guild,
    log_channel: discord.TextChannel,
    verbose: bool = True,
):
    """Archive project channels that have been inactive for over 90 days."""
    archive_channel = discord.utils.get(guild.channels, name="archive")
    if verbose:
        await log_channel.send("Deleting dead project channels.")
    archived = 0
    channel: discord.TextChannel
    for channel in get_archive_category(guild).channels:
        try:
            async for message in channel.history(
                limit=None,
                after=datetime.now() - timedelta(days=30 * 6),
                oldest_first=True,
            ):
                if not message.author.bot:
                    raise MessageFound("Found a non-bot message!")
        except MessageFound:
            continue

        await archive_channel.send(
            f"{channel.name} has had no activity in over three months. "
            f"Deleting..."
        )
        await delete_channel_inner(channel, guild)
        archived += 1

    if verbose or archived > 0:
        await log_channel.send(f"Deleted {archived} dead channels.")


@bot.command()
@commands.has_permissions(administrator=True)
async def change_presence(ctx):
    """Change the bot's presence."""
    await bot.change_presence(
        activity=discord.Game(name=get_random_top100_steam_game())
    )
    await ctx.send("??? Done!")


@bot.listen("on_message")
async def on_message(message: discord.Message) -> None:
    """Listen for messages in archived channels to unarchive them."""
    if (not isinstance(message.guild, discord.Guild)) or message.author.bot:
        return

    if message.channel.category == get_archive_category(message.guild):
        everyone = discord.utils.get(message.guild.roles, name="@everyone")
        await message.channel.set_permissions(everyone, overwrite=None)
        await reposition_channel(
            message.channel, get_project_categories(message.guild)
        )
        await get_log_channel(message.guild).send(
            f"Channel {message.channel.mention} unarchived."
        )
        await message.channel.send("Channel unarchived!")

    # Notify
    users_to_notify = get_notifies().get(str(message.channel.id), [])
    embed = discord.Embed()
    embed.set_author(
        name=message.author.name, icon_url=message.author.avatar_url
    )
    embed.description = message.content
    embed.url = message.jump_url
    embed.set_footer(text=f"#{message.channel.name}")

    for uid in users_to_notify:
        if uid == message.author.id:
            continue
        await bot.get_user(uid).send(
            f"{message.author.mention} sent a message in "
            f"{message.channel.mention}:",
            embed=embed,
        )


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


async def maybe_normalize_nickname(member: discord.Member) -> str:
    """Maybe normalize a member's nickname."""
    normalized = normalized_username(member)
    if normalized != member.display_name:
        await get_log_channel(member.guild).send(
            f"Renaming {member.mention}: {member.display_name} -> {normalized}"
        )
        await member.edit(nick=normalized_username(member))


@bot.event
async def on_member_join(member: discord.Member) -> None:
    """Normalize usernames for new members."""
    await maybe_normalize_nickname(member)


@bot.event
async def on_member_update(
    before: discord.Member, after: discord.Member
) -> None:
    """Normalize usernames on update."""
    await maybe_normalize_nickname(after)


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


@bot.event
async def on_command_error(ctx, exception):
    """Handle command errors by sending the stringified exception back."""
    await ctx.reply(str(exception))
    traceback.print_exception(
        type(exception), exception, exception.__traceback__, file=sys.stderr
    )


@bot.event
async def on_guild_channel_update(before, after):
    """Move channels to the correct position if they got renamed."""
    if not isinstance(after, discord.TextChannel):
        return
    categories = get_project_categories(before.guild)
    if not (after.category in categories and after.name != before.name):
        return
    await get_log_channel(before.guild).send(
        f"Channel {before.mention} was renamed: {before.name} -> {after.name}"
    )
    await reposition_channel(after, categories)


# Fun stuff
def get_random_top100_steam_game() -> str:
    """Get the name of a random top 100 steam game."""
    games = json.load(
        urlopen("https://steamspy.com/api.php?request=top100in2weeks")
    )
    game = random.choice(list(games.keys()))
    return games[game]["name"]


def cpu_temp_and_voltage() -> Tuple[float, float]:
    """Get the current system temperature."""
    try:
        data = json.loads(
            subprocess.run(["sensors", "-j"], stdout=subprocess.PIPE).stdout
        )
    except json.decoder.JSONDecodeError:
        return 40.0, 1.0
    return (
        data.get("coretemp-isa-0000", {})
        .get("Package id 0", {})
        .get("temp1_input", 40.0),
        data.get("nct6795-isa-0a20", {})
        .get("Vcore", {})
        .get("in0_input", 1.0),
    )


def get_neofetch_field(field: str) -> str:
    return (
        subprocess.run(["neofetch", field], stdout=subprocess.PIPE)
        .stdout.decode("utf-8")
        .partition(": ")[-1]
        .strip()
    )


def get_model() -> str:
    """Get mobo model."""
    with open("/sys/devices/virtual/dmi/id/board_vendor") as f:
        vendor = f.read().strip()
    with open("/sys/devices/virtual/dmi/id/board_name") as f:
        board_name = f.read().strip()

    return f"{vendor} {board_name}"


def disk_usage_str() -> str:
    """Return a Discord-formatted representation of total disk usage."""
    partitions = psutil.disk_partitions()
    total = 0
    used = 0
    seen_devices = set()
    for p in partitions:
        try:
            usage = psutil.disk_usage(p.mountpoint)
            if p.device not in seen_devices:
                total += usage.total
            used += usage.used
        except PermissionError:
            pass
        seen_devices.add(p.device)

    return (
        f"`{used / GiB:.2f}/{total / GiB:.2f} GiB "
        f"({(used / total) * 100:.2f}%)`"
    )


@bot.command()
@commands.is_owner()
async def run_python(ctx, *, code):
    """Run arbitrary Python."""

    async def aexec(source, globals_, locals_):
        exec(
            "async def __ex(ctx, globals, locals): "
            + "".join(f"\n {line}" for line in source.split("\n")),
            globals_,
            locals_,
        )
        try:
            return await locals_["__ex"](ctx, globals_, locals_)
        except Exception as e:
            await ctx.reply(f"?????? {e}")
            raise e

    code = re.match("```(python)?(.*?)```", code, flags=re.DOTALL).group(2)
    print(f"Running ```{code}```")
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        await aexec(code, globals(), locals())
    output = ""
    stdout_val = stdout.getvalue()
    if stdout_val:
        output = f"Stdout:\n```\n{stdout_val}\n```\n"
    stderr_val = stderr.getvalue()
    if stderr_val:
        output += f"Stderr:\n```\n{stderr_val}\n```\n"
    if not output:
        output = "Done!"
    await ctx.send(output)


@bot.command(name="eval")
@commands.is_owner()
async def eval_python(ctx, *, expr):
    """Eval an arbitrary python expression."""
    print(f"Evaluating `{expr}`")
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        result = eval(expr.strip(), globals(), locals())

    embed = discord.Embed(
        title=f"Python expression",
        description=f"```python\n>>> {expr}\n{result!r}\n```",
        colour=discord.Colour.green(),
    )

    stdout = stdout.getvalue()
    if stdout:
        embed.add_field(name="Stdout", value=stdout)
    stderr = stderr.getvalue()
    if stderr:
        embed.add_field(name="Stderr", value=stderr)
    await ctx.send(embed=embed)


@bot.command()
@commands.is_owner()
async def restart(ctx):
    """Restart the bot."""
    await ctx.send("Pulling latest code...")
    subprocess.run(["git", "pull"], cwd=Path(__file__).parent.resolve())
    await ctx.send("??? Code updated!")
    await ctx.send("Restarting!")
    os.execl(sys.executable, sys.executable, *sys.argv)


@bot.command(aliases=["neofetch", "info"])
async def status(ctx):
    """Display various system information."""
    start = time.perf_counter()

    virtual_memory = psutil.virtual_memory()
    total_memory = virtual_memory.total / GiB
    used_memory = (virtual_memory.total - virtual_memory.available) / GiB
    cpu_temp, voltage = cpu_temp_and_voltage()
    project_channels = len(
        list(
            chain.from_iterable(
                c.channels for c in get_project_categories(ctx.guild)
            )
        )
    )

    embed = discord.Embed(
        title=f"`channelsorter@{socket.gethostname()}:~$`",
        description=f"??? **Up for:** {get_neofetch_field('uptime')} ???\n\n"
        f"**OS**: `{get_neofetch_field('distro')}`\n"
        f"**Kernel**: `{get_neofetch_field('kernel')}`\n"
        f"**Host**: `{get_model()}`\n"
        f"**CPU**: `{get_neofetch_field('cpu')}`\n"
        f"**GPU**: `{get_neofetch_field('gpu')}`\n"
        f"**Memory**: `{used_memory:.2f}/{total_memory:.2f} GiB "
        f"({virtual_memory.percent}%)`\n"
        f"**Disk space**: {disk_usage_str()}\n\n"
        f"??????????? Managing {project_channels} wonderful project channels!\n\n"
        f"https://github.com/slavfox/ChannelSorter2\n\n",
        colour=discord.Colour.green(),
    )
    embed.add_field(
        name="???? Python version", value=f"`{sys.version}`", inline=False
    )
    embed.add_field(
        name="??? Latency", value=f"`{bot.latency*1000:n} ms`", inline=False
    )
    embed.add_field(
        name="???? CPU usage", value=f"`{psutil.cpu_percent():n}%`", inline=False
    )
    embed.add_field(
        name="??????? CPU temperature",
        value=f"`{cpu_temp}??C`",
        inline=False,
    )
    embed.add_field(
        name="??? Vcore",
        value=f"`{voltage}V`",
        inline=False,
    )
    await ctx.send(
        f"Diagnostic finished in: `{(time.perf_counter() - start)*1000:n} ms`",
        embed=embed,
    )


bot.run(os.getenv("CHANNELSORTER_TOKEN"))
