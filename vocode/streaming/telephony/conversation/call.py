from os import getenv
from pathlib import Path

from fastapi import WebSocket
from enum import Enum
import logging
from typing import Optional, TypeVar, Union
from vocode.streaming.agent.factory import AgentFactory
from vocode.streaming.models.agent import AgentConfig
from vocode.streaming.models.events import PhoneCallEndedEvent
from vocode.streaming.output_device.vonage_output_device import VonageOutputDevice
from vocode.streaming.scalevoice_config import get_scalevoice_conversation_config

from vocode.streaming.streaming_conversation import StreamingConversation
from vocode.streaming.output_device.twilio_output_device import TwilioOutputDevice
from vocode.streaming.models.synthesizer import (
    SynthesizerConfig,
)
from vocode.streaming.models.transcriber import (
    TranscriberConfig,
)
from vocode.streaming.synthesizer.factory import SynthesizerFactory
from vocode.streaming.telephony.config_manager.base_config_manager import (
    BaseConfigManager,
)
from vocode.streaming.telephony.constants import DEFAULT_SAMPLING_RATE
from vocode.streaming.streaming_conversation import StreamingConversation
from vocode.streaming.transcriber.factory import TranscriberFactory
from vocode.streaming.utils.events_manager import EventsManager
from vocode.streaming.utils.conversation_logger_adapter import wrap_logger
from vocode.streaming.utils import create_conversation_id

TelephonyOutputDeviceType = TypeVar(
    "TelephonyOutputDeviceType", bound=Union[TwilioOutputDevice, VonageOutputDevice]
)


class Call(StreamingConversation[TelephonyOutputDeviceType]):
    def __init__(
        self,
        from_phone: str,
        to_phone: str,
        base_url: str,
        config_manager: BaseConfigManager,
        output_device: TelephonyOutputDeviceType,
        agent_config: AgentConfig,
        transcriber_config: TranscriberConfig,
        synthesizer_config: SynthesizerConfig,
        conversation_id: Optional[str] = None,
        transcriber_factory: TranscriberFactory = TranscriberFactory(),
        agent_factory: AgentFactory = AgentFactory(),
        synthesizer_factory: SynthesizerFactory = SynthesizerFactory(),
        events_manager: Optional[EventsManager] = None,
        logger: Optional[logging.Logger] = None,
    ):
        conversation_id = conversation_id or create_conversation_id()
        logger = wrap_logger(
            logger or logging.getLogger(__name__),
            conversation_id=conversation_id,
        )

        self.from_phone = from_phone
        self.to_phone = to_phone
        self.base_url = base_url
        self.config_manager = config_manager
        super().__init__(
            output_device,
            transcriber_factory.create_transcriber(transcriber_config, logger=logger),
            agent_factory.create_agent(agent_config, logger=logger),
            synthesizer_factory.create_synthesizer(synthesizer_config, logger=logger),
            conversation_id=conversation_id,
            per_chunk_allowance_seconds=0.01,
            events_manager=events_manager,
            logger=logger,
            **get_scalevoice_conversation_config(logger)
        )

    def attach_ws(self, ws: WebSocket):
        self.logger.debug("Trying to attach WS to outbound call")
        self.output_device.ws = ws
        self.logger.debug("Attached WS to outbound call")

    async def attach_ws_and_start(self, ws: WebSocket):
        raise NotImplementedError

    def save_conversation(self, logs_path: Path) -> None:
        # if path doesn't exist, create it
        logs_path.mkdir(parents=True, exist_ok=True)
        # save transcript to file
        if len(self.transcript.event_logs) > 0:
            timestamp = self.transcript.event_logs[0].timestamp
            with open(logs_path / f"{timestamp}_conversation.txt", "w") as f:
                f.write(self.transcript.to_string(include_timestamps=True))
            # if self.summary is not None:
            #     with open(logs_path / f"{timestamp}_summary.txt", "w") as f:
            #         f.write(self.summary)
            return
        self.logger.warning("Transcript is empty, not saving to file")
    async def tear_down(self):
        self.events_manager.publish_event(PhoneCallEndedEvent(conversation_id=self.id))
        await self.terminate()

        logs_path = getenv("LOGS_PATH")
        if logs_path is not None:
            self.save_conversation(Path(logs_path))