from datetime import datetime
from pathlib import Path

from db import get_generated_post, list_generated_posts
from security import BASE_DIR, REPORT_DIR, MEMORY_DIR, safe_path


AI_LOG_DIR = Path("/home/dimitris/ai-orchestrator/logs").resolve()
ERROR_TERMS = ("error", "failed", "exception", "traceback", "not found", "timeout")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ASSETS_IMAGES_DIR = BASE_DIR / "assets" / "images"


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def write_report(filename: str, content: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    file_path = safe_path(REPORT_DIR, filename)
    file_path.write_text(content, encoding="utf-8")
    return file_path


def preview(text: str, limit: int = 900) -> str:
    compact = "\n".join(line.rstrip() for line in text.strip().splitlines() if line.strip())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def scan_logs_and_summarize() -> dict:
    log_dirs = [BASE_DIR / "logs", AI_LOG_DIR]
    matches = []

    for log_dir in log_dirs:
        if not log_dir.exists():
            continue
        files = sorted(
            (path for path in log_dir.iterdir() if path.is_file() and path.suffix.lower() in {".txt", ".log"}),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in files[:20]:
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines[-400:]:
                if any(term in line.lower() for term in ERROR_TERMS):
                    matches.append(f"{path}: {line.strip()}")
                    if len(matches) >= 60:
                        break
            if len(matches) >= 60:
                break

    summary = "Latest log issues\n\n" + ("\n".join(matches) if matches else "No recent error-like lines found.")
    file_path = write_report(f"error_summary_{timestamp()}.txt", summary)
    return {"created": True, "file": str(file_path), "summary": preview(summary)}


def create_weekly_campaign_report() -> dict:
    posts = list_generated_posts(limit=100)
    counts = {
        "total": len(posts),
        "draft": 0,
        "approved": 0,
        "published_mock": 0,
        "failed_rejected": 0,
    }

    for post in posts:
        status = (post.get("status") or "").lower()
        if status == "draft":
            counts["draft"] += 1
        elif status == "approved":
            counts["approved"] += 1
        elif status in {"published", "published_mock"}:
            counts["published_mock"] += 1
        elif status in {"failed", "rejected"}:
            counts["failed_rejected"] += 1

    latest = [
        f"#{post.get('id')} | {post.get('status')} | {post.get('topic')} | {post.get('provider') or 'unknown'}"
        for post in posts[:10]
    ]

    summary = (
        "Weekly campaign report\n\n"
        f"Total posts: {counts['total']}\n"
        f"Draft posts: {counts['draft']}\n"
        f"Approved posts: {counts['approved']}\n"
        f"Published/mock-published posts: {counts['published_mock']}\n"
        f"Failed/rejected posts: {counts['failed_rejected']}\n\n"
        "Latest 10 posts:\n"
        + ("\n".join(latest) if latest else "No generated posts found.")
    )
    file_path = write_report(f"weekly_campaign_report_{timestamp()}.txt", summary)
    return {"created": True, "file": str(file_path), "summary": preview(summary)}


def image_category(filename: str) -> str:
    name = filename.lower()
    keyword_map = {
        "kids_party": ("kids", "party", "children", "birthday", "παιδ"),
        "wedding": ("wedding", "γάμος", "γαμ"),
        "baptism": ("baptism", "βάπτιση", "βαπτισ"),
        "school": ("school", "σχολ"),
        "festival": ("festival", "food", "πανηγ", "φεστιβάλ"),
        "sweet": ("sweet", "γλυκ"),
        "savory": ("savory", "αλμυρ"),
    }
    for category, words in keyword_map.items():
        if any(word in name for word in words):
            return category
    return "uncategorized"


def organize_campaign_assets_report_only() -> dict:
    groups = {
        "kids_party": [],
        "wedding": [],
        "baptism": [],
        "school": [],
        "festival": [],
        "sweet": [],
        "savory": [],
        "uncategorized": [],
    }

    if ASSETS_IMAGES_DIR.exists():
        for path in sorted(ASSETS_IMAGES_DIR.iterdir()):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                groups[image_category(path.name)].append(path.name)

    lines = ["Campaign assets organization report", "", "No files were moved.", ""]
    for category, filenames in groups.items():
        lines.append(f"{category}: {len(filenames)}")
        lines.extend(f"  - {filename}" for filename in filenames[:30])
        lines.append("")

    summary = "\n".join(lines)
    file_path = write_report(f"assets_organization_report_{timestamp()}.txt", summary)
    return {"created": True, "file": str(file_path), "summary": preview(summary)}


def greek_quality_check(post_id: int) -> dict:
    post = get_generated_post(post_id)
    if not post:
        return {"created": False, "file": None, "summary": "Post not found."}

    content = post.get("content") or ""
    greek_letters = sum(1 for ch in content if "α" <= ch.lower() <= "ω")
    latin_letters = sum(1 for ch in content if "a" <= ch.lower() <= "z")
    total_letters = sum(1 for ch in content if ch.isalpha())
    greek_ratio = greek_letters / total_letters if total_letters else 0
    hashtag_count = content.count("#")
    cta_terms = ("στείλ", "κλεί", "επικοιν", "μάθε", "παράγγει", "κάνε", "ζητή", "ρωτή", "dm")

    issues = []
    if len(content) > 700:
        issues.append("Content may be too long.")
    if greek_ratio < 0.45:
        issues.append("Greek character ratio is low.")
    if hashtag_count > 6:
        issues.append("Too many hashtags.")
    if latin_letters > greek_letters:
        issues.append("Text appears English-heavy.")
    if not any(term in content.lower() for term in cta_terms):
        issues.append("Missing CTA-like phrase.")

    summary = (
        f"Greek quality check for post #{post_id}\n\n"
        f"Greek ratio: {greek_ratio:.2f}\n"
        f"Hashtags: {hashtag_count}\n"
        f"Length: {len(content)} characters\n\n"
        "Issues:\n"
        + ("\n".join(f"- {issue}" for issue in issues) if issues else "- No obvious issues found.")
        + "\n\nContent preview:\n"
        + preview(content, limit=600)
    )
    file_path = write_report(f"greek_quality_post_{post_id}_{timestamp()}.txt", summary)
    return {"created": True, "file": str(file_path), "summary": preview(summary)}


def safe_memory_category(category: str | None) -> str:
    category = (category or "campaigns").strip().lower()
    if not category.replace("_", "").replace("-", "").isalnum():
        return "campaigns"
    folder = (MEMORY_DIR / category).resolve()
    if not str(folder).startswith(str(MEMORY_DIR.resolve())):
        return "campaigns"
    return category


def extract_topic_from_memory(content: str, fallback: str) -> str:
    in_frontmatter = False
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter or not line:
            continue
        line = line.lstrip("#-* ").strip()
        if line:
            return line[:140]
    return fallback


def prepare_batch_posts_from_memory(category: str = "campaigns", limit: int = 5) -> dict:
    category = safe_memory_category(category)
    if limit < 1:
        limit = 5

    memory_dir = MEMORY_DIR / category
    memory_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(memory_dir.glob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True)[:limit]

    topics = []
    for path in files:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        topics.append(f"- {extract_topic_from_memory(content, path.stem)} ({path.name})")

    summary = (
        f"Batch post planning report\n\n"
        f"Memory category: {category}\n"
        f"Notes reviewed: {len(files)}\n\n"
        "Suggested topics:\n"
        + ("\n".join(topics) if topics else "No memory notes found for this category.")
    )
    file_path = write_report(f"batch_post_plan_{timestamp()}.txt", summary)
    return {"created": True, "file": str(file_path), "summary": preview(summary)}
