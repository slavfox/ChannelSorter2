# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import json
from random import choice
from urllib.request import urlopen


def get_random_top100_steam_game() -> str:
    """Get the name of a random top 100 steam game."""
    try:
        games = json.load(
            urlopen("https://steamspy.com/api.php?request=top100in2weeks")
        )
    except json.JSONDecodeError:
        return "dead"
    game = choice(list(games.keys()))
    return games[game]["name"]
