import datetime
from pathlib import Path
from jinja2 import Environment
from typing import Union


# 4k token window version saves around 10-50% latency and likely has lower latency variance.
ENGINE = "gpt-35-turbo"
# 16k longer context
# ENGINE = "gpt-35-turbo-16k"


WEEKDAYS = {
    1: "v pondělí",
    2: "v úterý",
    3: "ve středu",
    4: "ve čtvrtek",
    5: "v pátek",
    6: "v sobotu",
    7: "v neděli",
}

DAYS = {
    1: "prvního",
    2: "druhého",
    3: "třetího",
    4: "čtvrtého",
    5: "pátého",
    6: "šestého",
    7: "sedmého",
    8: "osmého",
    9: "devátého",
    10: "desátého",
    11: "jedenáctého",
    12: "dvanáctého",
    13: "třináctého",
    14: "čtrnáctého",
    15: "patnáctého",
    16: "šestnáctého",
    17: "sedmnáctého",
    18: "osmnáctého",
    19: "devatenáctého",
    20: "dvacátého",
    30: "třicátého",
    31: "třicátého prvního",
}
DAYS.update({20 + d: DAYS[20] + " " + DAYS[d] for d in range(1, 10)})

MONTHS = {
    1: "ledna",
    2: "února",
    3: "března",
    4: "dubna",
    5: "května",
    6: "června",
    7: "července",
    8: "srpna",
    9: "září",
    10: "října",
    11: "listopadu",
    12: "prosince",
}

HOURS = {
    0: "ve dvanáct",
    1: "v jednu",
    2: "ve dvě",
    3: "ve tři",
    4: "ve čtyři",
    5: "v pět",
    6: "v šest",
    7: "v sedm",
    8: "v osm",
    9: "v devět",
    10: "v deset",
    11: "v jedenáct",
    12: "ve dvanáct",
    13: "v jednu",
    14: "ve dvě",
    15: "ve tři",
    16: "ve čtyři",
    17: "v pět",
    18: "v šest",
    19: "v sedm",
    20: "v osm",
    21: "v devět",
    22: "v deset",
    23: "v jedenáct",
}

MINUTES = {
    0: "nula nula",
    1: "nula jedna",
    2: "nula dva",
    3: "nula tři",
    4: "nula čtyři",
    5: "nula pět",
    6: "nula šest",
    7: "nula sedm",
    8: "nula osm",
    9: "nula devět",
    10: "deset",
    11: "jedenáct",
    12: "dvanáct",
    13: "třináct",
    14: "čtrnáct",
    15: "patnáct",
    16: "šestnáct",
    17: "sedmnáct",
    18: "osmnáct",
    19: "devatenáct",
    20: "dvacet",
    21: "dvacet jedna",
    22: "dvacet dva",
    23: "dvacet tři",
    24: "dvacet čtyři",
    25: "dvacet pět",
    26: "dvacet šest",
    27: "dvacet sedm",
    28: "dvacet osm",
    29: "dvacet devět",
    30: "třicet",
    31: "třicet jedna",
    32: "třicet dva",
    33: "třicet tři",
    34: "třicet čtyři",
    35: "třicet pět",
    36: "třicet šest",
    37: "třicet sedm",
    38: "třicet osm",
    39: "třicet devět",
    40: "čtyřicet",
    41: "čtyřicet jedna",
    42: "čtyřicet dva",
    43: "čtyřicet tři",
    44: "čtyřicet čtyři",
    45: "čtyřicet pět",
    46: "čtyřicet šest",
    47: "čtyřicet sedm",
    48: "čtyřicet osm",
    49: "čtyřicet devět",
    50: "padesát",
    51: "padesát jedna",
    52: "padesát dva",
    53: "padesát tři",
    54: "padesát čtyři",
    55: "padesát pět",
    56: "padesát šest",
    57: "padesát sedm",
    58: "padesát osm",
    59: "padesát devět",
}


def date_to_tts(value: Union[str, datetime.date], current_date: Union[str, datetime.date]) -> str:
    if isinstance(current_date, str):
        current_date = datetime.date.fromisoformat(current_date)
    if not isinstance(value, datetime.date):
        try:
            value = datetime.date.fromisoformat(value)
        except (ValueError, TypeError):
            return "neznámé datum"
    if value == current_date:
        return "dnes"
    elif value == current_date + datetime.timedelta(days=1):
        return "zítra"
    day = DAYS[value.day]
    month = MONTHS[value.month]
    weekday = WEEKDAYS[value.isoweekday()]
    return f"{weekday} {day} {month}"


def time_to_tts(value: Union[str, datetime.time]) -> str:
    if not isinstance(value, datetime.time):
        try:
            value = datetime.time.fromisoformat(value)
        except (ValueError, TypeError):
            return "neznámý čas"

    hour_int = value.hour
    if 4 <= hour_int < 10:
        day_period = "ráno"
    elif 10 <= hour_int < 12:
        day_period = "dopoledne"
    elif 17 <= hour_int <= 23:
        day_period = "večer"
    elif 23 < hour_int < 4:
        day_period = "v noci"
    else:
        day_period = ""

    minute = MINUTES[value.minute]
    hour = HOURS[hour_int]

    if minute is None or minute == 0:
        return f"{hour} {day_period}".strip()
    else:
        if value.hour == 13:
            hour = "ve třináct"
        return f"{hour} {minute} {day_period}".strip()


def date_from_weekday(today: datetime.date, weekday: int) -> datetime.date:
    if weekday > today.isoweekday():
        return today + datetime.timedelta(days=(weekday - today.isoweekday()))
    else:
        return today + datetime.timedelta(days=(7 + weekday - today.isoweekday()))


def get_jinja_env() -> Environment:
    env = Environment()
    env.filters["date_to_tts"] = date_to_tts
    env.filters["time_to_tts"] = time_to_tts
    return env


def load_template(name: str) -> str:
    current_dir = Path(__file__).parent
    templates_dir = current_dir / "templates"
    with open(templates_dir / name, 'r') as f:
        return f.read()

def print_colored(text, color):
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m",
        "white": "\033[97m",
        "end": "\033[0m"
    }
    print(f"{colors[color]}{text}{colors['end']}")

def get_state_by_id(states, test_id):
    for state in states:
        if state["id"] == test_id:
            return state
    raise ValueError(f"Unknown test id {test_id}")