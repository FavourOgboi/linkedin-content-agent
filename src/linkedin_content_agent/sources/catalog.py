from __future__ import annotations

from linkedin_content_agent.config import AppConfig
from linkedin_content_agent.sources.base import RSSSource, RedditHotSource, SignalSource, YouTubeChannelFeedSource


def build_default_sources(config: AppConfig) -> list[SignalSource]:
    sources: list[SignalSource] = []

    for url in config.rss_feeds:
        name = "hackernews" if "hnrss.org" in url else f"rss:{url}"
        sources.append(RSSSource(name=name, url=url, limit=config.signal_limit_per_source))

    for subreddit in config.reddit_subreddits:
        sources.append(RedditHotSource(subreddit=subreddit, limit=config.signal_limit_per_source))

    for channel_id in config.youtube_channel_ids:
        sources.append(YouTubeChannelFeedSource(channel_id=channel_id, limit=config.signal_limit_per_source))

    return sources
