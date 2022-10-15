# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import os
import re
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import discord
from discord.ext import commands

from breadbot.bot import bot
from breadbot.util.random import get_random_top100_steam_game


@bot.command()
@commands.has_permissions(administrator=True)
async def change_presence(ctx):
    """Change the bot's presence."""
    await bot.change_presence(
        activity=discord.Game(name=get_random_top100_steam_game())
    )
    await ctx.send("✅ Done!")


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
            await ctx.reply(f"⚠️ {e}")
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
    await ctx.send("✅ Code updated!")
    await ctx.send("Restarting!")
    os.execl(sys.executable, sys.executable, *sys.argv)
