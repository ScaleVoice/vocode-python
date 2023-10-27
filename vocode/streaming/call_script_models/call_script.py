import datetime
import itertools
import json
from abc import ABC, abstractmethod
from copy import copy
from typing import List, Optional, Dict, Tuple, Type, Any, Union

from jinja2 import Template
from pydantic import ValidationError

from vocode.streaming.call_script_models.models import BaseDialogState, OutboundBuyState, ConsoleChatDecision
from vocode.streaming.call_script_models.utils_ours import date_from_weekday, get_jinja_env, load_template, print_colored

SCRIPT_LOCATION_KEY_NAME = 'script_location'

EXIT_SCRIPT_LOCATION = 'EXIT'
ANSWERED_THE_QUESTION = 'user_answered_the_question'
USER_ASKED_GENERAL_QUESTION = 'user_asked_general_question'
USER_ASKED_FAQ_QUESTION = 'user_asked_frequent_question'
INTENT_KEY_NAME = 'INTENT'
CAR_INFORMATION_INIT = 'car_information_init'

JINJA_ENV = get_jinja_env()


class ScriptIntent():
    def __init__(self,
                 name: str,
                 match_examples: List[str],
                 response: str,
                 match_examples_updates: Optional[List[Dict[str, str]]] = None,
                 dialog_state_update: Optional[Dict[str, str]] = None):

        self.name = name
        self.match_examples = [Template(match_example) for match_example in match_examples]
        if match_examples_updates is not None:
            assert len(match_examples) == len(
                match_examples_updates), "match_examples count must match match_examples_updates count."
            self.match_examples_updates = []
            for match_examples_update in match_examples_updates:
                # TODO validate assert all(key in dialog_state.schema()['properties'] for key in match_examples_update.keys())
                match_examples_update_template: Dict[Template, Template] = {Template(key): Template(value) for
                                                                            key, value in match_examples_update.items()}
                match_examples_update_template[Template(INTENT_KEY_NAME)] = Template(name)
                self.match_examples_updates.append(match_examples_update_template)

        else:
            self.match_examples_updates = None

        self.response = JINJA_ENV.from_string(response)
        if dialog_state_update is None:
            dialog_state_update = dict()

        assert INTENT_KEY_NAME not in dialog_state_update
        # Enforces standard and allows testing.
        dialog_state_update_template: Dict[Template, Template] = {Template(INTENT_KEY_NAME): Template(name)}
        dialog_state_update_template.update(
            {Template(key): Template(value) for key, value in dialog_state_update.items()})
        self.dialog_state_update = dialog_state_update_template

    def render_dialog_state_update(self, dialog_state: BaseDialogState, match_example_index: Optional[int] = None):
        dialog_state_dict = dialog_state.dict()
        if match_example_index is None:
            dialog_state_update = self.dialog_state_update

        else:
            dialog_state_update = self.match_examples_updates[match_example_index]

        return {key.render(**dialog_state_dict): value.render(**dialog_state_dict,
                                                              dialog_state_schema=dialog_state.schema(),
                                                              dialog_state=dialog_state) for key, value in
                dialog_state_update.items()}

    def render(self, dialog_state: BaseDialogState):
        return copy(self)


class MatchExampleTemplateScriptIntent(ScriptIntent):

    def __init__(self,
                 name: str,
                 match_examples: List[str],
                 response: str,
                 match_examples_updates: Optional[List[Dict[str, str]]] = None,
                 dialog_state_update: Optional[Dict[str, str]] = None):
        super().__init__(name, match_examples, response, match_examples_updates, dialog_state_update)
        assert len(match_examples) > 0, "At least one match example is supported now."

    def render(self, dialog_state: BaseDialogState):
        rendered_intent = copy(self)
        dialog_state_schema = dialog_state.schema()
        template_property_name = dialog_state.template_property_name
        template_property_schema = dialog_state_schema['properties'][template_property_name]
        if 'enum' in template_property_schema:
            examples = template_property_schema['enum']

        else:
            examples = template_property_schema['examples']

        match_examples_cycle = itertools.cycle(rendered_intent.match_examples)
        rendered_intent.match_examples = []
        for example in examples:
            match_example = next(match_examples_cycle)
            match_example_render = match_example.render(template_property_name=template_property_name,
                                                        template_property_example=example)
            rendered_intent.match_examples.append(JINJA_ENV.from_string(match_example_render))

        rendered_intent.match_examples_updates = [
            {JINJA_ENV.from_string(INTENT_KEY_NAME): JINJA_ENV.from_string(rendered_intent.name),
             JINJA_ENV.from_string(template_property_name): JINJA_ENV.from_string(str(example))}
            for example in examples]

        return rendered_intent


class PrintIntent(ScriptIntent):

    def __init__(self, response: str):
        super().__init__('always_print_below', [], response)


