import asyncio
import hashlib
import json
import os
import re
import threading
import time
import traceback
from logging import getLogger

import validate
import validators
from database import *
from gdoc import gdoc_get
from openai_slackbot.bot import start_bot
from openai_slackbot.utils.envvars import string
from peewee import *
from playhouse.db_url import *
from playhouse.shortcuts import model_to_dict
from sdlc_slackbot.config import get_config, load_config
from sdlc_slackbot.handlers import (
    SDLCMessageHandler,
    SubmitFollowupQuestionsHandler,
    SubmitFormHandler,
)
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient
from utils import *


logger = getLogger(__name__)

# Global variable to track the background thread
_background_thread = None
_background_thread_stop = threading.Event()


async def send_update_notification(input, response):
    risk_str, confidence_str = risk_and_confidence_to_string(response)
    risk_num = response["risk"]
    confidence_num = response["confidence"]

    msg = f"""
    Project {input['project_name']} has been updated and has a new decision:

    This new decision for the project is that it is: *{risk_str}({risk_num})* with *{confidence_str}({confidence_num})*. {response['justification']}."
    """

    await app.client.chat_postMessage(channel=config.notification_channel_id, text=msg)


def hash_content(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


url_pat = re.compile(
    r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+\b(?!>)"
)


def extract_urls(text):
    logger.info(f"extracting urls from {text}")
    urls = re.findall(url_pat, text)
    return [url for url in urls if validators.url(url)]


async def async_fetch_slack(url):
    parts = url.split("/")
    channel = parts[-2]
    ts = parts[-1]
    ts = ts[1:]  # trim p
    seconds = ts[:-6]
    nanoseconds = ts[-6:]
    result = await app.client.conversations_replies(channel=channel, ts=f"{seconds}.{nanoseconds}")
    return " ".join(message.get("text", "") for message in result.data.get("messages", []))


content_fetchers = [
    (
        lambda u: u.startswith(("https://docs.google.com/document", "docs.google.com/document")),
        gdoc_get,
    ),
    (lambda u: "slack.com/archives" in u, async_fetch_slack),
]


async def fetch_content(url):
    for condition, fetcher in content_fetchers:
        if condition(url):
            if asyncio.iscoroutinefunction(fetcher):
                return await fetcher(url)  # Await the result if it's a coroutine function
            else:
                return fetcher(url)  # Call it directly if it's not a coroutine function


# Shared utility functions for update_resources thread
skip_params = set(
    [
        "id",
        "project_name",
        "links_to_resources",
        "point_of_contact",
        "estimated_go_live_date",
    ]
)

multiple_whitespace_pat = re.compile(r"\s+")


def model_params_to_str(params):
    ss = (v for k, v in params.items() if k not in skip_params)
    return re.sub(multiple_whitespace_pat, " ", "\n".join(map(str, ss))).strip()


def normalize_response(response):
    if isinstance(response, list):
        return [json.loads(block.text) for block in response]
    elif isinstance(response, dict):
        return [response]
    else:
        raise TypeError("Unsupported response type")


def clean_normalized_response(normalized_responses):
    """
    Remove the 'decision' key from each dictionary in a list of dictionaries.
    Break it down into 'risk' and 'confidence'
    """
    for response in normalized_responses:
        if "decision" in response:
            decision = response["decision"]
            response["risk"] = decision.get("risk")
            response["confidence"] = decision.get("confidence")
            response.pop("decision", None)
    return normalized_responses


def risk_and_confidence_to_string(decision):
    # Lookup tables for risk and confidence
    risk_lookup = {
        (1, 2): "extremely low risk",
        (3, 3): "low risk",
        (4, 5): "medium risk",
        (6, 7): "medium-high risk",
        (8, 9): "high risk",
        (10, 10): "critical risk",
    }

    confidence_lookup = {
        (1, 2): "extremely low confidence",
        (3, 3): "low confidence",
        (4, 5): "medium confidence",
        (6, 7): "medium-high confidence",
        (8, 9): "high confidence",
        (10, 10): "extreme confidence",
    }

    def find_in_lookup(value, lookup):
        for (min_val, max_val), descriptor in lookup.items():
            if min_val <= value <= max_val:
                return descriptor
        return "unknown"

    risk_str = find_in_lookup(decision["risk"], risk_lookup)
    confidence_str = find_in_lookup(decision["confidence"], confidence_lookup)

    return risk_str, confidence_str


def update_resources():
    """Background thread to monitor and update resources with graceful shutdown support"""
    while not _background_thread_stop.is_set():
        # Use wait instead of sleep to allow interruption
        if _background_thread_stop.wait(monitor_thread_sleep_seconds):
            break
            
        try:
            for assessment in Assessment.select():
                # Check for stop signal before processing each assessment
                if _background_thread_stop.is_set():
                    break
                    
                logger.info(f"checking {assessment.project_name} for updates")

                assessment_params = model_to_dict(assessment)
                new_params = assessment_params.copy()

                changed = False

                previous_content = ""

                for resource in assessment.resources:
                    new_content = asyncio.run(fetch_content(resource.url))

                    if resource.content_hash != hash_content(new_content):
                        # just save previous content in memory temporarily
                        previous_content = resource.content
                        resource.content = new_content
                        new_params[resource.url] = new_content
                        changed = True

                    if not changed:
                        continue

                    old_context = model_params_to_str(assessment_params)
                    new_context = model_params_to_str(new_params)

                    context = {
                        "previous_context": previous_content,
                        "previous_decision": {
                            "risk": assessment.risk,
                            "confidence": assessment.confidence,
                            "justification": assessment.justification,
                        },
                        "new_context": new_content,
                    }

                    context_json = json.dumps(context, indent=2)

                    new_response = ask_ai(config.base_prompt + config.update_prompt, context_json)

                    resource.content_hash = hash_content(new_content)
                    resource.save()

                    if new_response["outcome"] == "unchanged":
                        continue

                    normalized_response = normalize_response(new_response)
                    clean_response = clean_normalized_response(normalized_response)

                    for item in clean_response:
                        assessment.update(**item).execute()

                    asyncio.run(send_update_notification(assessment_params, new_response))
        except Exception as e:
            logger.error(f"error: {e} updating resources")
            traceback.print_exc()
    
    logger.info("Background resource update thread stopped")


def stop_background_thread():
    """Stop the background thread gracefully"""
    global _background_thread
    if _background_thread and _background_thread.is_alive():
        logger.info("Stopping background thread...")
        _background_thread_stop.set()
        _background_thread.join(timeout=10)
        if _background_thread.is_alive():
            logger.warning("Background thread did not stop gracefully")


monitor_thread_sleep_seconds = 6

if __name__ == "__main__":
    import atexit
    import sys
    
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, "config.toml")
        
        # Load configuration
        logger.info(f"Loading configuration from {config_path}")
        load_config(config_path)
        config = get_config()
        
        # Validate configuration
        if not config.notification_channel_id:
            raise ValueError("notification_channel_id must be set in config.toml")
        
        logger.info("Configuration loaded successfully")
        logger.info(f"Notification channel: {config.notification_channel_id}")

        template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

        # Start background thread for resource monitoring
        logger.info("Starting background resource monitoring thread")
        _background_thread = threading.Thread(target=update_resources, daemon=True)
        _background_thread.start()
        
        # Register cleanup on exit
        atexit.register(stop_background_thread)

        # Use start_bot with proper handler classes
        logger.info("Starting SDLC Slackbot...")
        asyncio.run(
            start_bot(
                openai_organization_id=config.openai_organization_id,
                slack_message_handler=SDLCMessageHandler,
                slack_action_handlers=[SubmitFormHandler, SubmitFollowupQuestionsHandler],
                slack_template_path=template_path,
            )
        )
    except FileNotFoundError as e:
        logger.error(f"Configuration file not found: {e}")
        logger.error("Please ensure config.toml exists in the sdlc_slackbot directory")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please check your configuration and environment variables")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Failed to start SDLC Slackbot: {e}")
        sys.exit(1)
