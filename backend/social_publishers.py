ENABLE_REAL_PUBLISHING = False
ALLOWED_PLATFORMS = {"instagram", "facebook", "x"}


def real_publishing_enabled() -> bool:
    return ENABLE_REAL_PUBLISHING


def _mock_result(post: dict, platform: str):
    return {
        "success": True,
        "mode": "mock",
        "platform": platform,
        "message": "Mock publish successful. No real post was sent.",
        "post_id": post["id"],
    }


def publish_to_instagram(post):
    if not real_publishing_enabled():
        return _mock_result(post, "instagram")

    # TODO: Use the official Meta Graph API for Instagram publishing.
    return {
        "success": False,
        "platform": "instagram",
        "mode": "real",
        "message": "Instagram official API publishing is not implemented yet.",
    }


def publish_to_facebook(post):
    if not real_publishing_enabled():
        return _mock_result(post, "facebook")

    # TODO: Use the official Meta Graph API for Facebook Page publishing.
    return {
        "success": False,
        "platform": "facebook",
        "mode": "real",
        "message": "Facebook Page official API publishing is not implemented yet.",
    }


def publish_to_x(post):
    if not real_publishing_enabled():
        return _mock_result(post, "x")

    # TODO: Use the official X API for X/Twitter publishing.
    return {
        "success": False,
        "platform": "x",
        "mode": "real",
        "message": "X official API publishing is not implemented yet.",
    }


def publish_post(post, platform: str):
    normalized = platform.strip().lower()
    if normalized not in ALLOWED_PLATFORMS:
        return {
            "success": False,
            "error": "Unsupported platform",
        }

    if normalized == "instagram":
        return publish_to_instagram(post)
    if normalized == "facebook":
        return publish_to_facebook(post)
    return publish_to_x(post)