class CallScriptLocation():
    def __init__(self, name: str, goal: str, knowledge: str, intents: List[ScriptIntent],
                 input_states: Optional[List[Union[str, Template]]] = None, append_question_intent=True):

        self.name = name
        self.goal = JINJA_ENV.from_string(goal)
        self.knowledge = JINJA_ENV.from_string(knowledge)
        self.intents = intents
        if input_states is None:
            input_states = []

        self.input_states = input_states
        if append_question_intent:
            self.intents = intents + [
                ScriptIntent(
                    USER_ASKED_GENERAL_QUESTION,
                    ["A jak se jmenujete?", "Kde jste mě našli?", "Odkud máte moje číslo?", "Proč?", "Kde?", "Co?",
                     "Kdo volá?", "Proč?", "Proč bych to měl udělat?"],
                    'Odpověď je, {answer to the question based on the knowledge or the dialog_state}.'),
                ScriptIntent(
                    USER_ASKED_FAQ_QUESTION,
                    ["Kde máte pobočky?", "Můžete mi poradit?", "Jak to pomůže?", "Jaké jsou podmínky?",
                     "Jaké jsou výhody?"],
                    'Odpověď je, {answer to the question based on the knowledge and FAQ and don\'t ask questions}.')
            ]

    def render(self, dialog_state: BaseDialogState, global_input_states: Optional[List[str]]):
        # TODO consider having final string object structure to render into instead.
        # Deepcopy failed due to Template object.
        rendered_script_location = copy(self)
        rendered_script_location.intents = [intent.render(dialog_state) for intent in self.intents]

        # prevent shallow copy
        dialog_state_copy_schema = dialog_state.schema().copy()
        #
        dialog_state_copy_schema['properties'] = copy(dialog_state_copy_schema['properties'])
        dialog_state_copy_schema['properties'][INTENT_KEY_NAME]['enum'] = [i.name for i in
                                                                           rendered_script_location.intents]

        schema_properties__keys = list(dialog_state_copy_schema['properties'].keys())
        assert schema_properties__keys == list(dialog_state.dict().keys()), "Compare keys "

        input_states = []
        for input_state in self.input_states:
            if isinstance(input_state, Template):
                input_state = input_state.render(**dialog_state.dict(), dialog_state_schema=dialog_state_copy_schema)

            input_states.append(input_state)

        dialog_state_dict = dialog_state.dict()

        for property_name in schema_properties__keys:
            if property_name not in global_input_states and property_name not in input_states:
                dialog_state_copy_schema['properties'].pop(property_name)
                dialog_state_dict.pop(property_name)

        return rendered_script_location, dialog_state_copy_schema, dialog_state_dict


class PrintScriptLocation(CallScriptLocation):
    def __init__(self, name: str, goal: str, knowledge: str, output_print: str,
                 input_states: Optional[List[Union[str, Template]]] = None):
        super().__init__(name, goal, knowledge, [PrintIntent(output_print)], input_states=input_states,
                         append_question_intent=False)


INTRODUCTION = CallScriptLocation(
    'introduction',
    'Your goal is to introduce and kindly ask customer to have a short call with you. ALWAYS ONLY EXACTLY ASK THE SENTENCE IN PRINT FUNCTION and always wait for customer answer!!',
    'AAA AUTO platí nejvyšší výkupní ceny na trhu. Jako největší bazar prodáváme nejvíce aut. Ale neakceptujeme každý vůz.',
    [
        ScriptIntent('user_greeting', ["s kým mluvím?", "Kdo volá?"],
                     'Dobrý den ještě jednou, {{ user_salutation }}. Pokud máte minutku, tak pojďme na to, ano?'),
        ScriptIntent('user_is_available_for_call',
                     ["Ano můžu", "Dobře teď můžu", "Dobrý den", "Ano", "Dobře no", "Tak jo"],
                     'Výborně, {{ user_salutation }}. Tak pojďme na to, ano?'),
        ScriptIntent('user_not_available_for_call', ["Teď asi nemám čas.", "Nevim.", "Ne"],
                     '{{ user_salutation }}, je to opravdu jen minutka.'),
        ScriptIntent('user_is_very_negative',
                     ["Běžte do prdele", "Ne, s vama nechci nic řešit", "Neotravujte mě", "už nevolejte"],
                     'Omlouvám se, {{ user_salutation }}. Dobrá tedy, chápu, že své auto nechcete prodat k nám do bazaru, ale ale nechcete aspoň slyšet cenu jakou bychom vám nabídli?'),
    ]
)

# TODO How to render this follow-up message without GPT but also without moving this into decision function? Follow-up function for the transition?
CAR_INFORMATION_PRINT = PrintScriptLocation(
    'car_information_init',
    'Find out the specific missing car property {{ template_property_name }}. Never ask for more parameters in a single sentence. Only ask about {{ template_property_name }}. ALWAYS ONLY EXACTLY ASK THE SENTENCE IN PRINT FUNCTION and always wait for customer answer!!',
    'Abychom mohli auto nakoupit, potřebujeme znát všechny důležité informace pro odhad ceny.',
    "{{ dialog_state_schema['properties'][template_property_name]['ask'] }}",
    input_states=[
        JINJA_ENV.from_string('{{ template_property_name }}'),
        'template_property_name'
    ]
)

CAR_INFORMATION = CallScriptLocation(
    'car_information',
    'Find out the specific missing car property {{ template_property_name }} and then only say thanks.',
    'Abychom mohli auto nakoupit, potřebujeme znát všechny důležité informace pro odhad ceny.',
    [
        MatchExampleTemplateScriptIntent(ANSWERED_THE_QUESTION,
                                         response='Aha. Říkate { {{ template_property_name }} }. Děkuji.',
                                         match_examples=["{{ template_property_example }}.",
                                                         "Je to {{ template_property_example }}.",
                                                         "Mám {{ template_property_example }}."],
                                         match_examples_updates=None,
                                         dialog_state_update={'{{ template_property_name }}': '{corresponding value}'}),

        ScriptIntent('user_doesnt_know',
                     ["To nevím.", "To neznám", "Bohužel nevím", "A jaké jsou možnosti?", "Co by to mohlo být?"],
                     "Chápu, vaše auto může nejspíš být { give examples of {{ template_property_name }}: {{ (dialog_state_schema['properties'][template_property_name]['examples'] if 'examples' in dialog_state_schema['properties'][template_property_name] else dialog_state_schema['properties'][template_property_name]['enum']) |join(', ') }} } ?"),

        ScriptIntent('user_answer_unclear', ["Tam nevim.", "Prosim co?", "Tamto je to.", "Uhuhu", "Ne ne ne"],
                     'Promiňte. Mohl by jste to upřesnit?'),

    ],
    input_states=[
        JINJA_ENV.from_string('{{ template_property_name }}'),
        'template_property_name'
    ]
)

