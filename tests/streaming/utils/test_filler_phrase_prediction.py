import random

import pytest

from vocode.streaming.utils.filler_phrase_prediction import (
    predict_filler_phrase,
    NO_PROBLEM,
    PERFECT,
    PERFECT_THANKS,
    THANKS,
    THANKS_CONFIRM,
    THANKS_INFO,
    UNDERSTAND,
    UNDERSTAND_THANKS,
)

random.seed(42)


@pytest.mark.parametrize(
    "bot_text, user_text, expected",
    [
        ("Máte k tomu kola?", "Mám.", THANKS),
        ("Máte k tomu kola?", "jo.", THANKS),
        ("Máte k tomu kola?", "mam", THANKS),
        ("Máte k tomu kola?", "Ano, mám.", THANKS),
        ("Máte k tomu kola?", "Ano.", THANKS),
        ("Máte k tomu kola?", "Ne.", UNDERSTAND),
        ("Máte k tomu kola?", "Nemám.", UNDERSTAND),
        ("Máte k tomu kola?", "Ne, nemám.", UNDERSTAND),
        ("Máte k tomu kola?", "Ano ale nevím teď kde jsou.", None),
        ("Máte k tomu kola?", "Ano ty určitě budu někde mít.", None),
        ("Máte k tomu kola?", "Ty už asi teď nemám.", None),
        ("Máte k vozidlu hliníkové kola?", "Ty nemám.", NO_PROBLEM[0]),
        ("Budete mít k vozidlu i servisní knížku?", "Ne.", NO_PROBLEM[0]),
        ("Jste přímo majitelem vozu?", "Jo.", PERFECT_THANKS[1]),
        ("Jste přímo majitelem vozu?", "Je to na firmu.", None),
        ("Na kolik si své vozidlo ceníte?", "Nevím.", UNDERSTAND),
        ("Na kolik si své vozidlo ceníte?", "Na 500 tisíc.", THANKS_INFO),
        ("Na kolik si své vozidlo ceníte?", "pětset tisíc.", THANKS_INFO),
        ("Na kolik si své vozidlo ceníte?", "kolik nabízíte?", None),
        ("Rok výroby je 2015. Mám to tu uloženo správně?", "Ano.", THANKS_CONFIRM),
        ("Rok výroby je 2015. Mám to tu uloženo správně?", "Ne, je to 2016.", UNDERSTAND_THANKS),
        ("Jaký je rok výroby?", "Myslím že 2015.", THANKS_INFO),
        ("Jaký je rok výroby?", "2015", THANKS_INFO),
        ("Kolik má váš vůz najeto kilometrů?", "sto tisíc.", THANKS_INFO),
        ("Kolik má váš vůz najeto kilometrů?", "tisíc", THANKS_INFO),
        ("Kolik má váš vůz najeto kilometrů?", "250000.", THANKS_INFO),
        ("Kolik má váš vůz najeto kilometrů?", "kolem miliónu kilometrů.", THANKS_INFO),
        ("Kolik má váš vůz najeto kilometrů?", "kolem tisíci kilometrů.", THANKS_INFO),
        ("Kolik má váš vůz najeto kilometrů?", "jeden kilometr.", THANKS_INFO),
        ("Kolik má váš vůz najeto kilometrů?", "dva kilometry.", THANKS_INFO),
        ("Kolik má váš vůz najeto kilometrů?", "Nevím.", UNDERSTAND),
        ("Kolik má váš vůz najeto kilometrů?", "Hodně.", None),
        ("Kolik má váš vůz najeto kilometrů?", "To vám teď neřeknu.", None),
        ("Jedná se o automatickou nebo manuální převodovku?", "Automatickou.", THANKS_INFO),
        ("Jedná se o automatickou nebo manuální převodovku?", "Manuální.", THANKS_INFO),
        ("Jedná se o automatickou nebo manuální převodovku?", "automatika.", THANKS_INFO),
        ("Jedná se o automatickou nebo manuální převodovku?", "manuál.", THANKS_INFO),
        ("Jedná se o automatickou nebo manuální převodovku?", "manual", THANKS_INFO),
        ("Jedná se o automatickou nebo manuální převodovku?", "to nevim", UNDERSTAND),
        ("Jaký má auto objem motoru?", "nevím", UNDERSTAND),
        ("Jaký má auto objem motoru?", "vůbec netuším", UNDERSTAND),
        ("Jaký má auto objem motoru?", "nevim možná dva a půl", None),
        ("Budete mít čas zítra?", "ale jo", THANKS),
        ("Ahoj!", "Ahoj.", None),
    ]
)
def test_predict_filler_phrase(bot_text, user_text, expected):
    assert predict_filler_phrase(bot_text, user_text) == expected
