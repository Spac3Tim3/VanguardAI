<p align="center">
  <img width="150" alt="triage-slackbot-logo" src="https://github.com/openai/openai-security-bots/assets/124844323/5ac519fa-db9b-43f4-90cb-4d6d84240853](https://github.com/openai/openai-security-bots/assets/124844323/5ac519fa-db9b-43f4-90cb-4d6d84240853">
  <h1 align="center">Incident Response Slackbot</h1>
</p>

Incident Response Slackbot automatically chats with users who have been part of an incident alert.



## Prerequisites

You will need:
1. A Slack application (aka your triage bot) with Socket Mode enabled
2. OpenAI API key

Grab your `SLACK_BOT_TOKEN` by Oauth & Permissions tab in your Slack App page.

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

 - users:read
 - channels:history
 - chat:write
 - groups:history

## Setup

From the current directory, run:
```
make init-pyproject
```

From the repo root, run:
```
make clean-venv
source venv/bin/activate
make build-bot BOT=incident-response-slackbot
```

## Environment Variables

The bot requires the following environment variables to be set:

| Variable | Required | Description |
|----------|----------|-------------|
| `SLACK_BOT_TOKEN` | ✅ Yes | OAuth token for your Slack bot (starts with `xoxb-`) |
| `SOCKET_APP_TOKEN` | ✅ Yes | App-level token with `connections:write` scope (starts with `xapp-`) |
| `OPENAI_API_KEY` | ✅ Yes | Your OpenAI API key |

Set these in your `.env` file or export them in your shell.

## Configuration (config.toml)

The bot requires a `config.toml` file in the `incident_response_slackbot` directory. Key fields:

| Field | Type | Description |
|-------|------|-------------|
| `openai_organization_id` | string | Your OpenAI organization ID |
| `feed_channel_id` | string | Slack channel ID for alert feed (must start with 'C') |

## Deployment Checklist

Before deploying, ensure:

- [ ] All required environment variables are set
- [ ] `config.toml` is configured with valid `feed_channel_id`
- [ ] `feed_channel_id` starts with 'C' (valid Slack channel ID)
- [ ] Bot is added to the feed channel
- [ ] OpenAI API key has sufficient credits/quota
- [ ] Alert system/database is properly configured

## Run bot with example configuration

The example configuration is `config.toml`. Replace the configuration values as needed. In particular, the bot will post to channel `feed_channel_id`, and will take an OpenAI Organization ID associated with your OpenAI API key.

⚠️ *Make sure that the bot is added to the channels it needs to read from and post to.* ⚠️

We will need to add example alerts to `./scripts/alerts.toml` Replace with alert information and user_id. To get the user_id:
1. Click on the desired user name within Slack. 
2. Click on the ellpises (three dots).
3. Click on "Copy Member ID".

⚠️ *These are mock alerts. In real-world scenarios, this will be integrated with alert feed/database* ⚠️

To generate an axample alert, in this directory, run:
```
python ./scripts/send_alert.py
```

An example alert will be sent to the channel.


https://github.com/openai/openai-security-bots/assets/124844323/b919639c-b691-4b01-aa0c-7be987c9a70b


To have the bot start listening, run the following from the repo root:

```
make run-bot BOT=incident-response-slackbot
```

Now you can start a chat with a user, or do nothing. 
When you start a chat, 

1. The bot will reach out to the user involved with the alert
2. Post a message to the original thread in monitoring channel what was sent to the user (message generated with OpenAI API)
3. Post any messages the user sends to original thread
4. Checks to see if the user has answered the question using OpenAI's API.
 - If yes, end the chat and provide a summary to the original thread
 - If no, continues sending a message to the user, and repeats this step
   
Let's start a chat:

https://github.com/openai/openai-security-bots/assets/124844323/4b5dd292-b4d3-437a-9809-d6d80e824a9d

## Troubleshooting

### Bot won't start

**Error: "Missing required environment variable"**
- Ensure all required environment variables are set in your `.env` file
- Run `source .env` if using shell exports

**Error: "Configuration file not found"**
- Ensure `config.toml` exists in `bots/incident-response-slackbot/incident_response_slackbot/`
- Check file permissions

**Error: "channel ID must start with 'C'"**
- Verify `feed_channel_id` in `config.toml` is a valid Slack channel ID
- Get the channel ID by right-clicking the channel → View channel details → Copy ID

### Bot starts but doesn't process alerts

- Verify the bot is added to the feed channel
- Check bot token scopes include all required permissions
- Review logs for handler errors
- Ensure alerts are being sent via `send_alert.py` script

### Chat not starting with users

- Verify bot has permission to send direct messages
- Check that user IDs in `alerts.toml` are correct
- Ensure users have not disabled DMs from bots

### Database errors

- Check that the mock database is initialized
- Verify file permissions for database storage
- In production, ensure proper database connection

## Alert Details

In practice, the app will connect with a database or queuing system that monitors alerts. We provide a mock alert system here, and a mock database to hold the state of users and their alerts.

In the `alerts.toml` file:

```
[[ alerts ]]
id = "pivot"
...
user_id = ID of person to start chat with (@harold user)

[alerts.properties]
source_host = "source.machine.org"
destination_host = "destination.machine.org"

[[ alerts ]]
id = "privesc"
...
user_id = ID of person to start chat with (@harold user)
```