FIND_USERS_CAR_PRICE_PRINT = PrintScriptLocation(
    'find_users_car_price_init',
    'Zjistit cenovou představu zákaznika o jeho voze.',
    'Potřebujeme znát zákaznickou představu, abychom byli schopní udělat co nejlepší nabídku',
    'Teď bych se zeptala, {{ user_salutation }}, kolik za svůj vůj chcete? Pomůže mi to vám dát nejlepší možnou nabídku.'
)

FIND_USERS_CAR_PRICE = CallScriptLocation(
    'find_users_car_price',
    'Zjistit cenovou představu zákaznika.',
    'Chápu, {{ user_salutation }}, že neprodáváte vozy každý týden. Vy však své auto znáte nejlépe a vaše cenová představa nám pomůže zpřesnit naši nabídku – díky tomu dostanete přesnější cenu. Kdybyste si dával inzerát na internet, za jakou byste ho tam dal cenu?',
    [
        ScriptIntent(ANSWERED_THE_QUESTION, ["No asi tak dvestě tisíc", "milión", "šest set tisíc"],
                     match_examples_updates=[{"users_car_price": "200000"}, {"users_car_price": "1000000"},
                                             {"users_car_price": "600000"}, ],
                     response='Aha. Říkáte { users_car_price }. Děkuji. Chcete tedy znát naši nabídku?',
                     dialog_state_update=dict(users_car_price='{corresponding value}')),
        ScriptIntent('users_answer_unclear_or_rejected', ["Teď nevim.", "To vám teď neřeknu.", "Neřeknu"],
                     'Chápu, {{ user_salutation }}, ale nebojte, je to nezávazné. Kolik by vám udělalo radost?'),
        ScriptIntent('users_answer_with_question_about_our_price_offer',
                     ["Kolik by jste dali vy?", "Řekněte mi první vaší nabídku", "No a kolik mi date?",
                      "Řekněte vy první vaší nabídku"],
                     '{{ user_salutation.capitalize() }}, chápu, ale než Vám řeknu naší nabídku, řekněte mi prosím, kolik by vám za vaše auto udělalo radost?')
    ],
    input_states=['users_car_price'],
)

PRICE_OFFER_PRINT = PrintScriptLocation(
    'price_offer_init',
    'Prezentuj cenu auta {{ our_price_offer }} korun. ',
    'Já vám nabízím férovou cenu, slušné jednání a také to, že veškeré záruky za váš vůz přebíráme my, zatímco při prodeji přes inzerát budete za vůz ručit vy. Průměrný počet zájemců, kterým se budete muset věnovat, je asi 20. AAA má nejvyšší ceny, peníze okamžitě, přebíráme záruky, vyřídíme administrativu, celostátní síť poboček, rychlé jednání, bonus při protiúčtu.',
    'Cena je orientační, {{ user_salutation }}, protože vůz musíme vidět na pobočce. Běžná výkupní cena je nižší, ale dnes bych vám mohla nabídnout až {{ our_price_offer }}, protože teď takové vozy sháníme a platíme za ně víc. Je to pro vás zajímavé?',
    input_states=['our_price_offer'],
)

PRICE_OFFER = CallScriptLocation(
    'price_offer',
    'Vyhodnoť jestli zákazník jasně souhlasí s cenou {{ our_price_offer }} Kč za auto.',
    'Já vám nabízím férovou cenu, slušné jednání a také to, že veškeré záruky za váš vůz přebíráme my, zatímco při prodeji přes inzerát budete za vůz ručit vy. Průměrný počet zájemců, kterým se budete muset věnovat, je asi 20. AAA má nejvyšší ceny, peníze okamžitě, přebíráme záruky, vyřídíme administrativu, celostátní síť poboček, rychlé jednání, bonus při protiúčtu.',
    [
        ScriptIntent('user_accepts', ["Ano", "Dobře", "To je v pořádku", "To je fajn"],
                     'Výborně, {{ user_salutation }}, takže domluvíme schůzku. Co na to říkáte?'),
        ScriptIntent('users_thinks_the_price_is_too_low', ["To je málo.", "cena je příliš nízká"],
                     'Je mi jasné, že vaše představa je vyšší, {{ user_salutation }}. U nás ale máte záruku nejvyšší výkupní ceny díky velkému obratu nemusíme vydělávat na jednotlivém autě. Já vám nyní nabízím cenu vyšší právě proto, že vykupujeme vozy pro naši novou pobočku. Dostanete tak víc než kdy jindy a kdekoliv jinde, pojďme využít té šance a já vám zajistím přednostní jednání.'),
        ScriptIntent('user_wants_to_sell_alone', ["prodám si vůz sám přes inzerát"],
                     '{{ user_salutation.capitalize() }}, tomu rozumím. V inzerci se však do půl roku prodá jen pětina vozů. To znamená, že zbytečně budete trávit svůj čas projížďkou s lidmi, které vůbec neznáte a bez záruk. Můžeme se tedy domluvit na naší výkupní částce?'),
        ScriptIntent('users_saw_higher_prices_online', ["na internetu se takové vozy nabízejí za vyšší částky"],
                     'To máte úplnou pravdu, skutečně se za vyšší částky nabízejí, ale neprodávají se. Auto ztrátí svou hodnotu  nakonec za něj dostanete méně než teď. Já vám nabízím okamžitou výplatu celé částky, je to férová cena. Můžeme se tedy domluvit na naší výkupní částce?'),
    ],
    input_states=['our_price_offer'],
)

