# reporting_and_analytics/slack_utils.py

import requests
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

def send_structured_slack_message(blocks: list, channel: str = 'DEV'):
    """
    Sends a structured Slack message using Block Kit.
    Routes to different webhooks based on the 'channel' parameter.

    Args:
        blocks (list): A list of Slack Block Kit blocks.
        channel (str): The target audience/channel ('DEV', 'CLIENT', 'MANAGER').
                       Defaults to 'DEV'.
    """
    webhook_url = None
    if channel.upper() == 'DEV':
        webhook_url = 'https://hooks.slack.com/services/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'
    elif channel.upper() == 'CLIENT':
        webhook_url = 'https://hooks.slack.com/services/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'
    elif channel.upper() == 'MANAGER':
        webhook_url = 'https://hooks.slack.com/services/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'
    else:
        logger.error(f"Invalid Slack channel specified: {channel}. Defaulting to DEV channel.")
        webhook_url = settings.SLACK_WEBHOOK_URL_DEV

    if not webhook_url:
        logger.error(f"Slack webhook URL for channel '{channel}' is not configured.")
        return

    headers = {'Content-type': 'application/json'}
    payload = {'blocks': blocks}

    try:
        response = requests.post(webhook_url, headers=headers, data=json.dumps(payload), timeout=5)
        response.raise_for_status() # Raise an exception for bad status codes
        logger.info(f"Slack message sent successfully to {channel} channel.")
    except requests.exceptions.Timeout:
        logger.error(f"Slack message to {channel} timed out after 5 seconds.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Slack message to {channel}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"An unexpected error occurred while sending Slack message to {channel}: {e}", exc_info=True)