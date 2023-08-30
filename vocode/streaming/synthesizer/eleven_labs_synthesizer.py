import asyncio
import logging
import time
from typing import Any, AsyncGenerator, Optional, Tuple, Union, Dict
import wave
import aiohttp
from opentelemetry.trace import Span
from elevenlabs import generate

from vocode import getenv
from vocode.streaming.synthesizer.base_synthesizer import (
    BaseSynthesizer,
    SynthesisResult,
    encode_as_wav,
    tracer,
)
from vocode.streaming.models.synthesizer import (
    ElevenLabsSynthesizerConfig,
    SynthesizerType,
)
from vocode.streaming.agent.bot_sentiment_analyser import BotSentiment
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.utils.mp3_helper import decode_mp3
from vocode.streaming.synthesizer.miniaudio_worker import MiniaudioWorker


ADAM_VOICE_ID = "pNInz6obpgDQGcFmaJgB"
ELEVEN_LABS_BASE_URL = "https://api.elevenlabs.io/v1/"


class ElevenLabsSynthesizer(BaseSynthesizer[ElevenLabsSynthesizerConfig]):
    def __init__(
        self,
        synthesizer_config: ElevenLabsSynthesizerConfig,
        logger: Optional[logging.Logger] = None,
        aiohttp_session: Optional[aiohttp.ClientSession] = None,
    ):
        super().__init__(synthesizer_config, aiohttp_session)

        import elevenlabs

        self.elevenlabs = elevenlabs
        self.logger = logger
        self.api_key = synthesizer_config.api_key or getenv("ELEVEN_LABS_API_KEY")
        self.voice_id = synthesizer_config.voice_id or ADAM_VOICE_ID
        self.stability = synthesizer_config.stability
        self.similarity_boost = synthesizer_config.similarity_boost
        self.model_id = synthesizer_config.model_id
        self.optimize_streaming_latency = synthesizer_config.optimize_streaming_latency
        self.words_per_minute = 150
        self.experimental_streaming = synthesizer_config.experimental_streaming
        self.miniaudio_worker = None

    async def experimental_streaming_output_generator(
        self,
        response: aiohttp.ClientResponse,
        chunk_size: int,
        create_speech_span: Optional[Span],
    ) -> AsyncGenerator[SynthesisResult.ChunkResult, None]:
        start = time.time()
        miniaudio_worker_input_queue: asyncio.Queue[
            Union[bytes, None]
        ] = asyncio.Queue()
        miniaudio_worker_output_queue: asyncio.Queue[
            Tuple[bytes, bool]
        ] = asyncio.Queue()
        miniaudio_worker = MiniaudioWorker(
            self.synthesizer_config,
            chunk_size,
            miniaudio_worker_input_queue,
            miniaudio_worker_output_queue,
        )
        self.miniaudio_worker = miniaudio_worker
        miniaudio_worker.start()
        stream_reader = response.content

        # Create a task to send the mp3 chunks to the MiniaudioWorker's input queue in a separate loop
        async def send_chunks():
            async for chunk in stream_reader.iter_any():
                miniaudio_worker.consume_nonblocking(chunk)
            miniaudio_worker.consume_nonblocking(None)  # sentinel

        chunks_time = 0
        try:
            asyncio.create_task(send_chunks())

            # Await the output queue of the MiniaudioWorker and yield the wav chunks in another loop
            while True:
                # Get the wav chunk and the flag from the output queue of the MiniaudioWorker
                start = time.time()
                wav_chunk, is_last = await miniaudio_worker.output_queue.get()
                end = time.time()
                chunks_time += end - start
                self.logger.debug("11Labs: Getting wav chunk took %s, at %s", end - start, time.time())
                if self.synthesizer_config.should_encode_as_wav:
                    wav_chunk = encode_as_wav(wav_chunk, self.synthesizer_config)

                yield SynthesisResult.ChunkResult(wav_chunk, is_last)
                # If this is the last chunk, break the loop
                if is_last and create_speech_span is not None:
                    create_speech_span.end()
                    break
        except asyncio.CancelledError:
            pass
        finally:
            miniaudio_worker.terminate()
            self.miniaudio_worker = None

    async def create_speech(
        self,
        message: BaseMessage,
        chunk_size: int,
        bot_sentiment: Optional[BotSentiment] = None,
    ) -> SynthesisResult:
        start = time.time()
        self.logger.debug("11Labs: Creating speech: %s; Message %s", start, message.text)
        voice = self.elevenlabs.Voice(voice_id=self.voice_id)
        if self.stability is not None and self.similarity_boost is not None:
            voice.settings = self.elevenlabs.VoiceSettings(
                stability=self.stability, similarity_boost=self.similarity_boost
            )
        url = ELEVEN_LABS_BASE_URL + f"text-to-speech/{self.voice_id}"

        if self.experimental_streaming:
            url += "/stream"

        if self.optimize_streaming_latency:
            url += f"?optimize_streaming_latency={self.optimize_streaming_latency}"
        headers = {"xi-api-key": self.api_key}
        body = {
            "text": message.text,
            "voice_settings": voice.settings.dict() if voice.settings else None,
        }
        if self.model_id:
            body["model_id"] = self.model_id

        create_speech_span = tracer.start_span(
            f"synthesizer.{SynthesizerType.ELEVEN_LABS.value.split('_', 1)[-1]}.create_total",
        )
        session = self.aiohttp_session
        response = await session.request(
            "POST",
            url,
            json=body,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        )
        self.logger.debug("11Labs: response %s", time.time())
        if not response.ok:
            raise Exception(f"ElevenLabs API returned {response.status} status code")
        if self.experimental_streaming:
            self.logger.debug("Using experimental streaming %s", time.time())

            return SynthesisResult(
                self.experimental_streaming_output_generator(
                    response, chunk_size, create_speech_span
                ),  # should be wav
                lambda seconds: self.get_message_cutoff_from_voice_speed(
                    message, seconds, self.words_per_minute
                ),
            )
        else:
            audio_data = await response.read()
            create_speech_span.end()
            convert_span = tracer.start_span(
                f"synthesizer.{SynthesizerType.ELEVEN_LABS.value.split('_', 1)[-1]}.convert",
            )
            output_bytes_io = decode_mp3(audio_data)

            result = self.create_synthesis_result_from_wav(
                file=output_bytes_io,
                message=message,
                chunk_size=chunk_size,
            )
            convert_span.end()
            return result


