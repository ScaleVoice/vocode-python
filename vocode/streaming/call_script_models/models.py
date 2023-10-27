from __future__ import annotations

import datetime
import json
from abc import ABC
from dataclasses import dataclass
from typing import Optional, Union, ClassVar, List

from pydantic import BaseModel, Field, validator

from vocode.streaming.call_script_models.response_validator import ValidationResult

TIME_EXAMPLES = ["11:15", "09:30", "21:00"]
DATE_EXAMPLES = ["2023-01-11", "2024-10-27"]


@dataclass
class ConsoleChatResponse:
    message: str
    dialog_state_update: Optional[dict]
    raw_text: str
    failed_validation: Optional[ValidationResult] = None
    values_to_normalize: Optional[dict] = None

    @property
    def has_failed_validation(self):
        return self.failed_validation is not None

    @property
    def values_to_prompt_format(self) -> str:
        """Values to normalize in GPT functions friendly format
        :return: str with values to normalize
        """
        content = ""
        for key, value in self.values_to_normalize.items():
            if value is None:
                value = "null"
            content += f'{key}: {value}\n'
        return content


class ConsoleChatDecision(BaseModel):
    response: ConsoleChatResponse
    say_now_raw_text: Optional[str] = None
    say_now_script_location: Optional[str] = None
    retry: bool = None
    normalize: bool = False


class BaseDialogState(BaseModel, ABC):
    script_location: str = Field("introduction", examples=["closing", "router"], hidden=True)
    INTENT: Optional[str] = Field(
        None,
        description="The user's intent based on the last turn.",
        # enum=[ Fill-in in your implementation ]
        required=True
    )
    template_property_name: Optional[str] = Field(None, hidden=True)

    def __str__(self):
        return self.dict().__str__()


class RestaurantDialogStateModel(BaseDialogState):
    restaurant_name: str = None
    restaurant_address: str = None
    restaurant_phone_number: str = None
    restaurant_website: str = None
    restaurant_rating: str = None
    restaurant_price_range: str = None
    restaurant_cuisine: str = None
    restaurant_opening_hours: str = None


class RRExperimentBeliefState(BaseDialogState):
    my_name: str
    customer_title: str
    customer_name: str
    car_of_interest: str

    current_date: datetime.date = datetime.date.today()
    current_time: str = datetime.datetime.now().strftime("%H:%M")
    current_day: str = datetime.datetime.now().strftime("%A")

    branch_location: str = None
    branch_address: str = None

    def decision_callback(self, response: 'ConsoleChatResponse'):
        # TODO return ConsoleChatDecision
        pass


# class ProgramMemory(BaseBeliefState):
# dialog_state: BeliefStateModel = BeliefStateModel()

# def finacing(self, response):
#     if "Chci financovat" in response:
#         return True

# say_now= []
# def parse_reposne(self, response):
#     if self.address = 'financing':
#         parsed_response = response.split(' ')
#         self.dialog_state[]
#         retries +\
#
#     elif self.address = 'schedule_meeting':


