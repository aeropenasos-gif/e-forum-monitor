"""
reddit_source.py
-----------------
Следи новите коментари (и по избор — нови постове) в списък от
subreddit-и, използвайки официалното Reddit API чрез библиотеката PRAW.

Изисква три "тайни" стойности, зададени като GitHub Secrets (виж README.md):
    REDDIT_CLIENT_ID
    REDDIT_CLIENT_SECRET
    REDDIT_USER_AGENT

Не се изисква Reddit потребителско име/парола — работим в read-only
режим, което е достатъчно за следене на публични коментари и постове.
"""

import os
import time

import praw


def _build_reddit_client():
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent = os.environ.get("REDDIT_USER_AGENT") or "e-forum-monitor/1.0"

    if not client_id or not client_secret:
        raise RuntimeError(
            "Липсват REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET (GitHub Secrets). "
            "Виж README.md -> 'Настройка на Reddit API'."
        )

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )
    reddit.read_only = True
    return reddit


def fetch_new_items(reddit_cfg: dict):
    """
    Генератор, който връща речници във формат:
        {
            "id": "<уникален reddit id>",
            "url": "https://reddit.com/...",
            "text": "<заглавие/тяло на поста или коментара>",
            "source_label": "Reddit r/<subreddit>",
        }
    """
    subreddits = reddit_cfg.get("subreddits", []) or []
    if not subreddits:
        return

    fetch_limit = int(reddit_cfg.get("fetch_limit", 100))
    include_submissions = bool(reddit_cfg.get("include_submissions", True))

    reddit = _build_reddit_client()
    multi = "+".join(subreddits)
    subreddit = reddit.subreddit(multi)

    # Нови коментари
    for comment in subreddit.comments(limit=fetch_limit):
        yield {
            "id": f"comment_{comment.id}",
            "url": f"https://www.reddit.com{comment.permalink}",
            "text": comment.body or "",
            "source_label": f"Reddit r/{comment.subreddit.display_name} (коментар)",
            # Reddit ни дава точния момент на публикуване (UTC epoch) —
            # това е надеждно, за разлика от site_search източника.
            "created_at": float(comment.created_utc),
        }

    # Нови постове (по избор)
    if include_submissions:
        for submission in subreddit.new(limit=fetch_limit):
            title = submission.title or ""
            selftext = submission.selftext or ""
            yield {
                "id": f"submission_{submission.id}",
                "url": f"https://www.reddit.com{submission.permalink}",
                "text": f"{title}\n{selftext}",
                "source_label": f"Reddit r/{submission.subreddit.display_name} (пост)",
                "created_at": float(submission.created_utc),
            }
