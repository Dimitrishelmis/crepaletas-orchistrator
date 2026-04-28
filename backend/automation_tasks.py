import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from security import BASE_DIR, DATA_DIR, REPORT_DIR, safe_path


TASKS_FILE = DATA_DIR / "automation_tasks.json"
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"
PIP_PYTHON = BACKEND_DIR / ".venv" / "bin" / "python"
SAFE_PIP_SPEC = re.compile(r"^[A-Za-z0-9_.-]+([<>=!~]=?[A-Za-z0-9*_.!+\-]+)?$")
SAFE_NPM_SPEC = re.compile(r"^(@[A-Za-z0-9_.-]+/)?[A-Za-z0-9_.-]+$")
SAFE_GITHUB_SPEC = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ALLOWED_CODE_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".yml",
    ".yaml",
}
BLOCKED_PATH_PARTS = {".git", ".venv", "__pycache__", ".ssh", "node_modules"}
BLOCKED_FILENAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519"}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_tasks() -> list[dict]:
    if not TASKS_FILE.exists():
        return []
    try:
        return json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_tasks(tasks: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")


def next_task_id(tasks: list[dict]) -> int:
    return max((task.get("id", 0) for task in tasks), default=0) + 1


def get_task(task_id: int) -> dict | None:
    return next((task for task in load_tasks() if task.get("id") == task_id), None)


def validate_pip_package(package: str) -> str | None:
    package = (package or "").strip()
    if not package or package.startswith("-") or "/" in package or "\\" in package:
        return None
    return package if SAFE_PIP_SPEC.fullmatch(package) else None


def validate_npm_package(package: str) -> str | None:
    package = (package or "").strip()
    if not package or package.startswith("-") or "\\" in package:
        return None
    return package if SAFE_NPM_SPEC.fullmatch(package) else None


def validate_github_repo(repo: str) -> str | None:
    repo = (repo or "").strip()
    if repo.startswith(("http://", "https://", "git@", "-")):
        return None
    return repo if SAFE_GITHUB_SPEC.fullmatch(repo) else None


def resolve_safe_project_file(relative_path: str) -> Path | None:
    relative_path = (relative_path or "").strip().lstrip("/")
    if not relative_path or "\x00" in relative_path:
        return None

    target = (BASE_DIR / relative_path).resolve()
    base = BASE_DIR.resolve()
    if not str(target).startswith(str(base)):
        return None
    if any(part in BLOCKED_PATH_PARTS for part in target.parts):
        return None
    if target.name in BLOCKED_FILENAMES:
        return None
    if target.suffix.lower() not in ALLOWED_CODE_EXTENSIONS:
        return None
    return target


def create_install_task(kind: str, package: str) -> dict:
    if kind == "pip":
        safe_package = validate_pip_package(package)
        command_preview = f"python -m pip install {safe_package}" if safe_package else ""
    elif kind == "pip_github":
        safe_package = validate_github_repo(package)
        command_preview = f"python -m pip install git+https://github.com/{safe_package}.git" if safe_package else ""
    elif kind == "npm":
        safe_package = validate_npm_package(package)
        command_preview = f"npm install {safe_package}" if safe_package else ""
    else:
        return {"created": False, "error": "Unsupported task type."}

    if not safe_package:
        return {"created": False, "error": "Package name is not allowed."}

    tasks = load_tasks()
    task = {
        "id": next_task_id(tasks),
        "created_at": now(),
        "approved_at": None,
        "ran_at": None,
        "type": "pip_github_install" if kind == "pip_github" else f"{kind}_install",
        "package": safe_package,
        "status": "pending",
        "command_preview": command_preview,
        "report_file": None,
        "result": None,
    }
    tasks.append(task)
    save_tasks(tasks)
    return {"created": True, "task": task}


def create_code_write_task(relative_path: str, content: str) -> dict:
    target = resolve_safe_project_file(relative_path)
    if not target:
        return {"created": False, "error": "File path is not allowed."}
    if content is None or len(content) > 50000:
        return {"created": False, "error": "Content is empty or too large."}

    tasks = load_tasks()
    task = {
        "id": next_task_id(tasks),
        "created_at": now(),
        "approved_at": None,
        "ran_at": None,
        "type": "code_write",
        "path": str(target.relative_to(BASE_DIR)),
        "content": content,
        "status": "pending",
        "command_preview": f"write file {target.relative_to(BASE_DIR)}",
        "report_file": None,
        "result": None,
    }
    tasks.append(task)
    save_tasks(tasks)
    return {"created": True, "task": task}


def create_code_replace_task(relative_path: str, find_text: str, replace_text: str) -> dict:
    target = resolve_safe_project_file(relative_path)
    if not target:
        return {"created": False, "error": "File path is not allowed."}
    if not target.exists():
        return {"created": False, "error": "File does not exist."}
    if not find_text or len(find_text) > 20000 or len(replace_text or "") > 20000:
        return {"created": False, "error": "Find/replace text is empty or too large."}

    tasks = load_tasks()
    task = {
        "id": next_task_id(tasks),
        "created_at": now(),
        "approved_at": None,
        "ran_at": None,
        "type": "code_replace",
        "path": str(target.relative_to(BASE_DIR)),
        "find": find_text,
        "replace": replace_text or "",
        "status": "pending",
        "command_preview": f"replace text in {target.relative_to(BASE_DIR)}",
        "report_file": None,
        "result": None,
    }
    tasks.append(task)
    save_tasks(tasks)
    return {"created": True, "task": task}


def list_tasks(limit: int = 10) -> dict:
    tasks = sorted(load_tasks(), key=lambda task: task.get("id", 0), reverse=True)
    return {"tasks": tasks[:limit]}


def approve_task(task_id: int) -> dict:
    tasks = load_tasks()
    for task in tasks:
        if task.get("id") == task_id:
            if task.get("status") not in {"pending", "approved"}:
                return {"success": False, "error": f"Task is {task.get('status')} and cannot be approved."}
            task["status"] = "approved"
            task["approved_at"] = now()
            save_tasks(tasks)
            return {"success": True, "task": task}
    return {"success": False, "error": "Task not found."}


def command_for_task(task: dict) -> tuple[list[str] | None, Path | None, str | None]:
    if task.get("type") == "pip_install":
        if not PIP_PYTHON.exists():
            return None, None, "Backend virtualenv python was not found."
        return [
            str(PIP_PYTHON),
            "-m",
            "pip",
            "install",
            task["package"],
        ], BACKEND_DIR, None

    if task.get("type") == "pip_github_install":
        if not PIP_PYTHON.exists():
            return None, None, "Backend virtualenv python was not found."
        return [
            str(PIP_PYTHON),
            "-m",
            "pip",
            "install",
            f"git+https://github.com/{task['package']}.git",
        ], BACKEND_DIR, None

    if task.get("type") == "npm_install":
        package_json = FRONTEND_DIR / "package.json"
        if not package_json.exists():
            return None, None, "Frontend package.json was not found. Create the frontend app first."
        return ["npm", "install", task["package"]], FRONTEND_DIR, None

    return None, None, "Unsupported task type."


def write_task_report(task: dict, output: str) -> str:
    filename = f"automation_task_{task['id']}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
    path = safe_path(REPORT_DIR, filename)
    path.write_text(output, encoding="utf-8")
    return str(path)


def run_code_task(task: dict) -> dict:
    target = resolve_safe_project_file(task.get("path", ""))
    if not target:
        return {"success": False, "error": "File path is not allowed."}

    if task.get("type") == "code_write":
        target.parent.mkdir(parents=True, exist_ok=True)
        old_content = target.read_text(encoding="utf-8") if target.exists() else ""
        target.write_text(task.get("content", ""), encoding="utf-8")
        summary = f"Wrote {target.relative_to(BASE_DIR)}."
        report = (
            f"Task #{task['id']}\n"
            f"Action: code_write\n"
            f"File: {target}\n"
            f"Old length: {len(old_content)}\n"
            f"New length: {len(task.get('content', ''))}\n"
        )
        return {"success": True, "summary": summary, "report": report}

    if task.get("type") == "code_replace":
        content = target.read_text(encoding="utf-8")
        find_text = task.get("find", "")
        if find_text not in content:
            return {"success": False, "error": "Find text was not found in file."}
        updated = content.replace(find_text, task.get("replace", ""), 1)
        target.write_text(updated, encoding="utf-8")
        summary = f"Updated {target.relative_to(BASE_DIR)}."
        report = (
            f"Task #{task['id']}\n"
            f"Action: code_replace\n"
            f"File: {target}\n"
            f"Old length: {len(content)}\n"
            f"New length: {len(updated)}\n"
        )
        return {"success": True, "summary": summary, "report": report}

    return {"success": False, "error": "Unsupported code task type."}


def run_task(task_id: int) -> dict:
    tasks = load_tasks()
    task = next((item for item in tasks if item.get("id") == task_id), None)
    if not task:
        return {"success": False, "error": "Task not found."}
    if task.get("status") != "approved":
        return {"success": False, "error": "Task must be approved before running."}

    if task.get("type") in {"code_write", "code_replace"}:
        result = run_code_task(task)
        task["ran_at"] = now()
        if result.get("success"):
            report_file = write_task_report(task, result["report"])
            task["report_file"] = report_file
            task["status"] = "completed"
            task["result"] = result["summary"]
            save_tasks(tasks)
            return {"success": True, "task": task, "report_file": report_file, "summary": result["summary"]}

        task["status"] = "failed"
        task["result"] = result.get("error")
        save_tasks(tasks)
        return {"success": False, "error": result.get("error"), "task": task}

    command, cwd, error = command_for_task(task)
    if error:
        task["status"] = "failed"
        task["result"] = error
        save_tasks(tasks)
        return {"success": False, "error": error, "task": task}

    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = (
            f"Task #{task['id']}\n"
            f"Command: {task['command_preview']}\n"
            f"Return code: {result.returncode}\n\n"
            f"STDOUT:\n{result.stdout[-8000:]}\n\n"
            f"STDERR:\n{result.stderr[-8000:]}\n"
        )
        report_file = write_task_report(task, output)
        task["ran_at"] = now()
        task["report_file"] = report_file
        task["status"] = "completed" if result.returncode == 0 else "failed"
        task["result"] = "Package install completed." if result.returncode == 0 else "Package install failed."
        save_tasks(tasks)
        return {
            "success": result.returncode == 0,
            "task": task,
            "report_file": report_file,
            "summary": task["result"],
        }
    except subprocess.TimeoutExpired:
        task["status"] = "failed"
        task["result"] = "Package install timed out."
        save_tasks(tasks)
        return {"success": False, "error": task["result"], "task": task}
