import os
import aiohttp

from aiohttp import BasicAuth
from typing import Type
from pydantic import BaseModel, Field

from vocode.streaming.action.phone_call_action import TwilioPhoneCallAction
from vocode.streaming.models.actions import (
    ActionConfig,
    ActionInput,
    ActionOutput,
    ActionType,
)


class TransferCallActionConfig(ActionConfig, type=ActionType.TRANSFER_CALL):
    to_phone: str
    from_phone: str


class TransferCallParameters(BaseModel):
    pass


class TransferCallResponse(BaseModel):
    status: str = Field("success", description="status of the transfer")


class TransferCall(
    TwilioPhoneCallAction[
        TransferCallActionConfig, TransferCallParameters, TransferCallResponse
    ]
):
    description: str = "Never use it before confirming thast customer really wants to transfer call! Transfers the call."
    parameters_type: Type[TransferCallParameters] = TransferCallParameters
    response_type: Type[TransferCallResponse] = TransferCallResponse

    async def transfer_call(self, twilio_call_sid, to_phone, caller_id):
        twilio_account_sid = os.environ["TWILIO_ACCOUNT_SID"]
        twilio_auth_token = os.environ["TWILIO_AUTH_TOKEN"]

        url = "https://api.twilio.com/2010-04-01/Accounts/{twilio_account_sid}/Calls/{twilio_auth_token}.json".format(
            twilio_account_sid=twilio_account_sid, twilio_auth_token=twilio_call_sid
        )

        twiml_data = "<Response><Dial callerId='{caller_id}'><Number>{to_phone}</Number></Dial></Response>".format(
            to_phone=to_phone,
            caller_id=caller_id,
        )

        payload = {"Twiml": twiml_data}

        auth = BasicAuth(twilio_account_sid, twilio_auth_token)

        async with aiohttp.ClientSession(auth=auth) as session:
            async with session.post(url, data=payload) as response:
                if response.status != 200:
                    print(await response.text())
                    raise Exception("failed to update call")
                else:
                    return await response.json()

    async def run(
            self, action_input: ActionInput[TransferCallParameters]
    ) -> ActionOutput[TransferCallResponse]:
        twilio_call_sid = self.get_twilio_sid(action_input)

        await self.transfer_call(twilio_call_sid=twilio_call_sid, to_phone=self.action_config.to_phone,
                                 caller_id=self.action_config.from_phone)

        return ActionOutput(
            action_type=action_input.action_config.type,
            response=TransferCallResponse(status="success"),
        )