SCHEDULE_INSPECTION_APPOINTMENT_PRINT = PrintScriptLocation(
    'schedule_inspection_appointment_init',
    'Uzavři schůzku na nejbližší možný termín, nejlépe dnes na pobočce {{ branch_location }}',
    'Máme otevřeno od devíti do devíti každý den. Můžete přijít kdykoliv, ale nejlépe co nejdříve do pár dní. Máme otevřeno i o víkendu. Máme pobočku otevřenou do devíti hodin. Máte možnost se dříve uvolnit?',
    'Tak, a v kolik se dnes uvidíme? Můžete odpoledne nebo až večer?',
    input_states=['branch_location', "inspection_appointment_time", "inspection_appointment_date"],
)

SCHEDULE_INSPECTION_APPOINTMENT = CallScriptLocation(
    'schedule_inspection_appointment',
    "Uzavři schůzku na nejbližší možný termín, nejlépe dnes a za týden je pozdě. Ptej se dokud není jasné datum a čas na pobočce {{ branch_location }}.",
    'Máme otevřeno od devíti do devíti každý den. Můžete přijít kdykoliv, ale nejlépe co nejdříve do pár dní. Máme otevřeno i o víkendu. Máme pobočku otevřenou do devíti hodin. Máte možnost se dříve uvolnit? Dnes je {{ current_date|date_to_tts(current_date) }}. Teď je {{ current_time|time_to_tts }}.',
    [
        ScriptIntent('user_agreed_to_arrive_soon',
                     [
                         "Asi bych si to mohl zařídit a přijít v šest dnes.",
                         "Tak dobře, tedy zítra v 9"
                     ],
                     match_examples_updates=[
                         {"inspection_appointment_time": "18:00", "inspection_appointment_date": "{{ current_date }}"},
                         {"inspection_appointment_time": "09:00",
                          "inspection_appointment_date": "{{ dialog_state.get_tomorrow() }}"}
                     ],
                     response='Aha. Jsem moc ráda, že se nám takto podařilo vše domluvit.',
                     dialog_state_update={"inspection_appointment_time": '{corresponding time value}',
                                          "inspection_appointment_date": '{corresponding date value}'}
                     ),
        ScriptIntent('user_rejects_without_obstacle', ["dnes nemůžu přijet", "tento týden to nepůjde"],
                     'Proč dnes nemůžete přijet?'),
        ScriptIntent('user_rejects_with_obstacle', ["Nemám čas", "Jsem v práci", "hlídám děti"],
                     'Chápu, že {INSERT USERS_JUST_MENTIONED_OBSTACLE}. Ale co kdyby jste {INSERT ARGUMENTS_TO_REMOVE_OBSTACLE}, protože když přijdete dnes tak {INSERT ARGUMENTS_WHY_COME_TODAY}. Šlo by to ještě dnes?')
    ],
    input_states=['branch_location', "inspection_appointment_time", "inspection_appointment_date"],
)

CONFIRM_INSPECTION_APPOINTMENT_PRINT = PrintScriptLocation(
    'confirm_inspection_appointment_init',
    'Potvrdit, že zákazník přijde na schůzku v {{ inspection_appointment_date|date_to_tts(current_date) }} v {{ inspection_appointment_time|time_to_tts }} na pobočku { {{ branch_location }} } ',
    'Sebou si zakazník potřebuje: Povinné – OP, druhý doklad totožnosti, velký technický průkaz, zelená karta od pojištění. Doporučené – servisní kniha, kompletní klíče, malý technický průkaz. Pokud je v TP neukončený leasing, originál plné moci od leasing společnosti.',
    'Počítám tedy s vámi že určitě přijedete {{ inspection_appointment_date|date_to_tts(current_date) }} v {{ inspection_appointment_time|time_to_tts }} na pobočku {{ branch_location }}, je to tak?'
)

CONFIRM_INSPECTION_APPOINTMENT = CallScriptLocation(
    'confirm_inspection_appointment',
    'Potvrdit, že zákazník přijde na schůzku v {{ inspection_appointment_date|date_to_tts(current_date) }} v {{ inspection_appointment_time|time_to_tts }} na pobočku { {{ branch_location }} }. Dnes je {{ current_date }}. Teď je {{ current_time }}.',
    'Sebou si zakazník potřebuje: Povinné – OP, druhý doklad totožnosti, velký technický průkaz, zelená karta od pojištění. Doporučené – servisní kniha, kompletní klíče, malý technický průkaz. Pokud je v TP neukončený leasing, originál plné moci od leasing společnosti.',
    [
        ScriptIntent('user_accepts', ["Ano", "Dobře", "To je v pořádku", "To je fajn"],
                     'Výborně, {{ user_salutation }}, takže domluvíme schůzku. Co na to říkáte?'),
        ScriptIntent('user_rejected_or_changes', ["Nechci.", "Ne", "Spíše v devět."],
                     'Chápu, {{ user_salutation }}, tak se pojďme domluvit na jindy, ano?'),
        ScriptIntent('users_answer_unclear_or_rejected', ["To vám teď neřeknu.", "Nevim ještě.", ],
                     'Chápu, {{ user_salutation }}, tak se pojďme domluvit na jindy, ano?'),
    ],
    input_states=['branch_location', "inspection_appointment_time", "inspection_appointment_date"],
)

