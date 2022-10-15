# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import os
from importlib import import_module

import discord
from tortoise import run_async

from breadbot import BASE_DIR

# import all modules in breadbot.commands
for module in os.listdir(BASE_DIR / "breadbot" / "commands"):
    if module.endswith(".py"):
        import_module(f"breadbot.commands.{module[:-3]}")

from breadbot.bot import bot

bot.run(os.getenv("CHANNELSORTER_TOKEN"))


discord.utils.setup_logging()


async def runner():
    async with bot:
        await bot.start(os.getenv("CHANNELSORTER_TOKEN"), reconnect=True)


run_async(runner())
