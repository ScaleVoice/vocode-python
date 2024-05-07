import asyncio
import json
import time
from typing import Optional

import openai

from vocode.streaming.transcriber.base_transcriber import Transcription
from vocode.streaming.utils.default_prompts.interrupt_prompt import INTERRUPTION_PROMPT
from vocode.streaming.utils.worker import AsyncQueueWorker


class InterruptWorker(AsyncQueueWorker):
    """Processes transcriptions to determine if an interrupt is needed."""

    def __init__(self, input_queue: asyncio.Queue[Transcription], conversation, prompt: Optional[str] = None):
        super().__init__(input_queue)
        self.conversation = conversation
        self.prompt = prompt if prompt else INTERRUPTION_PROMPT

    async def classify_transcription(self, transcription: Transcription) -> bool:
        last_bot_message = self.conversation.transcript.get_last_bot_text()
        transcript_message = transcription.message
        model = "gpt-3.5-turbo"
        if self.conversation.agent.agent_config.type == "agent_llama3":
            model = "accounts/fireworks/models/llama-v3-70b-instruct"
        chat_parameters = {
            "model": model,
            "messages": [
                {"role": "system", "content": INTERRUPTION_PROMPT},
                {"role": "user", "content": transcript_message},
                {"role": "assistant", "content": last_bot_message},
            ]
        }
        try:
            response = await openai.ChatCompletion.acreate(**chat_parameters)
            decision = json.loads(response['choices'][0]['message']['content'].strip().lower())
            self.conversation.logger.info(f"Decision: {decision}")
            return decision['interrupt'] == 'true'

        except Exception as e:
            # Log the exception or handle it as per your error handling policy
            self.conversation.logger.error(f"Error in GPT-3.5 API call: {str(e)}")
            return False

    async def simple_interrupt(self, transcription: Transcription) -> bool:
        return not self.conversation.is_human_speaking and self.conversation.is_interrupt(transcription)

    async def process(self, transcription: Transcription):
        current_turn = self.conversation.turn_index
        is_propagate = await self.handle_interrupt(transcription, current_turn)
        if is_propagate:
            await self.conversation.transcriptions_worker.propagate_transcription(transcription)

    async def handle_interrupt(self, transcription: Transcription, current_turn: int) -> bool:
        if self.conversation.use_interrupt_agent:
            self.conversation.logger.info(
                f"Testing if bot should be interrupted: {transcription.message}"
            )
            is_interrupt = await self.classify_transcription(transcription)
            if self.conversation.turn_index != current_turn:
                # The conversation has moved on since this transcription was processed.
                self.conversation.logger.info(
                    f"Conversation has moved on since transcription was processed. Current turn: {current_turn}, index: {self.conversation.turn_index} ")
                return False
            if is_interrupt and self.conversation.is_bot_speaking:
                if self.conversation.is_bot_speaking:
                    self.conversation.broadcast_interrupt()
                    transcription.is_interrupt = True
                    transcription.message = "<SYSTEM: YOU WERE INTERRUPTED CONFIRM YOU UNDERSTOOD CUSTOMER. DON'T REPEAT YOURSELF. IF YOU NEED TO CLARIFY REPHRASE THE QUESTION.> " + transcription.message
                    self.conversation.current_transcription_is_interrupt = True

                return True
            return is_interrupt and not self.conversation.is_bot_speaking
        else:
            return await self.simple_interrupt(transcription)
