import random
import re
from typing import Optional

YES_PATTERN = re.compile(r"\b(m[aá]m|ano|jo)\b", re.IGNORECASE)
NO_PATTERN = re.compile(r"\b(nem[aá]m|ne)\b", re.IGNORECASE)
DONT_KNOW_PATTERN = re.compile(r"\b(nev[ií]m|netuš[ií]m)\b", re.IGNORECASE)
TRANSMISSION_PATTERN = re.compile(r"\b(manu[aá]l.*|automat.*)\b", re.IGNORECASE)
MILEAGE_PATTERN = re.compile(r"\b(\d+|kilometr[ůuy]?|tis[ií]ce?|set|sto|sta|stě)\b", re.IGNORECASE)
PRICE_PATTERN = re.compile(r"\b(\d+|korun|tis[ií]ce?|set|sto|sta|stě)\b", re.IGNORECASE)

# TODO: map to filler hashes in Vocode
NO_PROBLEM = ["Chápu, to nevadí.", "To je v pořádku."]
PERFECT = ["Výborně.", "Skvělé.", "To je skvělá zpráva."]
PERFECT_THANKS = ["Výborně, děkuji.", "Skvělé, děkuji."]
THANKS = "Děkuji."
THANKS_INFO = "Děkuji za informaci."
THANKS_CONFIRM = "Děkuji za potvrzení."
UNDERSTAND = "Rozumím."
UNDERSTAND_THANKS = "Rozumím, děkuji."

YES_ANSWER_MAX_LEN = 15
NO_ANSWER_MAX_LEN = 15
DONT_KNOW_ANSWER_MAX_LEN = 20


def predict_filler_phrase(bot_text: str, user_text: str) -> Optional[str]:
    """Rule-based filler phrase prediction based on pattern matching."""
    bot_text = bot_text.lower()

    # Specific questions and answers
    # TODO: extract SAY strings from the prompt
    if "jste přímo majitelem vozu?" in bot_text:
        if answer_yes(user_text):
            return random.choice(PERFECT_THANKS)
        elif answer_no(user_text):
            return UNDERSTAND_THANKS
    elif "mám to tu uloženo správně?" in bot_text:
        if answer_yes(user_text):
            return THANKS_CONFIRM
        elif answer_no(user_text):
            return UNDERSTAND_THANKS
    elif "kolik má váš vůz najeto kilometrů?" in bot_text:
        if MILEAGE_PATTERN.search(user_text):
            return THANKS_INFO
        elif answer_doesnt_know(user_text):
            return UNDERSTAND
    elif "na kolik si své vozidlo ceníte?" in bot_text:
        if PRICE_PATTERN.search(user_text):
            return THANKS_INFO
        elif answer_doesnt_know(user_text):
            return UNDERSTAND
    elif "jedná se o automatickou nebo manuální převodovku?" in bot_text:
        if TRANSMISSION_PATTERN.search(user_text):
            return THANKS_INFO
        elif answer_doesnt_know(user_text):
            return UNDERSTAND
    elif (
        "máte k vozidlu hliníkové kola?" in bot_text or
        "máte k vozidlu náhradní pneu?" in bot_text or
        "budete mít k vozidlu i servisní knížku?" in bot_text
    ):
        if answer_yes(user_text):
            return random.choice(PERFECT)
        elif answer_no(user_text) or answer_doesnt_know(user_text):
            return random.choice(NO_PROBLEM)

    # General cases
    if re.search(r"\d+", user_text):
        return THANKS_INFO
    elif answer_yes(user_text):
        return THANKS
    elif answer_no(user_text) or answer_doesnt_know(user_text):
        return UNDERSTAND


def answer_yes(user_text: str) -> bool:
    return YES_PATTERN.search(user_text) and len(user_text) <= YES_ANSWER_MAX_LEN


def answer_no(user_text: str) -> bool:
    return NO_PATTERN.search(user_text) and len(user_text) <= NO_ANSWER_MAX_LEN


def answer_doesnt_know(user_text: str) -> bool:
    return DONT_KNOW_PATTERN.search(user_text) and len(user_text) <= DONT_KNOW_ANSWER_MAX_LEN
