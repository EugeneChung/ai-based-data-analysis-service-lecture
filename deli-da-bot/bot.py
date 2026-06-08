"""Deli Slack Bot — Socket Mode 호출 방식 테스트.

3가지 트리거를 받아 그대로 echo:
- app_mention      : 채널에서 @bot 멘션
- message.im       : 봇과의 1:1 DM
- message.channels : REPLY_ALL_CHANNEL_IDS 화이트리스트 채널의 모든 일반 메시지
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from dotenv import load_dotenv
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

load_dotenv()

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("deli-da-bot")

BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
APP_TOKEN = os.environ["SLACK_APP_TOKEN"]

REPLY_ALL_CHANNEL_IDS: set[str] = {
    c.strip()
    for c in os.environ.get("REPLY_ALL_CHANNEL_IDS", "").split(",")
    if c.strip()
}

app = AsyncApp(token=BOT_TOKEN)

BOT_USER_ID: str | None = None


async def _resolve_bot_user_id(client: Any) -> str:
    global BOT_USER_ID
    if BOT_USER_ID is None:
        auth = await client.auth_test()
        BOT_USER_ID = str(auth["user_id"])
        logger.info("Bot user id resolved: %s", BOT_USER_ID)
    assert BOT_USER_ID is not None
    return BOT_USER_ID


def _strip_mention(text: str, bot_user_id: str) -> str:
    return text.replace(f"<@{bot_user_id}>", "").strip()


@app.event("app_mention")
async def handle_app_mention(event: dict[str, Any], say: Any, client: Any) -> None:
    bot_user_id = await _resolve_bot_user_id(client)
    user = event.get("user")
    channel = event.get("channel")
    text = _strip_mention(event.get("text", ""), bot_user_id)
    thread_ts = event.get("thread_ts") or event.get("ts")
    logger.info("app_mention channel=%s user=%s text=%r", channel, user, text)
    await say(
        text=(
            f":wave: *app_mention* received\n"
            f"• channel: `{channel}`\n"
            f"• user: <@{user}>\n"
            f"• text: `{text or '(empty)'}`"
        ),
        thread_ts=thread_ts,
    )


@app.event({"type": "message", "channel_type": "im"})
async def handle_dm(event: dict[str, Any], say: Any) -> None:
    if event.get("subtype") or event.get("bot_id"):
        return
    user = event.get("user")
    channel = event.get("channel")
    text = event.get("text", "")
    logger.info("message.im channel=%s user=%s text=%r", channel, user, text)
    await say(
        text=(
            f":speech_balloon: *DM* received\n"
            f"• channel: `{channel}`\n"
            f"• user: <@{user}>\n"
            f"• text: `{text}`"
        )
    )


@app.event({"type": "message", "channel_type": "channel"})
async def handle_channel_message(event: dict[str, Any], say: Any, client: Any) -> None:
    if event.get("subtype") or event.get("bot_id"):
        return
    channel = event.get("channel")
    if channel not in REPLY_ALL_CHANNEL_IDS:
        return
    bot_user_id = await _resolve_bot_user_id(client)
    text = event.get("text", "")
    if f"<@{bot_user_id}>" in text:
        return
    user = event.get("user")
    thread_ts = event.get("thread_ts") or event.get("ts")
    logger.info("message.channels (reply-all) channel=%s user=%s text=%r", channel, user, text)
    await say(
        text=(
            f":mega: *reply-all* received\n"
            f"• channel: `{channel}`\n"
            f"• user: <@{user}>\n"
            f"• text: `{text}`"
        ),
        thread_ts=thread_ts,
    )


@app.event({"type": "message", "channel_type": "group"})
async def handle_private_channel_message(event: dict[str, Any], say: Any, client: Any) -> None:
    await handle_channel_message(event, say, client)


@app.event("message")
async def catch_all_message(event: dict[str, Any]) -> None:
    logger.debug("uncaught message event: %s", event)


async def main() -> None:
    logger.info("Starting Deli Slack Bot in Socket Mode...")
    logger.info("reply-all whitelist: %s", REPLY_ALL_CHANNEL_IDS or "(none)")
    handler = AsyncSocketModeHandler(app, APP_TOKEN)
    await handler.start_async()


if __name__ == "__main__":
    asyncio.run(main())