class OutboundBuyState(BaseDialogState):
    BRANCH_OPENS: ClassVar[datetime.time] = Field(datetime.time(9, 0, 0), hidden=True)
    BRANCH_CLOSES: ClassVar[datetime.time] = Field(datetime.time(21, 0, 0), hidden=True)
    INTENT: Optional[str] = Field(
        None,
        description="The user's intent based on the last turn.",
        # This is dynamically changed property, so enum is set empty to avoid confusion.
        enum=[],
        required=True
    )

    current_date: datetime.date = Field(
        datetime.date.today(),
        description="Current date.",
        examples=DATE_EXAMPLES,
    )
    current_time: datetime.time = Field(
        datetime.datetime.now().time(),
        description="Current time.",
        examples=TIME_EXAMPLES,
    )

    user_first_name: str = Field(None, description="The first name of the user.", examples=["Michal", "František"])
    user_last_name: str = Field(None, description="The last name of the user.", examples=["Kovář", "Novák"])
    user_salutation: str = Field(None, description="How to call the user.",
                                 examples=["pane Potočka", "paní Habrman"])

    car_model_name: Optional[str] = Field(
        None,
        description="The model name of the user's car.",
        examples=["Renault Megane", "Škoda Superb"],
        ask="Jaký je model vašeho auta?",
    )
    car_manufacture_year: Optional[int] = Field(
        None,
        description="The manufacturing year of the customer car.",
        examples=[
            2018,
            2020,
            2011,
            2010,
            "90 osum",
            "dva tisíce 6"
            "2000 pět",
            "2 22",
            "dva tisíce patnáct",
            "dva sedumnáct",
        ],
        ge=1886,
        le=datetime.date.today().year,
        ask="Jaký je rok výroby vašeho vozu?",
    )

    car_transmission: Optional[str] = Field(
        None,
        description="The transmission type of the user's engine.",
        enum=["automat", "manuál"],
        ask="Jaký je typ převodovky vašeho vozu?",
    )

    car_body: Optional[str] = Field(
        None,
        description="The body type of the user's car.",
        enum=["sedan", "hatchback", "SUV", "kombi", "MPV", "off road", "kupé", "kabriolet", "pickup"],
        ask="Jaký je typ karoserie vašeho vozu?",
    )

    car_fuel: Optional[str] = Field(
        None,
        description="The fuel type of the user's car.",
        enum=["benzín", "diesel", "LPG", "CNG", "hybrid", "ethanol", "elektro"],
        examples=[
            "benzín",
            "diesel",
            "dýzl",
            "nafta",
            "naftový",
            "lpg",
            "cng",
            "biolíh",
            "hybrid",
            "elektro",
        ],
        ask="Jaké pohonné palivo používá váš vůz?",
    )

    car_engine_power_kw: Optional[int] = Field(
        None,
        description="The engine power of the user's car.",
        examples=[110, 160],
        gt=60,
        lt=300,
        ask="Jaký je výkon motoru vašeho vozu v kilowatech?",
    )

    # car_model_version = Field(2017, examples=[2018, 2019])  # in case of not certain from the year
    # seats_count = Field(4, examples=[4, 8])
    # size
    # car_interest = Field("hitlist", examples=["hitlist", "seen", "old_seen"])
    car_mileage: int = Field(
        None,
        description="The mileage of the user's car (in kilometers).",
        examples=[40_000, 80_000, 250_000],
        ge=0,
        lt=4_828_032,
        ask="Kolik má najeto váš vůz v kilometrech?",
    )

    # spz_id = Field("4A2 3000", examples=["4A2 3000", "1P1 0000"])
    # Motor + KW
    # filled service book
    # owner count
    # ...

    users_car_price: int = Field(
        None,
        description="The price for which the user offers to sell their car.",
        examples=[
            "třicet tisíc",
            "dvěstě tisíc",
            "stotisíc",
            "stodvacet tisíc",
            "150 tisíc",
            "100 padesát tisíc",
            "dvacet 1000",
            "sto 1000",
            "dvěstě 1000",
            "40 pět tisíc",
            "sto padesát",
            "milión",
            200_000,
            300_000,
        ],
        gt=0,
        lt=3_322_917_000,
    )
    our_price_offer: int = Field(
        None,
        description="The price for which we offer to buy the user's car.",
        gt=0,
        lt=3_322_917_000,
    )

    is_inspection_meeting_at_company_branch = Field(True, enum=[True, False])
    non_branch_inspection_meeting_address: Optional[str] = Field(
        None,
        examples=["Líšnice 3, 252 10 Líšnice", "B. Jelínka 40, 533 61 Choltice"],
        ask="Kde byste se chtěl sejít?",
    )
    inspection_appointment_date: Union[datetime.date, None] = Field(
        None,
        description='The date of the scheduled appointment with the user.',
        examples=[
            "dnes",
            "zítra",
            "pozítří",
            "v pondělí",
            "v pátek",
            "druhého července",
            "příští středu",
            "2. 8."
            "5. října",
            "12. 3. 2023"
        ],
    )
    inspection_appointment_time: Union[datetime.time, None] = Field(
        None,
        description=(
            'The time of the scheduled appointment with the user. Don\'t extract any value if the time is not '
            'specific (e.g. "dopoledne", "večer" or "kolem oběda").'
        ),
        examples=[
            "ve dvě",
            "tak ve tři",
            "ve 12",
            "10 30"
            "devět 30",
            "v jedenáct 15"
            "v půl jedenácté",
            "půl deváté ráno",
            "kolem devíti ráno",
            "na pátou",
            "na osmou večer",
            "čtvrt na dvě",
            "večer v sedum",
        ],
    )
    branch_location: Optional[str] = Field(
        None,
        description="The branch location where the appointment with the customer is scheduled.",
        examples=["Praha", "Brno", "Ostrava"]
    )
    users_obstacle: Optional[str] = Field(
        None,
        description="Obstacle mentioned by the user.",
        examples=["nemám čas", "hlídám děti"],
    )

    # extra fields from form
    car_mileage_range: Optional[str] = None
    gender: Optional[str] = None
    initial_message_outbound: Optional[str] = None
    initial_message_NR_inbound: Optional[str] = None
    gpt_make_fon: Optional[str] = None
    gpt_model_fon: Optional[str] = None

    normalize_ignore: List[str] = Field(["current_date", "current_time", "our_price_offer"], hidden=True)

    def get_tomorrow(self):
        return (self.current_date + datetime.timedelta(days=1)).isoformat()

    @validator("inspection_appointment_date")
    def validate_inspection_appointment_date(cls, v: datetime.date, values: dict, **kwargs) -> Optional[datetime.date]:
        if v is not None and v < values["current_date"]:
            raise ValueError("inspection_appointment_date must not be in the past")
        return v

    @validator("inspection_appointment_time")
    def validate_inspection_appointment_time(cls, v: datetime.time, values: dict, **kwargs) -> Optional[datetime.time]:
        if v is None:
            return
        if "inspection_appointment_date" in values:
            appointment_date = values["inspection_appointment_date"]
            current_date = values["current_date"]
            current_time = values["current_time"]
            if datetime.datetime.combine(appointment_date, v) < datetime.datetime.combine(current_date, current_time):
                raise ValueError("inspection_appointment_time must not be in the past")
        if v < cls.BRANCH_OPENS or v >= cls.BRANCH_CLOSES:
            raise ValueError("inspection_appointment_time must be between 9:00 and 21:00")
        return v

    @validator("car_fuel")
    def validate_car_fuel(cls, v: str) -> Optional[str]:
        enum = cls.schema()["properties"]["car_fuel"]["enum"] + [None]
        if v not in enum:
            raise ValueError("car_fuel must be one of the allowed values: {}".format(enum))
        return v

    @classmethod
    def from_form(cls, form: dict):
        cleaned_form = {}

        # Mapping relevant JSON fields to OutboundBuyState class fields
        cleaned_form["car_model_name"] = f"{form['make']} {form['model']}"
        cleaned_form["branch_location"] = form["branch"]
        cleaned_form["user_first_name"] = form["customer_name"]
        cleaned_form["user_last_name"] = form["customer_surname"]
        cleaned_form["user_salutation"] = form["salutation"]
        cleaned_form["gender"] = form["gender"]

        cleaned_form["car_mileage_range"] = form["car_mileage"]
        cleaned_form["car_fuel"] = form["car_fuel"]
        cleaned_form["initial_message_outbound"] = form["initial_message_outbound"]
        cleaned_form["initial_message_NR_inbound"] = form["initial_message_NR_inbound"]
        cleaned_form["gpt_make_fon"] = form["gpt_make_fon"]
        cleaned_form["gpt_model_fon"] = form["gpt_model_fon"]

        try:
            cleaned_form["car_manufacture_year"] = int(form["manufacture_year"])
        except ValueError:
            print(f"Invalid manufacture_year value: {form['manufacture_year']}")

        if form["customer_price"]:
            try:
                cleaned_form["users_car_price"] = int(form["customer_price"])
            except ValueError:
                print(f"Invalid customer_price value: {form['customer_price']}")

        return cls(**cleaned_form)


