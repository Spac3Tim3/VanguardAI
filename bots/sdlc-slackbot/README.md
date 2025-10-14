
<p align="center">
  <img width="150" alt="sdlc-slackbot-logo" src="https://github.com/openai/openai-security-bots/assets/4993572/70bbe02c-7c4d-4f72-b154-5df45df9e03d">
  <h1 align="center">SDLC Slackbot</h1>
</p>

SDLC Slackbot decides if a project merits a security review.

## Prerequisites

You will need:
1. A Slack application (aka your sdlc bot) with Socket Mode enabled
2. OpenAI API key

Generate an App-level token for your Slack app, by going to:
```
Your Slack App > Basic Information > App-Level Tokens > Generate Token and Scopes
```
Create a new token with `connections:write` scope. This is your `SOCKET_APP_TOKEN` token.

Once you have them, from the current directory, run:
```
$ make init-env-file
```
and fill in the right values.

Your Slack App needs the following scopes:

- app\_mentions:read
- channels:join
- channels:read
- channels:history
- chat:write
- groups:history
- groups:read
- groups:write
- usergroups:read
- users:read
- users:read.email


## Setup

From the current directory, run:
```
make init-pyproject
```

From the repo root, run:
```
make clean-venv
source venv/bin/activate
make build-bot BOT=sdlc-slackbot
```

## Environment Variables

The bot requires the following environment variables to be set:

| Variable | Required | Description |
|----------|----------|-------------|
| `SLACK_BOT_TOKEN` | ✅ Yes | OAuth token for your Slack bot (starts with `xoxb-`) |
| `SOCKET_APP_TOKEN` | ✅ Yes | App-level token with `connections:write` scope (starts with `xapp-`) |
| `OPENAI_API_KEY` | ✅ Yes | Your OpenAI API key |
| `OPENAI_ORGANIZATION_ID` | ✅ Yes | Your OpenAI organization ID (set in config.toml) |
| `CLAUDE_API_KEY` | ⚠️ Optional | Claude API key if using Anthropic models |

Set these in your `.env` file or export them in your shell.

## Configuration (config.toml)

The bot requires a `config.toml` file in the `sdlc_slackbot` directory. Required fields:

| Field | Type | Description |
|-------|------|-------------|
| `openai_organization_id` | string | Your OpenAI organization ID |
| `notification_channel_id` | string | Slack channel ID for notifications (must start with 'C') |
| `context_limit` | integer | Maximum context length for AI prompts |
| `base_prompt` | string | Base system prompt for AI |
| `initial_prompt` | string | Prompt for initial assessment |
| `update_prompt` | string | Prompt for resource updates |
| `summary_prompt` | string | Prompt for summarization |
| `reviewing_message` | string | Message shown while processing |
| `recoverable_error_message` | string | Message for recoverable errors |
| `irrecoverable_error_message` | string | Message for critical errors |

For optional Google Docs integration you'll need a 'credentials.json' file:
- Go to the Google Cloud Console.
- Select your project.
- Navigate to "APIs & Services" > "Credentials".
- Under "OAuth 2.0 Client IDs", find your client ID and download the JSON file.
- Save it in the `sdlc-slackbot/sdlc_slackbot` directory as `credentials.json`.

## Deployment Checklist

Before deploying, ensure:

- [ ] All required environment variables are set
- [ ] `config.toml` is configured with valid values
- [ ] `notification_channel_id` starts with 'C' (valid Slack channel ID)
- [ ] Bot is added to all channels it needs to access
- [ ] OpenAI API key has sufficient credits/quota
- [ ] Database is properly initialized (if using persistence)

## Running the Bot

⚠️ *Make sure that the bot is added to the channels it needs to read from and post to.* ⚠️

From the repo root, run:

```
make run-bot BOT=sdlc-slackbot
```

The bot will:
1. Validate environment variables
2. Load configuration from `config.toml`
3. Start a background thread to monitor resource changes
4. Connect to Slack via Socket Mode
5. Begin processing app mentions and direct messages

## Troubleshooting

### Bot won't start

**Error: "Missing required environment variable"**
- Ensure all required environment variables are set in your `.env` file
- Run `source .env` if using shell exports

**Error: "Configuration file not found"**
- Ensure `config.toml` exists in `bots/sdlc-slackbot/sdlc_slackbot/`
- Check file permissions

**Error: "channel ID must start with 'C'"**
- Verify `notification_channel_id` in `config.toml` is a valid Slack channel ID
- Get the channel ID by right-clicking the channel → View channel details → Copy ID

### Bot starts but doesn't respond

- Verify the bot is added to channels where it should respond
- Check bot token scopes include all required permissions
- Review logs for handler errors

### Database errors

- Ensure database file has write permissions
- Check that the database schema is initialized
- Verify sufficient disk space

### Google Docs integration not working

- Ensure `credentials.json` is in the correct location
- Verify Google Cloud project has Drive API enabled
- Check OAuth scopes include Drive access

