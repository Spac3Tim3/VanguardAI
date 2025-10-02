import asyncio
import json
import re
import typing as t
from logging import getLogger

import validate
from database import Assessment, Question, Resource
from openai_slackbot.clients.slack import SlackClient
from openai_slackbot.handlers import BaseActionHandler, BaseMessageHandler
from peewee import IntegrityError
from playhouse.shortcuts import model_to_dict
from sdlc_slackbot.config import get_config
from utils import (
    ask_ai,
    field,
    get_form_input,
    input_block,
    submit_block,
)

logger = getLogger(__name__)


# Import from bot.py - these are shared utility functions
def extract_urls(text):
    """Extract URLs from text"""
    import validators
    url_pat = re.compile(
        r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+\b(?!>)"
    )
    urls = re.findall(url_pat, text)
    return [url for url in urls if validators.url(url)]


def hash_content(content):
    """Hash content for change detection"""
    import hashlib
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def fetch_content(url):
    """Fetch content from URLs (Google Docs, Slack, etc.)"""
    from gdoc import gdoc_get
    
    content_fetchers = [
        (
            lambda u: u.startswith(("https://docs.google.com/document", "docs.google.com/document")),
            gdoc_get,
        ),
    ]
    
    for condition, fetcher in content_fetchers:
        if condition(url):
            if asyncio.iscoroutinefunction(fetcher):
                return await fetcher(url)
            else:
                return fetcher(url)
    return None


skip_params = set([
    "id",
    "project_name",
    "links_to_resources",
    "point_of_contact",
    "estimated_go_live_date",
])

multiple_whitespace_pat = re.compile(r"\s+")


def model_params_to_str(params):
    """Convert model params to string for AI context"""
    ss = (v for k, v in params.items() if k not in skip_params)
    return re.sub(multiple_whitespace_pat, " ", "\n".join(map(str, ss))).strip()


def summarize_params(params):
    """Summarize params using AI for context length management"""
    config = get_config()
    summary = {}
    for k, v in params.items():
        if k not in skip_params:
            summary[k] = ask_ai(
                config.base_prompt + config.summary_prompt, v[: config.context_limit]
            )
        else:
            summary[k] = v
    return summary


def get_response_with_retry(prompt, context, max_retries=1):
    """Get AI response with retry logic"""
    prompt = prompt.strip().replace("\n", " ")
    retries = 0
    while retries <= max_retries:
        try:
            response = ask_ai(prompt, context)
            return response
        except json.JSONDecodeError as e:
            logger.error(f"JSON error on attempt {retries + 1}: {e}")
            retries += 1
            if retries > max_retries:
                return {}


def normalize_response(response):
    """Normalize AI response to list format"""
    if isinstance(response, list):
        return [json.loads(block.text) for block in response]
    elif isinstance(response, dict):
        return [response]
    else:
        raise TypeError("Unsupported response type")


def clean_normalized_response(normalized_responses):
    """Break down decision into risk and confidence"""
    for response in normalized_responses:
        if "decision" in response:
            decision = response["decision"]
            response["risk"] = decision.get("risk")
            response["confidence"] = decision.get("confidence")
            response.pop("decision", None)
    return normalized_responses


def risk_and_confidence_to_string(decision):
    """Convert risk and confidence numbers to descriptive strings"""
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


def decision_msg(response):
    """Generate decision message"""
    risk_str, confidence_str = risk_and_confidence_to_string(response)
    risk_num = response["risk"]
    confidence_num = response["confidence"]

    return f"Thanks for your response! Based on this input, we've decided that this project is *{risk_str}({risk_num})* with *{confidence_str}({confidence_num})*. {response['justification']}."


# Form definition
form = [
    input_block(
        "project_name",
        "Project Name",
        field("plain_text_input", "Enter the project name"),
    ),
    input_block(
        "project_description",
        "Project Description",
        field("plain_text_input", "Enter the project description", multiline=True),
    ),
    input_block(
        "links_to_resources",
        "Links to Resources",
        field("plain_text_input", "Enter links to resources", multiline=True),
    ),
    input_block("point_of_contact", "Point of Contact", field("users_select", "Select a user")),
    input_block(
        "estimated_go_live_date",
        "Estimated Go Live Date",
        field("datepicker", "Select a date"),
    ),
    submit_block("submit_form"),
]


class SDLCMessageHandler(BaseMessageHandler):
    """
    Handles app mentions and direct messages for SDLC assessments.
    """

    def __init__(self, slack_client: SlackClient) -> None:
        super().__init__(slack_client)
        self.config = get_config()

    async def should_handle(self, args) -> bool:
        """Handle app mentions and direct messages"""
        event = args.event
        
        # Handle app mentions
        if event.get("type") == "app_mention":
            return True
        
        # Handle direct messages
        if event.get("channel_type") == "im":
            return True
        
        return False

    async def handle(self, args):
        """Send the SDLC assessment form"""
        event = args.event
        ts = event.get("ts")
        
        logger.info(f"Handling message event: {event.get('type')}")
        
        # Post the form as a reply in thread
        await self._slack_client.post_message(
            channel=event.get("channel"),
            blocks=form,
            thread_ts=ts,
        )