GOODBYE_PRINT = PrintScriptLocation(
    'good_bye_init',
    'Potvrdit, že zákazník přijde na schůzku a vezme potřebné dokumenty.',
    'Povinné – OP, druhý doklad totožnosti, velký technický průkaz, zelená karta od pojištění. Doporučené – servisní kniha, kompletní klíče, malý technický průkaz. Pokud je v TP neukončený leasing, originál plné moci od leasing společnosti.',
    'Tak {{ inspection_appointment_date|date_to_tts(current_date) }} v {{ inspection_appointment_time|time_to_tts }}. Vemte si určitě druhý doklad totožnosti, velký technický průkaz, zelená karta od pojištění. Na to nezapomeňte, prosím. A raději také servisní knihu, kompletní klíče, malý technický průkaz. Pokud je v TP neukončený leasing, originál plné moci od leasing společnosti. Ano?'
)

GOOD_BYE = CallScriptLocation(
    'good_bye',
    'Potvrdit, že zákazník přijde na schůzku a vezme potřebné dokumenty.',
    'Povinné – OP, druhý doklad totožnosti, velký technický průkaz, zelená karta od pojištění. Doporučené – servisní kniha, kompletní klíče, malý technický průkaz. Pokud je v TP neukončený leasing, originál plné moci od leasing společnosti.',
    [
        ScriptIntent('user_confirms', ["Ano?", "Dobře"], 'Výborně, {{ user_salutation }}. Tak se uvidíme.'),
        ScriptIntent('users_answer_unclear_or_rejected', ["Nevim.", "Ne"], 'Aha, takže zpět.')
    ],
    input_states=['branch_location', "inspection_appointment_time", "inspection_appointment_date"],
)


class NormalizationPromptExamples:
    def __init__(self, field_name: str, examples: List[Tuple[str, str]], dialogue_state_class: Type[BaseDialogState]):
        self.field_name = field_name
        self.examples = examples
        self.enum = dialogue_state_class().schema()['properties'][field_name].get('enum')

    def render(self) -> str:
        examples_heading = f"Here are some examples of correct normalizations for {self.field_name} values:"
        examples = (
                "```\n" +
                "\n".join([f"{example} -> {normalized}" for example, normalized in self.examples]) +
                "\n```"
        )
        if self.enum:
            value_list_heading = f"For {self.field_name}, normalize the input to one of the following values:"
            value_list = "\n".join([f"* {v}" for v in self.enum])
            return "\n\n".join([value_list_heading, value_list, examples_heading, examples])
        else:
            return "\n\n".join([examples_heading, examples])


DATE_NORMALIZATION_EXAMPLES = NormalizationPromptExamples(
    field_name="inspection_appointment_date",
    examples=[
        ("dnes", OutboundBuyState().current_date.isoformat()),
        ("zítra", (OutboundBuyState().current_date + datetime.timedelta(days=1)).isoformat()),
        ("pozítří", (OutboundBuyState().current_date + datetime.timedelta(days=2)).isoformat()),
        ("v pondělí", date_from_weekday(OutboundBuyState().current_date, 1).isoformat()),
        ("v pátek", date_from_weekday(OutboundBuyState().current_date, 5).isoformat()),
    ],
    dialogue_state_class=OutboundBuyState,
)

TIME_NORMALIZATION_EXAMPLES = NormalizationPromptExamples(
    field_name="inspection_appointment_time",
    examples=[
        ("tak ve tři", "15:00"),
        ("kolem devíti ráno", "09:00"),
        ("na desátou", "10:00"),
        ("půl deváté ráno", "08:30"),
        ("v půl devátý večer", "20:30"),
        ("na půl jedenáctou dopoledne", "10:30"),
        ("čtvrt na dvě", "13:15"),
        ("třičtvrtě na pět", "16:45"),
        ("za hodinu", (datetime.datetime.combine(datetime.date.today(),
                                                 OutboundBuyState().current_time) + datetime.timedelta(
            hours=1)).time().isoformat(timespec="minutes")),
        ("za dvě hodiny", (datetime.datetime.combine(datetime.date.today(),
                                                     OutboundBuyState().current_time) + datetime.timedelta(
            hours=2)).time().isoformat(timespec="minutes")),
    ],
    dialogue_state_class=OutboundBuyState,
)

PRICE_NORMALIZATION_EXAMPLES = NormalizationPromptExamples(
    field_name="users_car_price",
    examples=[
        ("třicet tisíc", "30000"),
        ("šedesát pět tisíc", "65000"),
        ("alespoň pade", "50000"),
        ("stotisíc", "100000"),
        ("stovku", "100000"),
        ("kilo", "100000"),
        ("litr", "1000"),
        ("stodvacet tisíc", "120000"),
        ("sto devadesát tisíc", "190000"),
        ("sto padesát sedum tisíc", "157000"),
        ("milión", "1000000"),
    ],
    dialogue_state_class=OutboundBuyState,
)

