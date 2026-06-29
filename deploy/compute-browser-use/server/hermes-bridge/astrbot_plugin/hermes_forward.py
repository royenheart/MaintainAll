"""AstrBot Plugin: Forward messages to Hermes Bridge.

This plugin intercepts incoming messages and forwards them to the Hermes Bridge
service, which passes them to Hermes Agent. Hermes Agent's response is then
sent back to the user via AstrBot's platform pipeline.

Installation:
    Copy this directory to AstrBot's data/plugins/hermes_forward/
"""

import asyncio
import json
import logging

import aiohttp

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

logger = logging.getLogger(__name__)

# Configuration — set these in the plugin's config or environment
HERMES_BRIDGE_URL = "http://hermes-bridge:8421"
BRIDGE_AUTH_TOKEN = ""


@register("hermes_forward", "CUA Team", "Forward messages to Hermes Agent via bridge", "1.0.0")
class HermesForwardPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.on_message_event()
    async def forward_to_hermes(self, event: AstrMessageEvent):
        """Forward every incoming message to Hermes Agent."""
        message_str = event.get_message_str()
        if not message_str or not message_str.strip():
            return

        platform = event.get_platform_name()
        sender_id = event.get_sender_id()
        sender_name = event.get_sender_name() or "User"
        session_id = f"{platform}:{sender_id}"

        payload = {
            "session_id": session_id,
            "platform": platform,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "message": message_str,
            "streaming": False,
        }

        headers = {"Content-Type": "application/json"}
        if BRIDGE_AUTH_TOKEN:
            headers["Authorization"] = f"Bearer {BRIDGE_AUTH_TOKEN}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{HERMES_BRIDGE_URL}/api/v1/chat",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error("Hermes Bridge returned %d: %s", resp.status, error_text[:200])
                        yield event.plain_result(
                            f"Sorry, the AI agent is temporarily unavailable. (Error: {resp.status})"
                        )
                        return

                    result = await resp.json()
                    reply = result.get("reply") or result.get("response") or result.get("content", "")
                    if isinstance(reply, list):
                        text_parts = []
                        for part in reply:
                            if isinstance(part, dict):
                                if part.get("type") == "text":
                                    text_parts.append(part.get("text", ""))
                            elif isinstance(part, str):
                                text_parts.append(part)
                        reply = "\n".join(text_parts)

                    if reply:
                        yield event.plain_result(str(reply))
                    else:
                        yield event.plain_result("(Hermes Agent returned no response)")

        except aiohttp.ClientConnectorError:
            logger.error("Cannot connect to Hermes Bridge at %s", HERMES_BRIDGE_URL)
            yield event.plain_result(
                "Sorry, the AI agent service is currently starting up. Please try again in a moment."
            )
        except asyncio.TimeoutError:
            logger.error("Hermes Bridge request timed out")
            yield event.plain_result(
                "Sorry, the AI agent took too long to respond. Please try again."
            )
        except Exception as e:
            logger.error("Error forwarding to Hermes: %s", e, exc_info=True)
            yield event.plain_result(f"Internal error: {str(e)[:100]}")