class SubmitFormHandler(BaseActionHandler):
    """
    Handles the initial SDLC assessment form submission.
    """

    def __init__(self, slack_client: SlackClient) -> None:
        super().__init__(slack_client)
        self.config = get_config()

    @property
    def action_id(self) -> str:
        return "submit_form"

    async def handle(self, args):
        """Process the submitted assessment form"""
        body = args.body
        
        try:
            ts = body["container"]["message_ts"]
            channel = body["container"].get("channel_id")
            values = body["state"]["values"]
            params = get_form_input(
                values,
                "project_name",
                "project_description",
                "links_to_resources",
                "point_of_contact",
                "estimated_go_live_date",
            )

            validate.required(params, "project_name", "project_description", "point_of_contact")

            await self._slack_client.post_message(
                channel=channel,
                text=self.config.reviewing_message,
                thread_ts=ts,
            )

            try:
                assessment = Assessment.create(**params, user_id=body["user"]["id"])
            except IntegrityError as e:
                raise validate.ValidationError("project_name", "must be unique")

            resources = []
            for url in extract_urls(params.get("links_to_resources", "")):
                content = await fetch_content(url)
                if content:
                    params[url] = content
                    resources.append(
                        dict(
                            assessment=assessment,
                            url=url,
                            content_hash=hash_content(content),
                        )
                    )
            if resources:
                Resource.insert_many(resources).execute()

            context = model_params_to_str(params)
            if len(context) > self.config.context_limit:
                logger.info(f"context too long: {len(context)}. Summarizing...")
                summarized_context = summarize_params(params)
                context = model_params_to_str(summarized_context)
                if len(context) > self.config.context_limit:
                    logger.info(f"Summarized context too long: {len(context)}. Cutting off...")
                    context = context[: self.config.context_limit]

            response = get_response_with_retry(self.config.base_prompt + self.config.initial_prompt, context)
            if not response:
                return

            normalized_response = normalize_response(response)
            clean_response = clean_normalized_response(normalized_response)

            for item in clean_response:
                if item["outcome"] == "decision":
                    assessment.update(**item).execute()
                    await self._slack_client.post_message(
                        channel=channel,
                        text=decision_msg(item),
                        thread_ts=ts,
                    )
                elif item["outcome"] == "followup":
                    db_questions = [dict(assessment=assessment, question=q) for q in item["questions"]]
                    Question.insert_many(db_questions).execute()

                    followup_form = []
                    for i, q in enumerate(item["questions"]):
                        followup_form.append(
                            input_block(
                                f"question_{i}",
                                q,
                                field("plain_text_input", "...", multiline=True),
                            )
                        )
                    followup_form.append(submit_block(f"submit_followup_questions_{assessment.id}"))

                    await self._slack_client.post_message(
                        channel=channel,
                        blocks=followup_form,
                        thread_ts=ts,
                    )
        except validate.ValidationError as e:
            await self._slack_client.post_message(
                channel=channel,
                text=f"{e.field}: {e.issue}",
                thread_ts=ts,
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            await self._slack_client.post_message(
                channel=channel,
                text=self.config.irrecoverable_error_message,
                thread_ts=ts,
            )


class SubmitFollowupQuestionsHandler(BaseActionHandler):
    """
    Handles follow-up questions submission for SDLC assessments.
    """

    def __init__(self, slack_client: SlackClient) -> None:
        super().__init__(slack_client)
        self.config = get_config()

    @property
    def action_id(self) -> str:
        # This needs to match the pattern: submit_followup_questions_*
        return re.compile("submit_followup_questions.*")

    async def handle(self, args):
        """Process the submitted follow-up questions"""
        body = args.body
        
        try:
            assessment_id = int(body["actions"][0]["action_id"].split("_")[-1])
            ts = body["container"]["message_ts"]
            channel = body["container"].get("channel_id")
            assessment = Assessment.get(Assessment.id == assessment_id)
            params = model_to_dict(assessment)
            followup_questions = [q.question for q in assessment.questions]
        except Exception as e:
            logger.error(f"Failed to find params for user {body['user']['id']}", e)
            await self._slack_client.post_message(
                channel=channel,
                text=self.config.recoverable_error_message,
                thread_ts=ts,
            )
            return

        try:
            await self._slack_client.post_message(
                channel=channel,
                text=self.config.reviewing_message,
                thread_ts=ts,
            )

            values = body["state"]["values"]
            for i, q in enumerate(followup_questions):
                params[q] = values[f"question_{i}"][f"question_{i}_input"]["value"]

            for question in assessment.questions:
                question.answer = params[question.question]
                question.save()

            context = model_params_to_str(params)

            response = ask_ai(self.config.base_prompt, context)
            text_to_update = response
            if (
                isinstance(response, dict)
                and "text" in response
                and "type" in response
                and response["type"] == "text"
            ):
                text_to_update = response.text

            normalized_response = normalize_response(text_to_update)
            clean_response = clean_normalized_response(normalized_response)

            for item in clean_response:
                if item["outcome"] == "decision":
                    assessment.update(**item).execute()
                    await self._slack_client.post_message(
                        channel=channel,
                        text=decision_msg(item),
                        thread_ts=ts,
                    )

        except Exception as e:
            logger.error(f"error: {e} processing followup questions: {json.dumps(body, indent=2)}")
            await self._slack_client.post_message(
                channel=channel,
                text=self.config.irrecoverable_error_message,
                thread_ts=ts,
            )
