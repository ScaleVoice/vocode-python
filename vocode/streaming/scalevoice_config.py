import os
from logging import Logger
from typing import Optional

from azure.ai.textanalytics.aio import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential

from vocode.streaming.agent.gpt_belief_state_extractor import ChatGPTBeliefExtractionAgent
from vocode.streaming.agent.gpt_summary_agent import ChatGPTSummaryAgent
from vocode.streaming.ignored_while_talking_fillers_fork import OpenAIEmbeddingOverTalkingFillerDetector
from vocode.streaming.models.agent import ChatGPTAgentConfig, AzureOpenAIConfig
from vocode.streaming.response_classifier import OpenaiEmbeddingsResponseClassifier

SUMMARIZER_PROMPT_PREAMBLE = """You are creating summaries for telephone calls transcripts between AI voice bot and customer.
Bot`s name is Romana. Customer`s responses are after ``Human:`` and bot`s responses are after ``Bot:``.

You will generate increasingly concise entity-dense summaries of the given call transcript.
If previous summary exists it will be added below call transcript. Use it as a reference you need to keep all the entities
and just update the summary with new information.

Guidelines:
- The summary should (4-5 sentences, ~80 words), be a concise and accurate summary of the call transcript.
- Make space with fusion, compression, and removal of uninformative phrases like "the article discusses".
- The summaries should become highly dense and concise, yet self-contained, e.g., easily understood without the article.
- Never drop entities from the previous summary.
- The most important entities are names, locations, and dates and cars discussed in the call and very important what
agent and customer discussed already - e.g. financial terms, location of car etc. It is first priority so
GPT-3 can use it later in the conversation and won't repeat itself or forget important information.

Remember: Try to keep the summary as short as possible, but not shorter. Summary is later used by GPT-3 as a reference to
what it have discussed and agreed with the customer. If the summary is too short or missing some important information,
the GPT-3 will not be able to continue correctly the conversation.

NEVER ADD CAR DETAILS AND OPTIONS INTO THE SUMMARY
KEEP THE SUMMARY SHORT

Fill in the summary after the line ``SUMMARY:``. If there is no summary yet, create one.
SUMMARY:

"""

BELIEF_STATE_PROMPT_PREAMBLE = """You are creating belief state for telephone calls transcripts between AI voice bot and customer.
Bot`s name is Romana. Customer`s responses are after ``Human:`` and bot`s responses are after ``Bot:``.

You will always respond with JSON that contains the following fields:
- ``intent``: the intent of the user's message. Intents are user_intrested, user_not_intrested
- ``car_name``: the name of the car that the user is interested in.
- ``car_model``: the model of the car that the user is interested in.
- ``car_year``: the year of the car that the user is interested in.
- ``car_color``: the color of the car that the user is interested in.

You don't need to fill in all the fields. If conversation yields no information about any of the fields, respond with empty JSON.

"""


def get_scalevoice_conversation_config(logger: Logger,
                                       summarizer_prompt_preamble: Optional[str] = None):
    """
    This is a quick hack to pass configuration to the config below.
    The disadvantage is that we have to be able to quickly change this code on changes beyond the environmental variables.
    The reason is to have the simplest and minimized changes to the Vocode's code for now and maximum flexibility

    Variables will change during import time because of loading config files, so they are extracted here at runtime.
    """
    if summarizer_prompt_preamble is None:
        summarizer_prompt_preamble = SUMMARIZER_PROMPT_PREAMBLE

    AZURE_OPENAI_API_KEY_SUMMARY = os.environ['AZURE_OPENAI_API_KEY_SUMMARY']
    AZURE_OPENAI_API_BASE_SUMMARY = os.environ['AZURE_OPENAI_API_BASE_SUMMARY']
    PROJECT_ROOT = os.environ['PROJECT_ROOT']
    AZURE_TEXT_ANALYTICS_KEY = os.environ['AZURE_TEXT_ANALYTICS_KEY']
    AZURE_TEXT_ANALYTICS_ENDPOINT = os.environ['AZURE_TEXT_ANALYTICS_ENDPOINT']

    return dict(
        summarizer=ChatGPTSummaryAgent(logger=logger,
                                       # TODO: refactor it. RN there is a problem with standard openai auth because we have
                                       # to use uk endpoint but our 3.5 runs in western europe.
                                       key=AZURE_OPENAI_API_KEY_SUMMARY,
                                       base=AZURE_OPENAI_API_BASE_SUMMARY,
                                       agent_config=ChatGPTAgentConfig(

                                           prompt_preamble=summarizer_prompt_preamble,
                                           azure_params=AzureOpenAIConfig(
                                               api_type="azure",
                                               api_version="2023-03-15-preview",
                                               engine="gpt4"  # always use gpt4
                                           ),
                                       )) if AZURE_OPENAI_API_BASE_SUMMARY is not None else None,
        over_talking_filler_detector=OpenAIEmbeddingOverTalkingFillerDetector(logger=logger),
        openai_embeddings_response_classifier=OpenaiEmbeddingsResponseClassifier(),
        text_analysis_client=TextAnalyticsClient(endpoint=AZURE_TEXT_ANALYTICS_ENDPOINT,
                                                 credential=AzureKeyCredential(AZURE_TEXT_ANALYTICS_KEY)),

        belief_state_extractor=ChatGPTBeliefExtractionAgent(logger=logger,
                                                            key=AZURE_OPENAI_API_KEY_SUMMARY,
                                                            base=AZURE_OPENAI_API_BASE_SUMMARY,
                                                            agent_config=ChatGPTAgentConfig(
                                                                prompt_preamble=BELIEF_STATE_PROMPT_PREAMBLE,
                                                                azure_params=AzureOpenAIConfig(
                                                                    api_type="azure",
                                                                    api_version="2023-03-15-preview",
                                                                    engine="gpt3"  # always use davinci
                                                                ),

                                                            )))