CAR_MILEAGE_NORMALIZATION_EXAMPLES = NormalizationPromptExamples(
    field_name="car_mileage",
    examples=[
        ("třicet tisíc", "30000"),
        ("šedesát pět tisíc", "65000"),
        ("stotisíc", "100000"),
        ("stotisíc kilometrů", "100000"),
        ("stovku", "100000"),
        ("stodvacet", "120000"),
        ("stodvacet tisíc", "120000"),
        ("dvěstě tisíc", "200000"),
        ("200 tisíc", "200000"),
        ("sto padesát sedum tisíc", "157000"),
    ],
    dialogue_state_class=OutboundBuyState,
)

YEAR_NORMALIZATION_EXAMPLES = NormalizationPromptExamples(
    field_name="car_manufacture_year",
    examples=[
        ("tenhle rok", str(OutboundBuyState().current_date.year)),
        ("loni", str(OutboundBuyState().current_date.year - 1)),
        ("dvatisíce 3", "2003"),
        ("dva tisíce třináct", "2013"),
        ("dva osum", "2008"),
        ("dva patnáct", "2015"),
        ("dva devatenáct", "2019"),
        ("devadesát pět", "1995"),
        ("devadesát šest", "1996"),
        ("devatenáct", "2019"),
    ],
    dialogue_state_class=OutboundBuyState,
)

CAR_FUEL_NORMALIZATION_EXAMPLES = NormalizationPromptExamples(
    field_name="car_fuel",
    examples=[
        ("nafta", "diesel"),
        ("dýzl", "diesel"),
        ("propan butan", "LPG"),
        ("autoplyn", "LPG"),
        ("zkapalněný ropný plyn", "LPG"),
        ("metan", "CNG"),
        ("zemní plyn", "CNG"),
        ("ztlačený zemní plyn", "CNG"),
        ("etanol", "ethanol"),
        ("biolíh", "ethanol"),
        ("bioetanol", "ethanol"),
        ("elektrický", "elektro"),
    ],
    dialogue_state_class=OutboundBuyState,
)


class CallScript(ABC):
    def __init__(self, script_goal: str, global_input_states: Optional[List[str]],
                 script_locations: List[CallScriptLocation], dialog_state: BaseDialogState,
                 text_template: str, dialog_state_prompt: str, normalization_prompt: str,
                 normalization_examples: List[NormalizationPromptExamples]):

        self.script_goal = JINJA_ENV.from_string(script_goal)
        if global_input_states is None:
            global_input_states = []

        if INTENT_KEY_NAME not in global_input_states:
            global_input_states += [INTENT_KEY_NAME, SCRIPT_LOCATION_KEY_NAME]

        self.global_input_states = global_input_states
        self.script_locations = script_locations
        self.dialog_state = dialog_state
        self._text_template = text_template
        self._dialog_state_prompt = dialog_state_prompt
        self._normalization_prompt = normalization_prompt
        self.normalization_examples = normalization_examples
        self.location_to_script: Dict[str, CallScriptLocation] = {location.name: location for location in
                                                                  script_locations}

    # HACK for twilio JSON to redis serialization.
    @property
    def text_template(self):
        return Template(self._text_template)

    @property
    def dialog_state_prompt(self):
        return Template(self._dialog_state_prompt)

    @property
    def normalization_prompt(self):
        return Template(self._normalization_prompt)

    def render_text_prompt(self, override_dialog_state: Optional[dict] = None):
        if override_dialog_state is not None:
            dialog_state_copy = self.dialog_state.copy(update=override_dialog_state)
        else:
            dialog_state_copy = self.dialog_state.copy()

        call_script_location, dialog_state_schema_copy, dialog_state_dict = self.location_to_script[
            dialog_state_copy.script_location].render(
            dialog_state_copy,
            self.global_input_states
        )

        text_template_render = self.text_template.render(
            dialog_state_extraction=False,
            script_goal=self.script_goal,
            script=call_script_location,
            dialog_state=dialog_state_dict,
            dialog_state_str=self.get_dialog_state_str(dialog_state_dict, dialog_state_schema_copy),
            dialog_state_schema_str=self.get_dialog_state_update_openai_function(
                dialog_state_schema_copy,
                name="dialog_state_schema",
                schema_description=None),
            dialog_state_schema=dialog_state_schema_copy)

        print_colored(f'local_state: {dialog_state_dict}', 'yellow')
        return text_template_render

    def render_dialog_state_prompt_and_function(self, override_dialog_state: Optional[dict] = None):
        if override_dialog_state is not None:
            dialog_state_copy = self.dialog_state.copy(update=override_dialog_state)
        else:
            dialog_state_copy = self.dialog_state.copy()

        call_script_location, dialog_state_schema_copy, dialog_state_dict = self.location_to_script[
            dialog_state_copy.script_location].render(
            dialog_state_copy, self.global_input_states)

        prompt_render = self.dialog_state_prompt.render(
            dialog_state_extraction=True,
            script_goal=self.script_goal,
            script=call_script_location,
            dialog_state=dialog_state_dict,
            dialog_state_str=self.get_dialog_state_str(dialog_state_dict, dialog_state_schema_copy),
            dialog_state_schema=dialog_state_schema_copy,
        )
        function = self.get_dialog_state_update_openai_function(dialog_state_schema_copy)
        return prompt_render, function

    def render_normalization_prompt(self, keys_to_normalize: List[str]):
        today = self.dialog_state.dict().get("current_date") or datetime.date.today()
        normalization_examples = [
            example for example in self.normalization_examples if example.field_name in keys_to_normalize
        ]
        examples = "\n\n".join(examples.render() for examples in normalization_examples)
        prompt_render = self.normalization_prompt.render(examples=examples)
        return prompt_render

    @abstractmethod
    def decision_callback(self, response: 'ConsoleChatResponse') -> 'ConsoleChatDecision':
        pass

    def get_dialog_state_str(self, dialog_state_dict: Dict[str, Any], dialog_state_schema: dict):
        filtered = {}
        for prop, value in dialog_state_dict.items():
            if not dialog_state_schema['properties'][prop].get('hidden', False):
                if isinstance(value, datetime.date):
                    value = value.isoformat()
                elif isinstance(value, datetime.time):
                    value = value.isoformat(timespec="minutes")
                filtered[prop] = value

        return self.json_dump(filtered)

    @staticmethod
    def json_dump(d: dict):
        return json.dumps(d, indent=2, ensure_ascii=False)

    def get_dialog_state_update_openai_function(self,
                                                dialog_state_copy_schema: dict,
                                                include_descriptions: bool = False,
                                                name: Optional[str] = "get_argument_values",
                                                schema_description: Optional[
                                                    str] = "Get values for arguments mentioned in the current turn."
                                                ) -> dict:
        """
        Reused for text prompt rendering, otherwise could be moved to the ChatGPTAgent
        """
        schema = {
            "name": name,
            "description": schema_description,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            }
        }
        keys = ['type', 'enum', 'examples']
        if include_descriptions:
            keys.remove('examples')
            keys.append('description')
        for prop, details in dialog_state_copy_schema['properties'].items():
            if prop != "script_location" and not details.get('hidden', False):
                schema["parameters"]["properties"][prop] = {
                    key: details[key] for key in keys if key in details
                }
                if include_descriptions and "examples" in details:
                    examples = (
                            "Examples: " +
                            ", ".join(self.format_schema_example(example) for example in details["examples"]) + "."
                    )
                    if "description" not in details:
                        schema["parameters"]["properties"][prop]["description"] = examples
                    else:
                        schema["parameters"]["properties"][prop]["description"] += " " + examples
        return schema

    @staticmethod
    def format_schema_example(example: Any) -> str:
        if isinstance(example, str):
            return '"' + str(example) + '"'
        else:
            return str(example)