class SocketElevenLabsSynthesizer(BaseSynthesizer[ElevenLabsSynthesizerConfig]):
    def __init__(
            self,
            synthesizer_config: ElevenLabsSynthesizerConfig,
            logger: Optional[logging.Logger] = None,
            aiohttp_session: Optional[aiohttp.ClientSession] = None,
    ):
        super().__init__(synthesizer_config, aiohttp_session)

        import elevenlabs

        self.elevenlabs = elevenlabs
        self.logger = logger
        self.api_key = synthesizer_config.api_key or getenv("ELEVEN_LABS_API_KEY")
        self.voice_id = synthesizer_config.voice_id or ADAM_VOICE_ID
        self.stability = synthesizer_config.stability
        self.similarity_boost = synthesizer_config.similarity_boost
        self.model_id = synthesizer_config.model_id
        self.optimize_streaming_latency = synthesizer_config.optimize_streaming_latency
        self.words_per_minute = 150
        self.experimental_streaming = synthesizer_config.experimental_streaming
        self.miniaudio_worker = None

    async def streaming_generator(
            self,
            response: aiohttp.ClientResponse,
            chunk_size: int,
            create_speech_span: Optional[Span],
    ) -> AsyncGenerator[SynthesisResult.ChunkResult, None]:
        miniaudio_worker_input_queue: asyncio.Queue[
            Union[bytes, None]
        ] = asyncio.Queue()
        miniaudio_worker_output_queue: asyncio.Queue[
            Tuple[bytes, bool]
        ] = asyncio.Queue()
        miniaudio_worker = MiniaudioWorker(
            self.synthesizer_config,
            chunk_size,
            miniaudio_worker_input_queue,
            miniaudio_worker_output_queue,
        )
        self.miniaudio_worker = miniaudio_worker
        miniaudio_worker.start()
        stream_reader = response

        # Create a task to send the mp3 chunks to the MiniaudioWorker's input queue in a separate loop
        async def send_chunks():
            for chunk in stream_reader:
                miniaudio_worker.consume_nonblocking(chunk)
            miniaudio_worker.consume_nonblocking(None)  # sentinel

        chunks_time = 0
        try:
            asyncio.create_task(send_chunks())

            # Await the output queue of the MiniaudioWorker and yield the wav chunks in another loop
            while True:
                # Get the wav chunk and the flag from the output queue of the MiniaudioWorker
                start = time.time()
                wav_chunk, is_last = await miniaudio_worker.output_queue.get()
                end = time.time()
                chunks_time += end - start
                self.logger.debug("11Labs: Getting wav chunk took %s, at %s", end - start, time.time())
                if self.synthesizer_config.should_encode_as_wav:
                    wav_chunk = encode_as_wav(wav_chunk, self.synthesizer_config)

                yield SynthesisResult.ChunkResult(wav_chunk, is_last)
                # If this is the last chunk, break the loop
                if is_last and create_speech_span is not None:
                    create_speech_span.end()
                    break
        except asyncio.CancelledError:
            pass
        finally:
            miniaudio_worker.terminate()
            self.miniaudio_worker = None

    def stream_speech(self, params: Dict[str, Any] = None) -> AsyncGenerator[bytes, None]:
        text = params.pop("text")
        audio_iter = generate(
            text=iter(text),
            **params,)
        # TODO make async generator
        return audio_iter

    async def create_speech(
            self,
            message: BaseMessage,
            chunk_size: int,
            bot_sentiment: Optional[BotSentiment] = None,
    ) -> SynthesisResult:
        start = time.time()
        self.logger.debug("11Labs: Creating speech: %s; Message %s", start, message.text)
        voice = self.elevenlabs.Voice(voice_id=self.voice_id)
        if self.stability is not None and self.similarity_boost is not None:
            voice.settings = self.elevenlabs.VoiceSettings(
                stability=self.stability, similarity_boost=self.similarity_boost
            )
        url = ELEVEN_LABS_BASE_URL + f"text-to-speech/{self.voice_id}"

        if self.experimental_streaming:
            url += "/stream"

        if self.optimize_streaming_latency:
            url += f"?optimize_streaming_latency={self.optimize_streaming_latency}"
        body = {
            "text": message.text,
            "voice": voice,
            "stream_chunk_size": chunk_size,
            "stream": True,
            "api_key": self.api_key,
        }
        if self.model_id:
            body["model_id"] = self.model_id

        create_speech_span = tracer.start_span(
            f"synthesizer.{SynthesizerType.ELEVEN_LABS.value.split('_', 1)[-1]}.create_total",
        )
        self.logger.info("Using experimental")
        audio_stream = self.stream_speech(body)
        return SynthesisResult(
             self.streaming_generator(
                audio_stream, chunk_size, create_speech_span
            ),  # should be wav
            lambda seconds: self.get_message_cutoff_from_voice_speed(
                message, seconds, self.words_per_minute
            ),
        )