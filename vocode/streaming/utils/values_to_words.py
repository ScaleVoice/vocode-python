import datetime
import re
import string
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

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

NUMBERS = {
    None: "",
    0: "nula",
    1: "jedna",
    2: "dva",
    3: "tři",
    4: "čtyři",
    5: "pět",
    6: "šest",
    7: "sedm",
    8: "osm",
    9: "devět",
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
    30: "třicet",
    40: "čtyřicet",
    50: "padesát",
    60: "šedesát",
    70: "sedmdesát",
    80: "osmdesát",
    90: "devadesát",
    100: "sto",
    200: "dvě stě",
    300: "tři sta",
    400: "čtyři sta",
    500: "pět set",
    600: "šest set",
    700: "sedm set",
    800: "osm set",
    900: "devět set",
    1000: "tisíc",
    1000000: "milión",
    1000000000: "miliarda",
}

NUMBERS_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2}|\d{2}:\d{2}|(\d+[\s.,]?)+)")
KW_PATTERN = re.compile(r"[kK][wW]")
PERCENT_PATTERN = re.compile(r"%")


@dataclass
class ValueToConvert:
    value: str
    position: Tuple[int, int]
    value_type: str
    tts_value: Optional[str]


def find_values_to_rewrite(text: str) -> List[ValueToConvert]:
    result = []
    for match in NUMBERS_PATTERN.finditer(text):
        start, end = match.start(), match.end()
        original_value = text[start:end]
        # TODO: handle ordinal numbers
        value = original_value.replace(" ", "").strip(string.punctuation)
        if "-" in value:
            value_type = "date"
            tts_value = date_to_words(value, current_date=None)
        elif ":" in value:
            value_type = "time"
            tts_value = time_to_words(value)
        elif value.isnumeric():
            value_type = "integer"
            tts_value = integer_to_words(value)
        else:
            try:
                float(value)
            except ValueError:
                continue
            value_type = "float"
            tts_value = float_to_words(value)

        # Add trailing spaces if the original value had them
        trailing_spaces = len(original_value) - len(original_value.rstrip())
        tts_value += " " * trailing_spaces

        result.append(ValueToConvert(original_value, (start, end), value_type, tts_value))

    # Find and convert all occurrences of kilowatt abbreviations
    for match in KW_PATTERN.finditer(text):
        start, end = match.start(), match.end()
        value = text[start:end]
        result.append(ValueToConvert(value, (start, end), "power", " kilowattů"))

    # Find and convert all occurrences of percent symbol
    for match in PERCENT_PATTERN.finditer(text):
        start, end = match.start(), match.end()
        value = text[start:end]
        result.append(ValueToConvert(value, (start, end), "percent", " procent"))

    return result


def float_to_words(value: str) -> Optional[str]:
    value = float(value)
    integral, decimal = divmod(value, 1)
    decimal = str(round(decimal, 3))[2:]  # Avoid decimal representation errors
    if decimal.startswith("0"):
        decimal_str = " ".join([integer_to_words(d) for d in decimal])
    else:
        decimal_str = integer_to_words(decimal)

    integral_str = integer_to_words(int(integral))
    return f"{integral_str} celá {decimal_str}" if int(decimal) > 0 else integral_str


def integer_to_words(value: Union[int, str]) -> Optional[str]:
    try:
        value = int(value)
    except ValueError:
        return "neznámé číslo"

    if 0 <= value <= 20:
        return NUMBERS[value]

    # Decompose the value to digits
    remainders = []
    while value > 0:
        remainders.append(value % 10)
        value = value // 10

    # Split the digits into groups of 3, where each group is a tuple of (hundreds, tens, ones)
    filled_positions = len(remainders) % 3
    if filled_positions > 0:
        for i in range(3 - filled_positions):
            remainders.append(0)
    groups = [(order, remainders[i:i + 3][::-1]) for order, i in enumerate(range(0, len(remainders), 3))][::-1]
    max_order = groups[0][0]

    # Translate to TTS-friendly format
    result_str = ""
    for order, (hundreds, tens, ones) in groups:
        if hundreds == 0 and tens == 0 and ones == 0:
            continue

        hundreds *= 100
        tens *= 10

        # Translate hundreds part to string
        hundreds_str = "" if hundreds == 0 else f"{NUMBERS[hundreds]} "

        # Translate tens part to string
        if tens == 0:
            tens_str = ""
        elif tens == 10:
            tens_str = f"{NUMBERS[tens + ones]} "
        else:
            tens_str = f"{NUMBERS[tens]} "

        # Translate ones part to string
        if ones == 0 or (order == max_order and ones == 1 and hundreds == 0 and tens == 0) or tens == 10:
            # Avoid outputs such as "jedna tisíc", "dvacet nula" and "dvanáct dva"
            ones_str = ""
        else:
            ones_str = f"{NUMBERS[ones]} "

        result_str += f"{hundreds_str}{tens_str}{ones_str}"

        # Add suffix (word representation of 1000^order)
        if ones == 1 and tens == 0 and hundreds == 0:
            # Special case for 1000 -> "tisíc", 1000000 -> "milión", etc.
            if order == 1:
                result_str += "tisíc "
            if order == 2:
                result_str += "milión "
            elif order == 3:
                result_str += "miliarda "
        elif ones in [2, 3, 4] and tens == 0 and hundreds == 0:
            # Special case for 2000 -> "dva tisíce", 2000000 -> "dva milióny", etc.
            if order == 1:
                result_str += "tisíce "
            elif order == 2:
                result_str += "milióny "
            elif order == 3:
                result_str += "miliardy "
        else:
            # General case, e.g. 12000 -> "dvanáct tisíc", 5000000 -> "pět miliónů", etc.
            if order == 1:
                result_str += "tisíc "
            elif order == 2:
                result_str += "miliónů "
            elif order == 3:
                result_str += "miliard "

    return result_str.strip()


def date_to_words(value: Union[str, datetime.date], current_date: Union[str, datetime.date, None]) -> str:
    if isinstance(current_date, str):
        current_date = datetime.date.fromisoformat(current_date)
    if not isinstance(value, datetime.date):
        try:
            value = datetime.date.fromisoformat(value)
        except (ValueError, TypeError):
            return "neznámé datum"
    if value == current_date:
        return "dnes"
    elif current_date is not None and value == current_date + datetime.timedelta(days=1):
        return "zítra"
    day = DAYS[value.day]
    month = MONTHS[value.month]
    weekday = WEEKDAYS[value.isoweekday()]
    return f"{weekday} {day} {month}"


def time_to_words(value: Union[str, datetime.time]) -> str:
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