class OutboundBuyCallScript(CallScript):
    VALIDATION_KEYS = (
        'users_car_price',
        'inspection_appointment_date',
        'inspection_appointment_time',
        'car_manufacture_year',
        'car_mileage',
        'car_fuel',
    )
    ENUM_VALIDATION_KEYS = ("car_fuel",)

    def __init__(self, dialog_state: OutboundBuyState):
        self.dialog_state = dialog_state
        super().__init__(
            'Zákazník prodává ojetý vůz.',
            ['current_date', 'current_time', 'user_first_name', 'user_last_name', 'user_salutation', 'car_model_name'],
            [INTRODUCTION, CAR_INFORMATION_PRINT, CAR_INFORMATION, FIND_USERS_CAR_PRICE_PRINT, FIND_USERS_CAR_PRICE,
             PRICE_OFFER_PRINT, PRICE_OFFER, SCHEDULE_INSPECTION_APPOINTMENT_PRINT, SCHEDULE_INSPECTION_APPOINTMENT,
             CONFIRM_INSPECTION_APPOINTMENT_PRINT, CONFIRM_INSPECTION_APPOINTMENT, GOODBYE_PRINT, GOOD_BYE],
            dialog_state,
            load_template("general_call_script.jinja"),
            load_template("general_call_script.jinja"),
            load_template("normalization.jinja"),
            [
                DATE_NORMALIZATION_EXAMPLES,
                TIME_NORMALIZATION_EXAMPLES,
                PRICE_NORMALIZATION_EXAMPLES,
                YEAR_NORMALIZATION_EXAMPLES,
                CAR_MILEAGE_NORMALIZATION_EXAMPLES,
                CAR_FUEL_NORMALIZATION_EXAMPLES,
            ],
        )

    @staticmethod
    def validate_updated_values(dialogue_state_update: dict) -> List[dict]:
        try:
            OutboundBuyState(**dialogue_state_update)
        except ValidationError as exc:
            errors = exc.errors()
        else:
            errors = []
        return errors

    def get_values_to_normalize(self, errors: List[Tuple[str, str, str]], dialog_state_update: dict) -> dict:
        type_error_keys = [
            key
            for key, error_type, _ in errors
            if error_type in ("type_error.integer", "value_error.date", "value_error.time")
               or key in self.ENUM_VALIDATION_KEYS
        ]
        values_to_normalize = {k: dialog_state_update[k] for k in type_error_keys}

        if values_to_normalize:
            values_to_normalize["current_date"] = self.dialog_state.current_date
            values_to_normalize["current_time"] = self.dialog_state.current_time
            # TODO: add other context values but ignore them after normalization

        return values_to_normalize

    def decision_callback(self, response: 'ConsoleChatResponse', normalize: bool = True) -> 'ConsoleChatDecision':
        def get_missing_car_information():
            for information in ['car_model_name', 'car_manufacture_year', 'car_transmission', 'car_body', 'car_fuel',
                                'car_mileage']:
                if getattr(self.dialog_state, information) is None:
                    return information

            return None

        validation_errors = self.validate_updated_values(response.dialog_state_update)
        relevant_errors = [
            (error["loc"][0], error["type"], error["msg"])
            for error in validation_errors if error["loc"][0] in self.VALIDATION_KEYS
        ]
        if normalize and relevant_errors:
            values_to_normalize = self.get_values_to_normalize(relevant_errors, response.dialog_state_update)
            if values_to_normalize:
                response.values_to_normalize = values_to_normalize
                return ConsoleChatDecision(normalize=True, say_now_raw_text=None, response=response)

        intent = response.dialog_state_update.get('INTENT')
        if self.dialog_state.script_location == 'introduction':
            if intent in ('user_greeting', 'user_is_available_for_call'):
                missing_car_information = get_missing_car_information()
                if missing_car_information is None:
                    # FIXME, need to router to the last not finished script section instead
                    self.dialog_state.script_location = 'find_users_car_price'
                    return ConsoleChatDecision(say_now_raw_text='O autě teď mám všechno. Tak pojďme dále.',
                                               response=response)

                else:
                    self.dialog_state.script_location = 'car_information'
                    self.dialog_state.template_property_name = missing_car_information

                self.dialog_state.script_location = 'car_information'
                return ConsoleChatDecision(say_now_script_location=CAR_INFORMATION_INIT, response=response)

            else:
                return ConsoleChatDecision(response=response)

        elif self.dialog_state.script_location == 'car_information':
            if intent == ANSWERED_THE_QUESTION:
                # FIXME validation
                template_property_value = response.dialog_state_update.get(self.dialog_state.template_property_name)
                if template_property_value is None:
                    return ConsoleChatDecision(say_now_script_location=CAR_INFORMATION_INIT, response=response)

                setattr(self.dialog_state, self.dialog_state.template_property_name, template_property_value)
                missing_car_information = get_missing_car_information()
                if missing_car_information is not None:
                    self.dialog_state.template_property_name = missing_car_information
                    return ConsoleChatDecision(say_now_script_location=CAR_INFORMATION_INIT, response=response)

                else:
                    # TODO How to make sure that the last response is either empty or just a static text?
                    self.dialog_state.script_location = 'find_users_car_price'
                    return ConsoleChatDecision(say_now_script_location='find_users_car_price_init', response=response)

            elif intent == 'user_doesnt_know':
                return ConsoleChatDecision(response=response)

            elif intent == 'user_answer_unclear':
                return ConsoleChatDecision(response=response)

            return ConsoleChatDecision(say_now_script_location=CAR_INFORMATION_INIT, response=response)

        elif self.dialog_state.script_location == 'find_users_car_price':
            if intent == ANSWERED_THE_QUESTION:
                self.dialog_state.users_car_price = response.dialog_state_update.get('users_car_price')
                self.dialog_state.script_location = 'price_offer'
                return ConsoleChatDecision(say_now_script_location='price_offer_init', response=response)

            else:
                return ConsoleChatDecision(response=response)

        elif self.dialog_state.script_location == 'price_offer':
            if intent == "user_accepts":
                self.dialog_state.script_location = 'schedule_inspection_appointment'
                # TODO try without, but it helps to get on rails
                return ConsoleChatDecision(say_now_script_location='schedule_inspection_appointment_init',
                                           response=response)

            else:
                return ConsoleChatDecision(response=response)

        elif self.dialog_state.script_location == 'schedule_inspection_appointment':
            if response.dialog_state_update.get('inspection_appointment_date') is not None:
                self.dialog_state.inspection_appointment_date = response.dialog_state_update.get(
                    'inspection_appointment_date')

            if response.dialog_state_update.get('inspection_appointment_time') is not None:
                self.dialog_state.inspection_appointment_time = response.dialog_state_update.get(
                    'inspection_appointment_time')

            if intent == "user_agreed_to_arrive_soon":
                if self.dialog_state.inspection_appointment_date is None:
                    return ConsoleChatDecision(
                        say_now_raw_text="Ale chybí nám tu ještě datum. Kdy nejdříve by jste mohl?", response=response)

                if self.dialog_state.inspection_appointment_time is None:
                    return ConsoleChatDecision(
                        say_now_raw_text="Ale chybí nám tu ještě čas. Kdy nejdříve by jste mohl?", response=response)

                self.dialog_state.script_location = "confirm_inspection_appointment"
                return ConsoleChatDecision(say_now_script_location='confirm_inspection_appointment_init',
                                           response=response)

            else:
                return ConsoleChatDecision(response=response)

        elif self.dialog_state.script_location == "confirm_inspection_appointment":
            if intent == "user_accepts":
                self.dialog_state.script_location = 'good_bye'
                return ConsoleChatDecision(say_now_script_location='good_bye_init', response=response)

            elif intent in ("users_answer_unclear_or_rejected", "user_rejected_or_changes"):
                # TODO improve the logic
                self.dialog_state.inspection_appointment_date = None
                self.dialog_state.inspection_appointment_time = None

                self.dialog_state.script_location = 'schedule_inspection_appointment'
                return ConsoleChatDecision(say_now_script_location='schedule_inspection_appointment_init',
                                           response=response)

            else:
                return ConsoleChatDecision(response=response,
                                           say_now_script_location="confirm_inspection_appointment_init")

        elif self.dialog_state.script_location == 'good_bye':
            if intent == "user_confirms":
                print("END OF CALL")
                self.dialog_state.script_location = EXIT_SCRIPT_LOCATION
                return ConsoleChatDecision(response=response)

            else:
                return ConsoleChatDecision(response=response)

        else:
            return ConsoleChatDecision(response=response)


if __name__ == '__main__':
    value = OutboundBuyCallScript(OutboundBuyState(script_location=CAR_INFORMATION.name)).render_text_prompt(
        dict(template_property_name='car_model_name'))
    print(value)
