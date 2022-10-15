# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import os
from importlib import import_module

from breadbot import BASE_DIR

# import all modules in breadbot.commands
for module in os.listdir(BASE_DIR / "breadbot" / "commands"):
    if module.endswith(".py"):
        import_module(f"breadbot.commands.{module[:-3]}")

from breadbot.bot import bot

bot.run(os.getenv("CHANNELSORTER_TOKEN"))
