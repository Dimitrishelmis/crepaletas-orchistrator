from pathlib import Path

BASE_DIR = Path("/home/dimitris/marketing-orchestrator").resolve()
LOG_DIR = BASE_DIR / "logs"
REPORT_DIR = BASE_DIR / "reports"
WORKSPACE_DIR = BASE_DIR / "workspace"
DATA_DIR = BASE_DIR / "data"
MEMORY_DIR = BASE_DIR / "memory"

ALLOWED_TELEGRAM_USER_ID = 7110687355

for folder in [LOG_DIR, REPORT_DIR, WORKSPACE_DIR, DATA_DIR, MEMORY_DIR]:
    folder.mkdir(parents=True, exist_ok=True)


def is_allowed_telegram_user(user_id: int) -> bool:
    return user_id == ALLOWED_TELEGRAM_USER_ID


def safe_path(base_folder: Path, filename: str) -> Path:
    """
    Prevents path traversal like ../../.ssh/id_rsa
    """
    base_folder = base_folder.resolve()
    target = (base_folder / filename).resolve()

    if not str(target).startswith(str(base_folder)):
        raise ValueError("Unsafe file path blocked.")

    return target
