import typing as t
from logging import getLogger

import openai
from openai_slackbot.clients.slack import SlackClient
from openai_slackbot.handlers import BaseActionHandler, BaseMessageHandler
from openai_slackbot.utils.envvars import string, validate_required_env_vars
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.app.async_app import AsyncApp

logger = getLogger(__name__)


async def register_app_handlers(
    *,
    app: AsyncApp,
    message_handler: t.Type[BaseMessageHandler],
    action_handlers: t.List[t.Type[BaseActionHandler]],
    slack_client: SlackClient,
):
    if message_handler:
        app.event("message")(message_handler(slack_client).maybe_handle)

    if action_handlers:
        for action_handler in action_handlers:
            handler = action_handler(slack_client)
            app.action(handler.action_id)(handler.maybe_handle)


async def init_bot(
    *,
    openai_organization_id: str,
    slack_message_handler: t.Type[BaseMessageHandler],
    slack_action_handlers: t.List[t.Type[BaseActionHandler]],
    slack_template_path: str,
):
    # Validate required environment variables
    required_vars = ["SLACK_BOT_TOKEN", "SOCKET_APP_TOKEN", "OPENAI_API_KEY"]
    success, missing_vars = validate_required_env_vars(required_vars)
    
    if not success:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # Validate OpenAI organization ID
    if not openai_organization_id:
        error_msg = "openai_organization_id must be provided"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info("Initializing bot with valid configuration")
    logger.info(f"OpenAI Organization ID: {openai_organization_id}")
    
    slack_bot_token = string("SLACK_BOT_TOKEN")
    openai_api_key = string("OPENAI_API_KEY")

    # Init OpenAI API
    openai.organization = openai_organization_id
    openai.api_key = openai_api_key

    # Init slack bot
    app = AsyncApp(token=slack_bot_token)
    slack_client = SlackClient(app.client, slack_template_path)
    await register_app_handlers(
        app=app,
        message_handler=slack_message_handler,
        action_handlers=slack_action_handlers,
        slack_client=slack_client,
    )
    
    logger.info("Bot initialized successfully")
    return app


async def start_app(app):
    socket_app_token = string("SOCKET_APP_TOKEN")
    
    logger.info("Connecting to Slack...")
    handler = AsyncSocketModeHandler(app, socket_app_token)
    
    try:
        await handler.start_async()
    except Exception as e:
        logger.exception(f"Failed to connect to Slack: {e}")
        raise


async def start_bot(
    *,
    openai_organization_id: str,
    slack_message_handler: t.Type[BaseMessageHandler],
    slack_action_handlers: t.List[t.Type[BaseActionHandler]],
    slack_template_path: str,
):
    try:
        app = await init_bot(
            openai_organization_id=openai_organization_id,
            slack_message_handler=slack_message_handler,
            slack_action_handlers=slack_action_handlers,
            slack_template_path=slack_template_path,
        )

        logger.info("Starting bot...")
        await start_app(app)
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise
    except Exception as e:
        logger.exception(f"Failed to start bot: {e}")
        raise
