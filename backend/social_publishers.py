import os

import requests


ALLOWED_PLATFORMS = {"instagram", "facebook", "x"}
DEFAULT_META_GRAPH_VERSION = "v20.0"
REQUEST_TIMEOUT = 30


def is_real_publishing_enabled() -> bool:
    return os.getenv("ENABLE_REAL_PUBLISHING", "false").strip().lower() == "true"


def real_publishing_enabled() -> bool:
    return is_real_publishing_enabled()


def missing_env(names: list[str]) -> list[str]:
    return [name for name in names if not os.getenv(name)]


def redact_secrets(text: str) -> str:
    redacted = text
    secret_names = [
        "META_PAGE_ACCESS_TOKEN",
        "X_BEARER_USER_TOKEN",
        "X_API_KEY",
        "X_API_SECRET",
        "X_ACCESS_TOKEN",
        "X_ACCESS_TOKEN_SECRET",
    ]
    for name in secret_names:
        value = os.getenv(name)
        if value:
            redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def api_error(response) -> dict:
    try:
        details = response.json()
    except ValueError:
        details = response.text
    return {
        "success": False,
        "mode": "real",
        "status_code": response.status_code,
        "error": redact_secrets(str(details)),
    }


def mock_result(post: dict, platform: str) -> dict:
    return {
        "success": True,
        "mode": "mock",
        "platform": platform,
        "message": "Mock publish successful. No real post was sent.",
        "post_id": post["id"],
    }


def missing_config_result(platform: str, names: list[str]) -> dict:
    return {
        "success": False,
        "mode": "real",
        "platform": platform,
        "error": f"Missing required configuration: {', '.join(names)}",
    }


def build_public_image_url(post: dict) -> str | None:
    image_url = (post.get("image_url") or "").strip()
    if image_url.startswith(("http://", "https://")):
        return image_url
    if image_url.startswith("/assets"):
        public_asset_base_url = os.getenv("PUBLIC_ASSET_BASE_URL")
        if public_asset_base_url:
            return public_asset_base_url.rstrip("/") + image_url
        # TODO: Later use Cloudinary/S3/static public host/ngrok only for testing.
        return None
    return None


def meta_graph_version() -> str:
    return os.getenv("META_GRAPH_VERSION", DEFAULT_META_GRAPH_VERSION).strip() or DEFAULT_META_GRAPH_VERSION


def publish_post(post: dict, platform: str) -> dict:
    normalized = (platform or "").strip().lower()
    if normalized not in ALLOWED_PLATFORMS:
        return {"success": False, "error": "Unsupported platform"}

    if not is_real_publishing_enabled():
        return mock_result(post, normalized)

    if normalized == "facebook":
        return publish_to_facebook(post)
    if normalized == "instagram":
        return publish_to_instagram(post)
    return publish_to_x(post)


def publish_to_facebook(post: dict) -> dict:
    platform = "facebook"
    missing = missing_env(["META_PAGE_ID", "META_PAGE_ACCESS_TOKEN"])
    if missing:
        return missing_config_result(platform, missing)

    page_id = os.getenv("META_PAGE_ID")
    token = os.getenv("META_PAGE_ACCESS_TOKEN")
    version = meta_graph_version()
    content = post.get("content") or ""
    public_image_url = build_public_image_url(post)

    if public_image_url:
        url = f"https://graph.facebook.com/{version}/{page_id}/photos"
        data = {
            "url": public_image_url,
            "caption": content,
            "access_token": token,
        }
    else:
        url = f"https://graph.facebook.com/{version}/{page_id}/feed"
        data = {
            "message": content,
            "access_token": token,
        }

    try:
        response = requests.post(url, data=data, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        return {
            "success": False,
            "mode": "real",
            "platform": platform,
            "error": redact_secrets(str(exc)),
        }

    if not response.ok:
        result = api_error(response)
        result["platform"] = platform
        return result

    data = response.json()
    platform_post_id = data.get("post_id") or data.get("id")
    return {
        "success": True,
        "mode": "real",
        "platform": platform,
        "message": "Facebook publish successful.",
        "post_id": post["id"],
        "platform_post_id": platform_post_id,
    }


def publish_to_instagram(post: dict) -> dict:
    platform = "instagram"
    missing = missing_env(["INSTAGRAM_BUSINESS_ACCOUNT_ID", "META_PAGE_ACCESS_TOKEN"])
    if missing:
        return missing_config_result(platform, missing)

    public_image_url = build_public_image_url(post)
    if not public_image_url:
        return {
            "success": False,
            "mode": "real",
            "platform": platform,
            "error": "Instagram real publishing requires a publicly reachable image_url.",
        }

    ig_user_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    token = os.getenv("META_PAGE_ACCESS_TOKEN")
    version = meta_graph_version()
    content = post.get("content") or ""

    media_url = f"https://graph.facebook.com/{version}/{ig_user_id}/media"
    media_data = {
        "image_url": public_image_url,
        "caption": content,
        "access_token": token,
    }

    try:
        media_response = requests.post(media_url, data=media_data, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        return {
            "success": False,
            "mode": "real",
            "platform": platform,
            "error": redact_secrets(str(exc)),
        }

    if not media_response.ok:
        result = api_error(media_response)
        result["platform"] = platform
        return result

    media_result = media_response.json()
    creation_id = media_result.get("id")
    if not creation_id:
        return {
            "success": False,
            "mode": "real",
            "platform": platform,
            "error": "Instagram media container creation did not return a creation_id.",
        }

    publish_url = f"https://graph.facebook.com/{version}/{ig_user_id}/media_publish"
    publish_data = {
        "creation_id": creation_id,
        "access_token": token,
    }

    try:
        publish_response = requests.post(publish_url, data=publish_data, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        return {
            "success": False,
            "mode": "real",
            "platform": platform,
            "error": redact_secrets(str(exc)),
        }

    if not publish_response.ok:
        result = api_error(publish_response)
        result["platform"] = platform
        return result

    publish_result = publish_response.json()
    return {
        "success": True,
        "mode": "real",
        "platform": platform,
        "message": "Instagram publish successful.",
        "post_id": post["id"],
        "platform_post_id": publish_result.get("id"),
    }


def truncate_x_text(text: str) -> str:
    text = " ".join((text or "").split())
    if len(text) <= 280:
        return text
    return text[:279].rstrip() + "…"


def publish_to_x(post: dict) -> dict:
    platform = "x"
    missing = missing_env(["X_BEARER_USER_TOKEN"])
    if missing:
        return missing_config_result(platform, missing)

    token = os.getenv("X_BEARER_USER_TOKEN")
    text = truncate_x_text(post.get("content") or "")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"text": text}

    try:
        response = requests.post(
            "https://api.x.com/2/tweets",
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        return {
            "success": False,
            "mode": "real",
            "platform": platform,
            "error": redact_secrets(str(exc)),
        }

    if not response.ok:
        result = api_error(response)
        result["platform"] = platform
        return result

    data = response.json()
    tweet_id = (data.get("data") or {}).get("id")
    return {
        "success": True,
        "mode": "real",
        "platform": platform,
        "message": "X publish successful.",
        "post_id": post["id"],
        "platform_post_id": tweet_id,
    }
