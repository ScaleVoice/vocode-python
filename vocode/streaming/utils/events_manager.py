from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import List, Optional

from redis.asyncio import Redis

from vocode.streaming.models.events import Event, EventType
from vocode.streaming.models.model import BaseModel


class ConversationLog(BaseModel):
    conversation_id: str
    current_timestamp: float = time.time()
    event: Event

    @property
    def redis_key(self):
        return f"conversation_log:{self.conversation_id}:{self.event.type.value}:{self.current_timestamp}"

    @property
    def data(self):
        return self.event.dict()

    @property
    def data_json(self):
        return self.event.json(ensure_ascii=False)


class RedisManager:
    def __init__(self, session_id: str, logger: Optional[logging.Logger] = None):
        self.session_id = session_id
        self.redis: Redis = Redis(
            host=os.environ['REDISHOST'],
            port=int(os.environ['REDISPORT']),
            password=os.environ['REDISPASSWORD'],
            ssl=True,
            db=os.environ['REDISDB'],
            decode_responses=True,
        )
        self.logger = logger or logging.getLogger(__name__)

    async def save_log(self, event: Event):
        timestamp = time.time() if event.dict().get("timestamp") is None else event.dict().get("timestamp")
        conversation_log = ConversationLog(conversation_id=self.session_id, event=event,
                                           current_timestamp=timestamp)
        await self.redis.set(conversation_log.redis_key, conversation_log.data_json)


class EventsManager:
    def __init__(self, subscriptions: List[EventType] = []):
        self.queue: asyncio.Queue[Event] = asyncio.Queue()
        self.subscriptions = set(subscriptions)
        self.active = False

    def publish_event(self, event: Event):
        if event.type in self.subscriptions:
            self.queue.put_nowait(event)

    async def start(self):
        self.active = True
        while self.active:
            try:
                event = await self.queue.get()
            except asyncio.QueueEmpty:
                await asyncio.sleep(1)
            await self.handle_event(event)

    async def handle_event(self, event: Event):
        pass

    async def flush(self):
        self.active = False
        while True:
            try:
                event = self.queue.get_nowait()
                await self.handle_event(event)
            except asyncio.QueueEmpty:
                break


class RedisEventsManager(EventsManager):
    def __init__(self, session_id: str, subscriptions: Optional[List[EventType]] = None):
        super().__init__(subscriptions)
        if subscriptions is None:
            self.subscriptions = {}
        self.redis_manager = RedisManager(session_id)

    def publish_event(self, event: Event):
        if event.type in self.subscriptions:
            self.queue.put_nowait(event)

    async def handle_event(self, event: Event):
        # Log the event to Redis

        await self.redis_manager.save_log(event)

    async def start(self):
        self.active = True
        while self.active:
            try:
                event = await self.queue.get()
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.1)
            await self.handle_event(event)


async def dump_transcript_api(transcript: dict):
    """
    POST transcript to API
    :param transcript: transcript dictionary to be posted
    """
    url = os.environ['TRANSCRIPT_API_URL']
    key = os.environ['TRANSCRIPT_API_KEY']
    headers = {
        'X-API-Key': key,
        'Content-Type': 'application/json'  # Make sure to set the content type for JSON
    }

    async with aiohttp.ClientSession() as session:
        for attempt in range(5):  # make 5 retries
            try:
                async with session.post(url, json=transcript, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        logger.warning(f"Failed to post transcript: HTTP {response.status}")
                        await asyncio.sleep(5)  # Wait for 5 seconds before retrying
            except Exception as e:
                logger.error(f"Error occurred: {e}")
                if attempt < 4:  # Check if it's not the last attempt
                    logger.info("Retrying in 5 seconds...")
                    await asyncio.sleep(5)
                else:
                    logger.error("Max retries reached, giving up.")

