"""Slack Web API integration."""

from dataclasses import dataclass


class SlackError(Exception):
    """Raised when a Slack operation fails."""


@dataclass
class SlackMessage:
    channel: str
    ts: str
    text: str


def get_client(token: str | None):
    """Get a Slack WebClient. Returns None if no token provided."""
    if not token:
        return None
    from slack_sdk import WebClient
    return WebClient(token=token)


def send_message(
    token: str | None,
    channel: str,
    text: str,
    blocks: list[dict] | None = None,
) -> SlackMessage:
    """Send a message to a Slack channel."""
    client = get_client(token)
    if not client:
        raise SlackError("Slack not configured: SLACK_BOT_TOKEN not set")

    response = client.chat_postMessage(
        channel=channel,
        text=text,
        blocks=blocks,
    )

    return SlackMessage(
        channel=response["channel"],
        ts=response["ts"],
        text=text,
    )


def format_task_notification(task_id: str, title: str, status: str, project: str) -> list[dict]:
    """Format a task notification as Slack blocks."""
    status_emoji = {
        "todo": ":white_circle:",
        "in-progress": ":large_blue_circle:",
        "done": ":white_check_mark:",
        "blocked": ":red_circle:",
    }
    emoji = status_emoji.get(status, ":grey_question:")

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{emoji} *Task Update*\n*{title}* (`{task_id}`)\nStatus: *{status}* | Project: {project}",
            },
        }
    ]


def format_pr_review_request(
    task_id: str,
    title: str,
    branch: str,
    pr_url: str | None = None,
) -> list[dict]:
    """Format a PR review request as Slack blocks."""
    pr_link = f"\n<{pr_url}|View Pull Request>" if pr_url else ""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":eyes: *Review Requested*\n*{title}* (`{task_id}`)\nBranch: `{branch}`{pr_link}",
            },
        },
    ]


def format_status_update(project: str, tasks: list[dict]) -> list[dict]:
    """Format a project status update as Slack blocks."""
    counts = {"todo": 0, "in-progress": 0, "done": 0, "blocked": 0}
    for t in tasks:
        s = t.get("status", "todo")
        counts[s] = counts.get(s, 0) + 1

    total = sum(counts.values())
    progress = counts["done"] / total * 100 if total > 0 else 0

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":bar_chart: *Project Status: {project}*\n"
                    f":white_check_mark: Done: {counts['done']} | "
                    f":large_blue_circle: In Progress: {counts['in-progress']} | "
                    f":white_circle: Todo: {counts['todo']} | "
                    f":red_circle: Blocked: {counts['blocked']}\n"
                    f"Progress: {progress:.0f}% ({counts['done']}/{total})"
                ),
            },
        }
    ]
