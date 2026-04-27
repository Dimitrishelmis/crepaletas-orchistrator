from datetime import datetime
from pathlib import Path

from security import MEMORY_DIR, safe_path


ALLOWED_CATEGORIES = {"daily", "projects", "customers", "ideas", "campaigns", "errors"}
PREVIEW_LENGTH = 220


def ensure_memory_folders():
    for category in ALLOWED_CATEGORIES:
        (MEMORY_DIR / category).mkdir(parents=True, exist_ok=True)


def normalize_category(category: str | None) -> str:
    if not category:
        return "daily"

    category = category.strip().lower()
    return category if category in ALLOWED_CATEGORIES else "daily"


def build_preview(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= PREVIEW_LENGTH:
        return compact
    return compact[:PREVIEW_LENGTH].rstrip() + "..."


def memory_item_from_file(path: Path) -> dict:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = path.read_text(encoding="utf-8", errors="replace")

    return {
        "filename": path.name,
        "category": path.parent.name,
        "file": str(path),
        "preview": build_preview(content),
    }


def iter_memory_files():
    ensure_memory_folders()
    for category in sorted(ALLOWED_CATEGORIES):
        folder = MEMORY_DIR / category
        yield from folder.glob("*.md")


def add_memory(content: str, category: str = "daily", tags: list[str] | None = None) -> dict:
    ensure_memory_folders()
    category = normalize_category(category)
    tags = tags or []

    timestamp = datetime.now().isoformat(timespec="seconds")
    filename_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    filename = f"memory_{filename_timestamp}.md"
    file_path = safe_path(MEMORY_DIR / category, filename)

    frontmatter = (
        "---\n"
        "type: memory\n"
        f"category: {category}\n"
        f"created: {timestamp}\n"
        f"tags: {tags}\n"
        "---\n\n"
    )

    file_path.write_text(frontmatter + content.strip() + "\n", encoding="utf-8")

    return {
        "created": True,
        "file": str(file_path),
        "filename": file_path.name,
        "category": category,
        "content": content,
    }


def search_memory(query: str, limit: int = 10) -> dict:
    query = (query or "").strip().lower()
    if limit < 1:
        limit = 10

    matches = []
    if query:
        for path in iter_memory_files():
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_text(encoding="utf-8", errors="replace")

            if query in content.lower():
                matches.append(memory_item_from_file(path))
                if len(matches) >= limit:
                    break

    return {
        "query": query,
        "matches": matches,
    }


def recent_memory(limit: int = 10) -> dict:
    if limit < 1:
        limit = 10

    files = sorted(
        iter_memory_files(),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    return {
        "memories": [memory_item_from_file(path) for path in files[:limit]],
    }
