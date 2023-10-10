import logging
from typing import Optional

import openai

from vocode.streaming.models.agent import ChatGPTAgentConfig


class ChatGPTBeliefExtractionAgent:
    def __init__(
            self,
            key: str,
            base: str,
            agent_config: ChatGPTAgentConfig,
            logger: Optional[logging.Logger] = None
    ):
        self.agent_config = agent_config
        self.open_ai_dict = {"api_type": agent_config.azure_params.api_type, "api_base": base,
                             "api_version": agent_config.azure_params.api_version, "api_key": key}
        self.logger = logger

    # create async function to call openai and use params from agent_config
    async def get_belief_state(self, transcript: str):

        messages = [
            {"role": "system", "content": self.agent_config.prompt_preamble},
            {"role": "user", "content": transcript}
        ]
        m = await openai.ChatCompletion.acreate(
            engine=self.agent_config.azure_params.engine,
            messages=messages,
            temperature=self.agent_config.temperature,
            max_tokens=self.agent_config.max_tokens,
            **self.open_ai_dict
        )
        return m
