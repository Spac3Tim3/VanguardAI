import asyncio
import os

from openai_slackbot.bot import start_bot
from triage_slackbot.config import get_config, load_config
from triage_slackbot.handlers import (
    InboundRequestAcknowledgeHandler,
    InboundRequestHandler,
    InboundRequestRecategorizeHandler,
    InboundRequestRecategorizeSelectConversationHandler,
    InboundRequestRecategorizeSelectHandler,
)

if __name__ == "__main__":
    import sys
    from logging import getLogger
    
    logger = getLogger(__name__)
    
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, "config.toml")
        
        # Load configuration
        logger.info(f"Loading configuration from {config_path}")
        load_config(config_path)
        config = get_config()
        
        # Validate configuration
        if not config.inbound_request_channel_id:
            raise ValueError("inbound_request_channel_id must be set in config.toml")
        
        logger.info("Configuration loaded successfully")
        logger.info(f"Inbound request channel: {config.inbound_request_channel_id}")

        message_handler = InboundRequestHandler
        action_handlers = [
            InboundRequestAcknowledgeHandler,
            InboundRequestRecategorizeHandler,
            InboundRequestRecategorizeSelectHandler,
            InboundRequestRecategorizeSelectConversationHandler,
        ]

        template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

        # Start bot
        logger.info("Starting Triage Slackbot...")
        asyncio.run(
            start_bot(
                openai_organization_id=config.openai_organization_id,
                slack_message_handler=message_handler,
                slack_action_handlers=action_handlers,
                slack_template_path=template_path,
            )
        )
    except FileNotFoundError as e:
        logger.error(f"Configuration file not found: {e}")
        logger.error("Please ensure config.toml exists in the triage_slackbot directory")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please check your configuration and environment variables")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Failed to start Triage Slackbot: {e}")
        sys.exit(1)
