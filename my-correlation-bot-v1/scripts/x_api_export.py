#!/usr/bin/env python3
"""Small official X API v2 exporter for user timelines, search, usage, and media."""

from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import os
import re
import sys
import time
from base64 import b64encode
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


API_BASE = "https://api.x.com/2"
APP_BEARER_TOKEN_URL = "https://api.twitter.com/oauth2/token"
DEFAULT_TWEET_FIELDS = ",".join(
    [
        "attachments",
        "author_id",
        "conversation_id",
        "created_at",
        "display_text_range",
        "entities",
        "id",
        "in_reply_to_user_id",
        "lang",
        "possibly_sensitive",
        "public_metrics",
        "referenced_tweets",
        "reply_settings",
        "source",
        "text",
    ]
)
DEFAULT_EXPANSIONS = ",".join(
    [
        "attachments.media_keys",
        "author_id",
        "entities.mentions.username",
        "in_reply_to_user_id",
        "referenced_tweets.id",
        "referenced_tweets.id.attachments.media_keys",
        "referenced_tweets.id.author_id",
    ]
)
DEFAULT_MEDIA_FIELDS = ",".join(
    [
        "alt_text",
        "duration_ms",
        "height",
        "media_key",
        "preview_image_url",
        "public_metrics",
        "type",
        "url",
        "variants",
        "width",
    ]
)
DEFAULT_USER_FIELDS = ",".join(
    [
        "created_at",
        "description",
        "entities",
        "id",
        "location",
        "name",
        "profile_image_url",
        "protected",
        "public_metrics",
        "url",
        "username",
        "verified",
    ]
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_env_value(value: str) -> str:
    value = value.strip()
    if value.startswith("export "):
        value = value[len("export ") :].strip()
    if "=" not in value:
        return ""
    value = value.split("=", 1)[1].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        key = key.split("=", 1)[0].strip()
        os.environ.setdefault(key, parse_env_value(line))


def bearer_token() -> str:
    for key in ("X_BEARER_TOKEN", "TWITTER_BEARER_TOKEN", "BEARER_TOKEN"):
        value = os.environ.get(key)
        if value:
            return value
    raise SystemExit("Missing X_BEARER_TOKEN, TWITTER_BEARER_TOKEN, or BEARER_TOKEN")


def api_key_secret() -> tuple[str, str]:
    api_key = os.environ.get("X_API_KEY") or os.environ.get("TWITTER_API_KEY")
    api_secret = os.environ.get("X_API_SECRET") or os.environ.get("TWITTER_API_SECRET")
    if not api_key or not api_secret:
        raise SystemExit("Missing X_API_KEY/X_API_SECRET or TWITTER_API_KEY/TWITTER_API_SECRET")
    return api_key, api_secret


def mint_app_bearer_token() -> str:
    api_key, api_secret = api_key_secret()
    credentials = b64encode(f"{api_key}:{api_secret}".encode()).decode()
    req = Request(
        APP_BEARER_TOKEN_URL,
        data=urlencode({"grant_type": "client_credentials"}).encode(),
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "User-Agent": "x-api-export/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"X bearer token refresh failed: {exc.code} {exc.reason}\n{body}") from exc

    token = payload.get("access_token")
    if not token:
        raise RuntimeError("X bearer token refresh did not return access_token")
    os.environ["X_BEARER_TOKEN"] = token
    return token


def upsert_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        key_line = stripped[len("export ") :].strip() if stripped.startswith("export ") else stripped
        key = key_line.split("=", 1)[0].strip() if "=" in key_line else ""
        if key in values:
            output.append(f'{key}="{values[key]}"')
            seen.add(key)
        else:
            output.append(line)
    for key, value in values.items():
        if key not in seen:
            output.append(f'{key}="{value}"')
    path.write_text("\n".join(output).rstrip() + "\n")


def request_json(path: str, params: dict[str, str | int | None] | None = None, retry_auth: bool = True) -> dict:
    url = f"{API_BASE}{path}"
    if params:
        filtered = {key: value for key, value in params.items() if value not in (None, "")}
        if filtered:
            url = f"{url}?{urlencode(filtered)}"
    req = Request(url, headers={"Authorization": f"Bearer {bearer_token()}", "User-Agent": "x-api-export/1.0"})
    try:
        with urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code == 401 and retry_auth and (os.environ.get("X_API_KEY") or os.environ.get("TWITTER_API_KEY")):
            print("Stored bearer token was rejected; refreshing app-only bearer token and retrying once.", file=sys.stderr)
            mint_app_bearer_token()
            return request_json(path, params, retry_auth=False)
        raise RuntimeError(f"X API request failed: {exc.code} {exc.reason}\n{body}") from exc


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def lookup_user(username: str) -> dict:
    username = username.removeprefix("@")
    return request_json(
        f"/users/by/username/{username}",
        {
            "user.fields": DEFAULT_USER_FIELDS,
            "expansions": "pinned_tweet_id",
            "tweet.fields": DEFAULT_TWEET_FIELDS,
        },
    )


def paginated_get(path: str, params: dict[str, str | int | None], token_param: str, max_pages: int, delay: float) -> list[dict]:
    pages: list[dict] = []
    token: str | None = None
    for page_number in range(1, max_pages + 1):
        page_params = dict(params)
        if token:
            page_params[token_param] = token
        page = request_json(path, page_params)
        page["_export_page_number"] = page_number
        pages.append(page)
        meta = page.get("meta") or {}
        token = meta.get("next_token")
        if not token:
            break
        if delay:
            time.sleep(delay)
    return pages


def export_timeline(user_id: str, max_pages: int, delay: float) -> list[dict]:
    return paginated_get(
        f"/users/{user_id}/tweets",
        {
            "max_results": 100,
            "tweet.fields": DEFAULT_TWEET_FIELDS,
            "expansions": DEFAULT_EXPANSIONS,
            "media.fields": DEFAULT_MEDIA_FIELDS,
            "user.fields": DEFAULT_USER_FIELDS,
        },
        "pagination_token",
        max_pages,
        delay,
    )


def export_search(query: str, max_pages: int, delay: float, recent: bool = False) -> list[dict]:
    endpoint = "/tweets/search/recent" if recent else "/tweets/search/all"
    max_results = 100 if recent else 500
    return paginated_get(
        endpoint,
        {
            "query": query,
            "max_results": max_results,
            "tweet.fields": DEFAULT_TWEET_FIELDS,
            "expansions": DEFAULT_EXPANSIONS,
            "media.fields": DEFAULT_MEDIA_FIELDS,
            "user.fields": DEFAULT_USER_FIELDS,
            "sort_order": "recency",
        },
        "next_token",
        max_pages,
        delay,
    )


def collect_media_by_key(pages: list[dict]) -> dict[str, dict]:
    media: dict[str, dict] = {}
    for page in pages:
        for item in (page.get("includes") or {}).get("media") or []:
            key = item.get("media_key")
            if key:
                media[key] = item
    return media


def normalize_pages(username: str, sources: dict[str, list[dict]]) -> list[dict]:
    tweets_by_id: dict[str, dict] = {}
    includes_media_by_source = {source: collect_media_by_key(pages) for source, pages in sources.items()}
    source_by_id: dict[str, list[str]] = {}

    for source, pages in sources.items():
        for page in pages:
            for tweet in page.get("data") or []:
                tweet_id = tweet.get("id")
                if not tweet_id:
                    continue
                tweets_by_id.setdefault(tweet_id, tweet)
                source_by_id.setdefault(tweet_id, []).append(source)

    rows: list[dict] = []
    for tweet_id, tweet in tweets_by_id.items():
        media_keys = (tweet.get("attachments") or {}).get("media_keys") or []
        media = []
        for source in source_by_id.get(tweet_id, []):
            media_map = includes_media_by_source.get(source, {})
            media.extend([media_map[key] for key in media_keys if key in media_map])
        media_keys_seen: set[str] = set()
        unique_media = []
        for item in media:
            key = item.get("media_key")
            if key and key not in media_keys_seen:
                media_keys_seen.add(key)
                unique_media.append(item)

        rows.append(
            {
                "id": tweet_id,
                "url": f"https://x.com/{username}/status/{tweet_id}",
                "created_at": tweet.get("created_at"),
                "text": tweet.get("text"),
                "author_id": tweet.get("author_id"),
                "conversation_id": tweet.get("conversation_id"),
                "in_reply_to_user_id": tweet.get("in_reply_to_user_id"),
                "referenced_tweets": tweet.get("referenced_tweets") or [],
                "public_metrics": tweet.get("public_metrics") or {},
                "lang": tweet.get("lang"),
                "source": tweet.get("source"),
                "media": unique_media,
                "sources": sorted(set(source_by_id.get(tweet_id, []))),
                "raw": tweet,
            }
        )
    rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "id",
        "url",
        "created_at",
        "text",
        "conversation_id",
        "in_reply_to_user_id",
        "like_count",
        "reply_count",
        "retweet_count",
        "quote_count",
        "media_count",
        "sources",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        for row in rows:
            metrics = row.get("public_metrics") or {}
            writer.writerow(
                {
                    "id": row.get("id"),
                    "url": row.get("url"),
                    "created_at": row.get("created_at"),
                    "text": row.get("text"),
                    "conversation_id": row.get("conversation_id"),
                    "in_reply_to_user_id": row.get("in_reply_to_user_id"),
                    "like_count": metrics.get("like_count"),
                    "reply_count": metrics.get("reply_count"),
                    "retweet_count": metrics.get("retweet_count"),
                    "quote_count": metrics.get("quote_count"),
                    "media_count": len(row.get("media") or []),
                    "sources": ",".join(row.get("sources") or []),
                }
            )


def safe_slug(value: str, limit: int = 90) -> str:
    return (re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "media")[:limit]


def choose_media_url(media: dict) -> str:
    if media.get("url"):
        return media["url"]
    variants = media.get("variants") or []
    mp4_variants = [item for item in variants if item.get("url") and item.get("content_type") == "video/mp4"]
    if mp4_variants:
        mp4_variants.sort(key=lambda item: item.get("bit_rate") or 0, reverse=True)
        return mp4_variants[0]["url"]
    if media.get("preview_image_url"):
        return media["preview_image_url"]
    return ""


def media_extension(url: str, content_type: str | None) -> str:
    suffix = Path(urlparse(url).path).suffix
    if suffix:
        return suffix
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if guessed:
            return guessed
    return ".bin"


def download_media(rows: list[dict], media_dir: Path) -> list[dict]:
    media_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    seen: dict[str, str] = {}
    for row in rows:
        for index, media in enumerate(row.get("media") or []):
            url = choose_media_url(media)
            item = {
                "tweet_id": row.get("id"),
                "media_index": index,
                "media_key": media.get("media_key"),
                "type": media.get("type"),
                "url": url,
                "local_path": "",
                "download_status": "missing_url",
            }
            if not url:
                manifest.append(item)
                continue
            if url in seen:
                item["local_path"] = seen[url]
                item["download_status"] = "duplicate"
                manifest.append(item)
                continue
            target_base = media_dir / safe_slug(f"{row.get('id')}_{index}_{media.get('media_key') or media.get('type')}")
            try:
                req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(req, timeout=60) as response:
                    body = response.read()
                    ext = media_extension(url, response.headers.get("Content-Type"))
                target = target_base.with_suffix(ext)
                target.write_bytes(body)
                item["local_path"] = str(target)
                item["download_status"] = "downloaded"
                seen[url] = str(target)
            except Exception as exc:  # noqa: BLE001
                item["download_status"] = f"error: {exc}"
            manifest.append(item)
    return manifest


def command_lookup(args: argparse.Namespace) -> int:
    load_env_file(args.env)
    payload = lookup_user(args.username)
    if args.out:
        write_json(args.out, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def command_usage(args: argparse.Namespace) -> int:
    load_env_file(args.env)
    payload = request_json("/usage/tweets")
    if args.out:
        write_json(args.out, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def command_refresh_bearer(args: argparse.Namespace) -> int:
    load_env_file(args.env)
    token = mint_app_bearer_token()
    if args.save:
        upsert_env_file(args.env, {"X_BEARER_TOKEN": token})
    print(json.dumps({"ok": True, "saved": bool(args.save), "env": str(args.env)}))
    return 0


def command_auth_check(args: argparse.Namespace) -> int:
    load_env_file(args.env)
    payload = request_json("/users/by/username/XDevelopers", {"user.fields": "id,username"})
    user = payload.get("data") or {}
    print(json.dumps({"ok": True, "username": user.get("username"), "id": user.get("id")}, indent=2))
    return 0


def command_export(args: argparse.Namespace) -> int:
    load_env_file(args.env)
    username = args.username.removeprefix("@")
    out_dir = args.out_dir or (project_root() / "data" / f"x_official_{username}")
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    user_payload = lookup_user(username)
    write_json(raw_dir / "user.json", user_payload)
    user = user_payload.get("data") or {}
    user_id = user.get("id")
    if not user_id:
        raise SystemExit(f"Could not resolve user id for {username}")

    sources: dict[str, list[dict]] = {}
    timeline_pages = export_timeline(user_id, args.max_pages, args.delay)
    sources["timeline"] = timeline_pages
    write_json(raw_dir / "timeline_pages.json", timeline_pages)

    search_query = f"from:{username}"
    try:
        search_pages = export_search(search_query, args.max_pages, args.delay, recent=False)
        sources["search_all"] = search_pages
        write_json(raw_dir / "search_all_pages.json", search_pages)
    except RuntimeError as exc:
        write_json(raw_dir / "search_all_error.json", {"query": search_query, "error": str(exc)})
        if not args.no_recent_fallback:
            recent_pages = export_search(search_query, args.max_pages, args.delay, recent=True)
            sources["search_recent"] = recent_pages
            write_json(raw_dir / "search_recent_pages.json", recent_pages)

    rows = normalize_pages(username, sources)
    write_json(out_dir / "tweets_combined.json", rows)
    with (out_dir / "tweets_combined.jsonl").open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_csv(out_dir / "tweets_combined.csv", rows)

    media_manifest = []
    if args.download_media:
        media_manifest = download_media(rows, out_dir / "media")
        write_json(out_dir / "media_manifest.json", media_manifest)

    summary = {
        "username": username,
        "user_id": user_id,
        "tweet_count": len(rows),
        "sources": {name: sum(len(page.get("data") or []) for page in pages) for name, pages in sources.items()},
        "media_items": sum(len(row.get("media") or []) for row in rows),
        "media_downloaded": sum(1 for item in media_manifest if item.get("download_status") == "downloaded"),
        "out_dir": str(out_dir),
    }
    write_json(out_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=project_root() / ".env")
    subparsers = parser.add_subparsers(dest="command", required=True)

    lookup = subparsers.add_parser("lookup-user")
    lookup.add_argument("username")
    lookup.add_argument("--out", type=Path)
    lookup.set_defaults(func=command_lookup)

    usage = subparsers.add_parser("usage")
    usage.add_argument("--out", type=Path)
    usage.set_defaults(func=command_usage)

    refresh = subparsers.add_parser("refresh-bearer")
    refresh.add_argument("--save", action="store_true")
    refresh.set_defaults(func=command_refresh_bearer)

    auth_check = subparsers.add_parser("auth-check")
    auth_check.set_defaults(func=command_auth_check)

    export = subparsers.add_parser("export-user")
    export.add_argument("username")
    export.add_argument("--out-dir", type=Path)
    export.add_argument("--max-pages", type=int, default=20)
    export.add_argument("--delay", type=float, default=1.0)
    export.add_argument("--download-media", action="store_true")
    export.add_argument("--no-recent-fallback", action="store_true")
    export.set_defaults(func=command_export)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
