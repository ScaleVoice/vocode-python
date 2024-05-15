import asyncio
import logging

from typing import Any, Dict, List, Union
from typing import AsyncGenerator, Optional, Tuple

from openai import AsyncAzureOpenAI, AsyncOpenAI, OpenAI, AzureOpenAI

from vocode import getenv
from vocode.streaming.action.factory import ActionFactory
from vocode.streaming.agent.base_agent import RespondAgent
from vocode.streaming.agent.utils import (
    format_openai_chat_messages_from_transcript,
    collate_response_async,
    openai_get_tokens,
    vector_db_result_to_openai_chat_message,
)
from vocode.streaming.models.actions import FunctionCall
from vocode.streaming.models.agent import  ChatGPTAgentConfigOLD
from vocode.streaming.models.transcript import Transcript
from vocode.streaming.vector_db.factory import VectorDBFactory


def messages_from_transcript(transcript: Transcript, system_prompt: str):
    last_summary = transcript.last_summary
    if last_summary is not None:
        system_prompt += '\n THIS IS SUMMARY OF CONVERSATION SO FAR' + last_summary.text

#FIXME: rename ChatGPTAgentOld to this ChatGPTAgent.
# class ChatGPTAgent(RespondAgent[ChatGPTAgentConfig]):


class ChatGPTAgentOld(RespondAgent[ChatGPTAgentConfigOLD]):
    def __init__(
            self,
            agent_config: ChatGPTAgentConfigOLD,
            action_factory: ActionFactory = ActionFactory(),
            logger: Optional[logging.Logger] = None,
            openai_api_key: Optional[str] = None,
            vector_db_factory=VectorDBFactory(),
            response_predictor: Optional[Any] = None,
    ):
        super().__init__(
            agent_config=agent_config, action_factory=action_factory, logger=logger
        )
        if agent_config.azure_params:
            openai.api_type = agent_config.azure_params.api_type
            openai.api_base = getenv("AZURE_OPENAI_API_BASE")
            openai.api_version = agent_config.azure_params.api_version
            openai.api_key = getenv("AZURE_OPENAI_API_KEY")
        else:
            openai.api_type = "open_ai"
            openai.api_base = "https://api.openai.com/v1"
            openai.api_version = None
            openai.api_key = openai_api_key or getenv("OPENAI_API_KEY")
        if not openai.api_key:
            raise ValueError("OPENAI_API_KEY must be set in environment or passed in")
        self.first_response = None
        self.is_first_response = True

        self.response_predictor = response_predictor
        self.seed = agent_config.seed
        if self.agent_config.vector_db_config:
            self.vector_db = vector_db_factory.create_vector_db(
                self.agent_config.vector_db_config
            )

    def get_functions(self):
        assert self.agent_config.actions
        if not self.action_factory:
            return None
        return [
            self.action_factory.create_action(action_config).get_openai_function()
            for action_config in self.agent_config.actions
        ]

    def get_chat_parameters(
            self, messages: Optional[List] = None, use_functions: bool = True, ignore_assert: bool = False
    ):
        if not ignore_assert:
            assert self.transcript is not None
        messages = messages or format_openai_chat_messages_from_transcript(
            self.transcript, self.agent_config.prompt_preamble
        )

        parameters: Dict[str, Any] = {
            "messages": messages,
            "max_tokens": self.agent_config.max_tokens,
            "temperature": self.agent_config.temperature,
        }

        if self.agent_config.azure_params is not None:
            parameters["engine"] = self.agent_config.azure_params.engine
        else:
            parameters["model"] = self.agent_config.model_name

        if use_functions and self.functions:
            parameters["functions"] = self.functions

        return parameters

    async def create_first_response(self, first_message_prompt: Optional[str] = None):
        system_prompt = first_message_prompt if first_message_prompt else self.agent_config.prompt_preamble
        messages = [{"role": "system", "content": system_prompt}]
        parameters = self.get_chat_parameters(messages)
        parameters["stream"] = True
        self.logger.info('Attempting to stream response for first message.')
        async for response, is_successful in self.__attempt_stream_with_retries(
                parameters, self.agent_config.timeout_seconds,
                max_retries=self.agent_config.max_retries):
            yield response, is_successful

    async def create_first_response_full(self, first_message_prompt: Optional[str] = None):
        system_prompt = first_message_prompt if first_message_prompt else self.agent_config.prompt_preamble
        messages = [{"role": "system", "content": system_prompt}]
        parameters = self.get_chat_parameters(messages, ignore_assert=True)
        parameters["stream"] = False
        self.logger.info('Attempting create response for the first message.')
        chat_completion = await openai.ChatCompletion.acreate(**parameters)
        return chat_completion.choices[0].message.content

    def attach_transcript(self, transcript: Transcript):
        self.transcript = transcript

    async def respond(
            self,
            human_input,
            conversation_id: str,
            is_interrupt: bool = False,
    ) -> Tuple[str, bool]:
        assert self.transcript is not None
        if is_interrupt and self.agent_config.cut_off_response:
            cut_off_response = self.get_cut_off_response()
            return cut_off_response, False
        self.logger.debug("LLM responding to human input")
        if self.is_first_response and self.first_response:
            self.logger.debug("First response is cached")
            self.is_first_response = False
            text = self.first_response
        else:
            chat_parameters = self.get_chat_parameters()
            chat_completion = await openai.ChatCompletion.acreate(**chat_parameters)
            text = chat_completion.choices[0].message.content
        self.logger.debug(f"LLM response: {text}")
        return text, False

    async def attempt_stream_response(self, chat_parameters, response_timeout):
        try:
            # Create the chat stream
            self.logger.info('attempt_stream_response')
            stream = await asyncio.wait_for(
                openai.ChatCompletion.acreate(**chat_parameters),
                timeout=self.agent_config.timeout_generator_seconds
            )
            self.logger.info('have attempt_stream_response')
            # Wait for the first message
            first_response = await asyncio.wait_for(
                collate_response_async(
                    openai_get_tokens(stream), get_functions=True
                ).__anext__(),
                timeout=response_timeout
            )
            self.logger.info('got first message')
            return stream, first_response
        except asyncio.TimeoutError:
            self.logger.info('got error timeout')
            return None, None

    async def __attempt_stream_with_retries(self, chat_parameters, initial_timeout, max_retries):
        timeout_increment = self.agent_config.retry_time_increment_seconds
        current_timeout = initial_timeout

        for attempt in range(max_retries + 1):
            stream, first_response = await self.attempt_stream_response(chat_parameters, current_timeout)

            if first_response is not None:
                self.logger.info(f'Stream attempt {attempt + 1} was successful.')
                yield first_response, True

                async for message in collate_response_async(
                        openai_get_tokens(stream), get_functions=True):
                    yield message, True
                return  # Exit the function after successful attempt

            else:
                self.logger.info(f'Stream attempt {attempt + 1} failed, retrying.')
                # Send filler words based on the attempt number minus one to ignore the first fail.
                if self.response_predictor is not None and attempt > 0:
                    # Ignore the first failed attempt.
                    yield self.response_predictor.get_retry_text(attempt - 1), False

                # Update timeout for the next attempt
                current_timeout += timeout_increment

        # If all retries fail
        self.logger.error('All stream attempts failed, giving up.')
        yield self.response_predictor.get_retry_failed(), False
        raise RuntimeError("Failed to get a timely response from OpenAI after retries.")

    async def generate_response(
            self,
            human_input: str,
            conversation_id: str,
            is_interrupt: bool = False,
    ) -> AsyncGenerator[Tuple[Union[str, FunctionCall], bool], None]:
        if is_interrupt and self.agent_config.cut_off_response:
            cut_off_response = self.get_cut_off_response()
            yield cut_off_response, False
            return
        assert self.transcript is not None
        if self.agent_config.vector_db_config:
            try:
                docs_with_scores = await self.vector_db.similarity_search_with_score(
                    self.transcript.get_last_user_message()[1]
                )
                docs_with_scores_str = "\n\n".join(
                    [
                        "Document: "
                        + doc[0].metadata["source"]
                        + f" (Confidence: {doc[1]})\n"
                        + doc[0].lc_kwargs["page_content"].replace(r"\n", "\n")
                        for doc in docs_with_scores
                    ]
                )
                vector_db_result = f"Found {len(docs_with_scores)} similar documents:\n{docs_with_scores_str}"
                messages = format_openai_chat_messages_from_transcript(
                    self.transcript, self.agent_config.prompt_preamble
                )
                messages.insert(
                    -1, vector_db_result_to_openai_chat_message(vector_db_result)
                )
                chat_parameters = self.get_chat_parameters(messages)
            except Exception as e:
                self.logger.error(f"Error while hitting vector db: {e}", exc_info=True)
                chat_parameters = self.get_chat_parameters()
        else:
            chat_parameters = self.get_chat_parameters()
        chat_parameters["stream"] = True
        chat_parameters["seed"] = self.seed

        self.logger.info('Attempting to stream response.')
        async for response, is_successful in self.__attempt_stream_with_retries(
                chat_parameters, self.agent_config.timeout_seconds,
                max_retries=self.agent_config.max_retries):
            yield response, is_successful