class OutboundSellState(BaseDialogState):
    car_model_name = Field("Škoda Octavia", examples=["Renault Megane", "Škoda Octavia"])

    user_first_name = Field("Petr", examples=["Michal", "František"])
    user_last_name = Field("Karta", examples=["Kovář", "Novák"])
    user_phone = Field("777 123 456", examples=["777 123 456", "777 987 654"])

    user_location = Field("Havířov", examples=["Praha", "Brno", "Ostrava"])
    branch_location = Field("Ostrava", examples=["Praha", "Brno", "Ostrava"])

    user_wants_car_financing: Optional[bool] = Field(None, type=Optional[bool], enum=[True, False])
    financing_rejected_count = Field(0, enum=[0, 1, 2], hidden=True)

    user_meeting_date: Optional[str] = Field(None, type=Optional[str], examples=DATE_EXAMPLES)
    user_meeting_time: Optional[str] = Field(None, type=Optional[str], examples=TIME_EXAMPLES)

    script_location = Field("financing", examples=["router", "introduction", "financing"])
    user_wants_something_else: bool = Field(False, enum=[True, False])
    intent: Optional[str] = Field(None, type=Optional[str], hidden=True,
                                  examples=["find_out_more", "financing_rejected", "answered_question"])

    def decision_callback(self, response: 'ConsoleChatResponse'):
        if response.dialog_state_update is None:
            return ConsoleChatDecision(retry=True, say_now_raw_text=None, response=response)

        meeting_init_raw_text = 'Tak, a v kolik se dnes uvidíme? Můžete odpoledne nebo až večer? INTENT: "user_schedule_meeting" DIALOG_STATE_UPDATE: {}'
        if self.script_location == 'financing':
            if response.dialog_state_update.get('intent') == 'user_accepts':
                self.user_wants_car_financing = True
                self.script_location = "meeting_schedule"
                return ConsoleChatDecision(say_now_raw_text=meeting_init_raw_text, retry=False, response=response)

            elif response.dialog_state_update.get('intent') == 'user_rejects_or_unsure':
                # we will retry
                self.user_wants_car_financing = False
                self.script_location = "financing"
                self.financing_rejected_count += 1
                if self.financing_rejected_count == 3:
                    self.user_wants_car_financing = False
                    self.script_location = "meeting_schedule"
                    # FIXME: this should not be in the template in some parsoble way.
                    return ConsoleChatDecision(say_now_raw_text=meeting_init_raw_text, retry=False, response=response)

                else:
                    return ConsoleChatDecision(
                        # say_now_raw_text='Zní Vám splátky dobře? INTENT" "user_rejects_or_unsure" DIALOG_STATE_UPDATE: {}'
                        say_now_raw_text=None
                        , retry=False, response=response)

            elif response.dialog_state_update.get('intent') == 'user_asks_question':
                return ConsoleChatDecision(
                    say_now_raw_text=f'Ale teď zpět k financování. INTENT: "user_asks_question" DIALOG_STATE_UPDATE: {json.dumps(response.dialog_state_update)}',
                    retry=False, response=response)

            elif len(response.dialog_state_update) == 0:
                return ConsoleChatDecision(
                    say_now_raw_text='Teď si nejsem jistá co přesně chcete říct. Jak to vidíte? INTENT: "continue" DIALOG_STATE_UPDATE: {}',
                    retry=True, response=response)

            else:
                self.script_location = "router"
                return ConsoleChatDecision(say_now_raw_text='To jste mě překvapil. INTENT: "entered_router" {}',
                                           retry=False, response=response)

        elif self.script_location == 'router':
            if response.dialog_state_update.get('decision') == 'user_wants_car':
                self.script_location = "introduction"

            elif response.dialog_state_update.get('decision') == 'user_wants_financing':
                self.script_location = "financing"

            else:
                self.script_location = "router"

        return ConsoleChatDecision(say_now_raw_text=None, retry=False, response=response)
