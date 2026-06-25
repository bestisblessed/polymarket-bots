#!/usr/bin/env python3
"""Normalize a bird-keychain X export and download referenced media."""

from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import re
import sys
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def load_tweets(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        tweets = payload.get("tweets", [])
    else:
        tweets = payload
    if not isinstance(tweets, list):
        raise ValueError(f"{path} does not contain a tweet list")
    return tweets


def discover_sources(raw_dir: Path) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    for path in sorted(raw_dir.rglob("*.json")):
        if path.name.endswith(".meta.json"):
            continue
        try:
            load_tweets(path)
        except (json.JSONDecodeError, ValueError):
            continue
        source_name = path.relative_to(raw_dir).with_suffix("").as_posix()
        sources[source_name] = path
    return sources


def parse_created_at(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return value


def safe_slug(value: str, limit: int = 80) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return (slug or "media")[:limit]


def media_extension(url: str, content_type: str | None = None) -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix
    if suffix:
        return suffix
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if guessed:
            return guessed
    return ".bin"


def iter_media(tweet: dict) -> list[dict]:
    found: list[dict] = []
    for role, item in (("tweet", tweet), ("quoted", tweet.get("quotedTweet") or {})):
        for index, media in enumerate(item.get("media") or []):
            url = media.get("url") or media.get("previewUrl")
            if not url:
                continue
            found.append(
                {
                    "tweet_id": tweet.get("id"),
                    "source_role": role,
                    "source_tweet_id": item.get("id") or tweet.get("id"),
                    "media_index": index,
                    "type": media.get("type"),
                    "url": url,
                    "preview_url": media.get("previewUrl"),
                    "width": media.get("width"),
                    "height": media.get("height"),
                }
            )
    return found


def download_media(items: list[dict], media_dir: Path) -> list[dict]:
    media_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    seen_urls: dict[str, str] = {}

    for item in items:
        if item["url"] in seen_urls:
            manifest.append({**item, "local_path": seen_urls[item["url"]], "download_status": "duplicate"})
            continue

        base = safe_slug(f"{item['tweet_id']}_{item['source_role']}_{item['media_index']}")
        target = media_dir / base
        try:
            req = Request(item["url"], headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=30) as response:
                content = response.read()
                ext = media_extension(item["url"], response.headers.get("Content-Type"))
            if not target.suffix:
                target = target.with_suffix(ext)
            target.write_bytes(content)
            status = "downloaded"
            local_path = str(target)
            seen_urls[item["url"]] = local_path
        except Exception as exc:  # noqa: BLE001 - export should continue on one bad media URL.
            status = f"error: {exc}"
            local_path = ""

        manifest.append({**item, "local_path": local_path, "download_status": status})
    return manifest


def normalize_tweet(tweet: dict, sources: list[str]) -> dict:
    quoted = tweet.get("quotedTweet") or {}
    return {
        "id": tweet.get("id"),
        "url": f"https://x.com/{tweet.get('author', {}).get('username', 'i')}/status/{tweet.get('id')}",
        "created_at": parse_created_at(tweet.get("createdAt")),
        "created_at_raw": tweet.get("createdAt"),
        "text": tweet.get("text"),
        "author_username": tweet.get("author", {}).get("username"),
        "author_name": tweet.get("author", {}).get("name"),
        "author_id": tweet.get("authorId"),
        "conversation_id": tweet.get("conversationId"),
        "in_reply_to_status_id": tweet.get("inReplyToStatusId"),
        "reply_count": tweet.get("replyCount"),
        "retweet_count": tweet.get("retweetCount"),
        "like_count": tweet.get("likeCount"),
        "quoted_tweet_id": quoted.get("id"),
        "quoted_author_username": quoted.get("author", {}).get("username"),
        "quoted_text": quoted.get("text"),
        "has_media": bool(tweet.get("media")),
        "has_quoted_media": bool(quoted.get("media")),
        "sources": sources,
        "raw": tweet,
    }


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--author", default="balthazarpoly")
    args = parser.parse_args()

    sources = discover_sources(args.raw_dir)
    if not sources:
        raise ValueError(f"No tweet JSON sources found under {args.raw_dir}")
    by_id: dict[str, dict] = {}
    source_by_id: dict[str, list[str]] = {}

    for source_name, source_path in sources.items():
        for tweet in load_tweets(source_path):
            tweet_id = tweet.get("id")
            if not tweet_id:
                continue
            author_username = (tweet.get("author") or {}).get("username")
            if args.author and author_username and author_username.lower() != args.author.lower():
                continue
            by_id.setdefault(tweet_id, tweet)
            source_by_id.setdefault(tweet_id, []).append(source_name)

    normalized = [
        normalize_tweet(tweet, sorted(set(source_by_id[tweet_id])))
        for tweet_id, tweet in by_id.items()
    ]
    normalized.sort(key=lambda row: row.get("created_at") or "", reverse=True)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "tweets_combined.json").write_text(json.dumps(normalized, indent=2, ensure_ascii=False))
    with (args.out_dir / "tweets_combined.jsonl").open("w") as handle:
        for row in normalized:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    tweet_fields = [
        "id",
        "url",
        "created_at",
        "text",
        "conversation_id",
        "in_reply_to_status_id",
        "reply_count",
        "retweet_count",
        "like_count",
        "quoted_tweet_id",
        "quoted_author_username",
        "has_media",
        "has_quoted_media",
        "sources",
    ]
    write_csv(args.out_dir / "tweets_combined.csv", normalized, tweet_fields)

    media_items: list[dict] = []
    for tweet in by_id.values():
        media_items.extend(iter_media(tweet))
    media_manifest = download_media(media_items, args.out_dir / "media")
    (args.out_dir / "media_manifest.json").write_text(json.dumps(media_manifest, indent=2, ensure_ascii=False))
    write_csv(
        args.out_dir / "media_manifest.csv",
        media_manifest,
        [
            "tweet_id",
            "source_role",
            "source_tweet_id",
            "media_index",
            "type",
            "url",
            "preview_url",
            "width",
            "height",
            "local_path",
            "download_status",
        ],
    )

    summary = {
        "unique_tweets": len(normalized),
        "raw_counts": {name: len(load_tweets(path)) for name, path in sources.items()},
        "media_items": len(media_manifest),
        "media_downloaded": sum(1 for item in media_manifest if item["download_status"] == "downloaded"),
        "media_errors": [item for item in media_manifest if item["download_status"].startswith("error:")],
        "author_filter": args.author,
        "tweet_ids": [row["id"] for row in normalized],
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
