import json
import os
from datetime import datetime
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from security import BASE_DIR, LOG_DIR, REPORT_DIR, WORKSPACE_DIR
from db import (
    init_db,
    list_generated_posts,
    get_generated_post,
    save_log,
    update_post_status,
    approve_post as approve_post_record,
    reject_post as reject_post_record,
    publish_post_record,
)
from agents import check_ollama, check_openclaw, openclaw_status
from marketing import generate_marketing_post
from memory_store import add_memory, search_memory, recent_memory
from openclaw_tasks import (
    scan_logs_and_summarize,
    create_weekly_campaign_report,
    organize_campaign_assets_report_only,
    greek_quality_check,
    prepare_batch_posts_from_memory,
)
from automation_tasks import (
    create_install_task,
    create_code_write_task,
    create_code_replace_task,
    list_tasks as list_automation_tasks,
    get_task as get_automation_task,
    approve_task as approve_automation_task,
    run_task as run_automation_task,
)
from social_publishers import ALLOWED_PLATFORMS, publish_post, real_publishing_enabled
from pathlib import Path

ASSETS_DIR = Path("/home/dimitris/marketing-orchestrator/assets").resolve()
IMAGES_DIR = ASSETS_DIR / "images"
app = FastAPI(title="Marketing Orchestrator")

app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

class PostRequest(BaseModel):
    topic: str
    platform: str = "Instagram"
    language: str = "Greek"


class LogRequest(BaseModel):
    source: str = "manual"
    message: str


class PublishRequest(BaseModel):
    platform: str = "instagram"


class MemoryAddRequest(BaseModel):
    content: str
    category: str = "daily"
    tags: list[str] = []


class MemorySearchRequest(BaseModel):
    query: str
    limit: int = 10


class InstallTaskRequest(BaseModel):
    package: str


class CodeWriteTaskRequest(BaseModel):
    path: str
    content: str


class CodeReplaceTaskRequest(BaseModel):
    path: str
    find: str
    replace: str


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def home():
    return {
        "message": "Marketing Orchestrator is running",
        "status_url": "/status",
        "docs_url": "/docs"
    }


def build_status():
    data = {
        "backend": "running",
        "time": datetime.now().isoformat(timespec="seconds"),
        "base_dir": str(BASE_DIR),
        "logs_dir_exists": LOG_DIR.exists(),
        "reports_dir_exists": REPORT_DIR.exists(),
        "workspace_dir_exists": WORKSPACE_DIR.exists(),
        "ollama": "unknown",
        "ollama_models": [],
        "openai_fallback": "configured" if os.getenv("OPENAI_API_KEY") else "not configured",
        "openclaw": "unknown",
        "real_publishing_enabled": real_publishing_enabled(),
        "allowed_publish_platforms": sorted(ALLOWED_PLATFORMS),
    }

    try:
        models = check_ollama()
        data["ollama"] = "reachable"
        data["ollama_models"] = models
    except Exception as e:
        data["ollama"] = f"not reachable: {e}"

    try:
        openclaw = check_openclaw()
        data["openclaw"] = "reachable" if openclaw["returncode"] == 0 else "error"
    except FileNotFoundError:
        data["openclaw"] = "not found"
    except Exception as e:
        data["openclaw"] = f"error: {e}"

    return data


@app.get("/status")
def status():
    return build_status()


@app.get("/api/status")
def api_status():
    return build_status()


@app.post("/log")
def create_log(request: LogRequest):
    log_id = save_log(request.source, request.message)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_path = LOG_DIR / f"log_{timestamp}.txt"

    file_path.write_text(
        f"Source: {request.source}\nMessage: {request.message}\n",
        encoding="utf-8"
    )

    return {
        "created": True,
        "id": log_id,
        "file": str(file_path)
    }


@app.post("/memory/add")
def memory_add(request: MemoryAddRequest):
    return add_memory(
        content=request.content,
        category=request.category,
        tags=request.tags,
    )


@app.post("/memory/search")
def memory_search(request: MemorySearchRequest):
    return search_memory(
        query=request.query,
        limit=request.limit,
    )


@app.get("/memory/recent")
def memory_recent(limit: int = 10):
    return recent_memory(limit=limit)


@app.post("/generate-post")
def generate_post(request: PostRequest):
    try:
        return generate_marketing_post(
            topic=request.topic,
            platform=request.platform,
            language=request.language
        )
    except Exception as e:
        save_log("generate_post_error", str(e))
        return {
            "created": False,
            "error": str(e)
        }


@app.get("/posts")
def posts():
    return {
        "posts": list_generated_posts()
    }


@app.get("/api/posts")
def api_posts():
    return {
        "posts": list_generated_posts()
    }


@app.get("/posts/{post_id}")
def post_detail(post_id: int):
    post = get_generated_post(post_id)

    if not post:
        return {
            "found": False,
            "error": "Post not found"
        }

    return {
        "found": True,
        "post": post
    }


@app.get("/api/posts/{post_id}")
def api_post_detail(post_id: int):
    post = get_generated_post(post_id)

    if not post:
        return {
            "found": False,
            "error": "Post not found"
        }

    return {
        "found": True,
        "post": post
    }


@app.post("/api/posts/{post_id}/approve")
def approve_post(post_id: int):
    post = get_generated_post(post_id)
    if not post:
        return {"success": False, "error": "Post not found"}

    updated_post = approve_post_record(post_id)
    return {"success": True, "post": updated_post}


@app.post("/api/posts/{post_id}/reject")
def reject_post(post_id: int):
    post = get_generated_post(post_id)
    if not post:
        return {"success": False, "error": "Post not found"}

    updated_post = reject_post_record(post_id)
    return {"success": True, "post": updated_post}


@app.post("/api/posts/{post_id}/schedule")
def schedule_post(post_id: int):
    post = get_generated_post(post_id)
    if not post:
        return {"success": False, "error": "Post not found"}
    if post.get("status") != "approved":
        return {"success": False, "error": "Post must be approved before scheduling."}

    update_post_status(post_id, "scheduled")
    return {"success": True, "post": get_generated_post(post_id)}


@app.post("/api/posts/{post_id}/regenerate")
def regenerate_post(post_id: int):
    post = get_generated_post(post_id)
    if not post:
        return {"success": False, "error": "Post not found"}

    try:
        regenerated = generate_marketing_post(
            topic=post["topic"],
            platform=post["platform"],
            language=post["language"],
        )
        return {"success": True, "regenerated": regenerated}
    except Exception as e:
        save_log("regenerate_post_error", str(e))
        return {"success": False, "error": str(e)}


@app.post("/api/posts/{post_id}/publish")
def publish_generated_post(post_id: int, request: PublishRequest):
    post = get_generated_post(post_id)
    if not post:
        return {"success": False, "error": "Post not found"}
    if post.get("status") != "approved":
        return {"success": False, "error": "Post must be approved before publishing."}

    platform = request.platform.strip().lower()
    if platform not in ALLOWED_PLATFORMS:
        return {"success": False, "error": "Target platform is not allowed."}

    result = publish_post(post, platform)
    publish_result_json = json.dumps(result, ensure_ascii=False)
    if result.get("success"):
        publish_status = "published" if result.get("mode") == "real" else "published_mock"
        updated_post = publish_post_record(
            post_id,
            platform,
            publish_result_json,
            status=publish_status,
        )
    else:
        update_post_status(
            post_id,
            "publish_failed",
            target_platform=platform,
            publish_result=publish_result_json,
        )
        updated_post = get_generated_post(post_id)

    return {
        "success": result.get("success", False),
        "result": result,
        "post_id": post_id,
        "platform": platform,
        "mode": result.get("mode"),
        "message": result.get("message") or result.get("error"),
        "status": updated_post.get("status") if updated_post else None,
        "post": updated_post,
    }


@app.get("/api/images")
def api_images():
    images = []
    if IMAGES_DIR.exists():
        for image in sorted(IMAGES_DIR.iterdir()):
            if image.is_file() and image.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                images.append({
                    "image_file": image.name,
                    "image_url": f"http://127.0.0.1:8000/assets/images/{image.name}",
                })

    return {"images": images}


@app.get("/openclaw/status")
def get_openclaw_status():
    try:
        return openclaw_status()
    except FileNotFoundError:
        return {
            "error": "OpenClaw command not found"
        }
    except Exception as e:
        save_log("openclaw_status_error", str(e))
        return {
            "error": str(e)
        }


@app.get("/openclaw/tasks/scan-logs")
def openclaw_task_scan_logs():
    return scan_logs_and_summarize()


@app.get("/openclaw/tasks/weekly-report")
def openclaw_task_weekly_report():
    return create_weekly_campaign_report()


@app.get("/openclaw/tasks/assets-report")
def openclaw_task_assets_report():
    return organize_campaign_assets_report_only()


@app.get("/openclaw/tasks/greek-quality/{post_id}")
def openclaw_task_greek_quality(post_id: int):
    return greek_quality_check(post_id)


@app.get("/openclaw/tasks/batch-posts/{category}")
def openclaw_task_batch_posts(category: str):
    return prepare_batch_posts_from_memory(category=category)


@app.post("/automation/tasks/pip")
def create_pip_install_task(request: InstallTaskRequest):
    return create_install_task("pip", request.package)


@app.post("/automation/tasks/pip-github")
def create_pip_github_install_task(request: InstallTaskRequest):
    return create_install_task("pip_github", request.package)


@app.post("/automation/tasks/npm")
def create_npm_install_task(request: InstallTaskRequest):
    return create_install_task("npm", request.package)


@app.post("/automation/tasks/code-write")
def create_code_write_endpoint(request: CodeWriteTaskRequest):
    return create_code_write_task(request.path, request.content)


@app.post("/automation/tasks/code-replace")
def create_code_replace_endpoint(request: CodeReplaceTaskRequest):
    return create_code_replace_task(request.path, request.find, request.replace)


@app.get("/automation/tasks")
def automation_tasks(limit: int = 10):
    return list_automation_tasks(limit=limit)


@app.get("/automation/tasks/{task_id}")
def automation_task_detail(task_id: int):
    task = get_automation_task(task_id)
    if not task:
        return {"found": False, "error": "Task not found."}
    return {"found": True, "task": task}


@app.post("/automation/tasks/{task_id}/approve")
def approve_task_endpoint(task_id: int):
    return approve_automation_task(task_id)


@app.post("/automation/tasks/{task_id}/run")
def run_task_endpoint(task_id: int):
    return run_automation_task(task_id)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Marketing Orchestrator Dashboard</title>
  <style>
    :root { color-scheme: light; font-family: Arial, sans-serif; }
    body { margin: 0; background: #f6f7f9; color: #1f2933; }
    header { background: #213547; color: white; padding: 18px 24px; }
    header h1 { margin: 0; font-size: 22px; letter-spacing: 0; }
    main { max-width: 1180px; margin: 0 auto; padding: 20px; }
    .status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }
    .status-box, .panel, .post-row { background: white; border: 1px solid #d9e0e7; border-radius: 8px; }
    .status-box { padding: 12px; }
    .label { color: #667085; font-size: 12px; text-transform: uppercase; }
    .value { margin-top: 6px; font-weight: 700; overflow-wrap: anywhere; }
    .layout { display: grid; grid-template-columns: minmax(260px, 420px) 1fr; gap: 16px; margin-top: 18px; }
    .panel { padding: 14px; min-width: 0; }
    .panel h2 { margin: 0 0 12px; font-size: 17px; }
    .post-row { width: 100%; text-align: left; padding: 10px; margin-bottom: 8px; cursor: pointer; }
    .post-row:hover { border-color: #4f7cac; }
    .post-row strong { display: block; margin-bottom: 4px; }
    .meta { color: #667085; font-size: 13px; overflow-wrap: anywhere; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #f1f4f8; padding: 12px; border-radius: 6px; }
    img { display: block; max-width: 100%; max-height: 280px; border-radius: 6px; object-fit: contain; background: #eef2f6; }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
    button { border: 1px solid #b8c2cc; background: white; border-radius: 6px; padding: 8px 10px; cursor: pointer; }
    button.primary { background: #2563eb; border-color: #2563eb; color: white; }
    button.danger { background: #b42318; border-color: #b42318; color: white; }
    select { border: 1px solid #b8c2cc; border-radius: 6px; padding: 8px; }
    @media (max-width: 820px) { .layout { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header><h1>Marketing Orchestrator</h1></header>
  <main>
    <section class="status-grid" id="status"></section>
    <section class="layout">
      <div class="panel">
        <h2>Latest Posts</h2>
        <div id="posts"></div>
      </div>
      <div class="panel">
        <h2>Post Detail</h2>
        <div id="detail" class="meta">Select a post.</div>
      </div>
    </section>
  </main>
  <script>
    let selectedPost = null;

    async function getJson(url, options) {
      const response = await fetch(url, options || {});
      return response.json();
    }

    function statusBox(label, value) {
      return `<div class="status-box"><div class="label">${label}</div><div class="value">${value}</div></div>`;
    }

    async function loadStatus() {
      const data = await getJson('/api/status');
      document.getElementById('status').innerHTML = [
        statusBox('Backend', data.backend),
        statusBox('Ollama', data.ollama),
        statusBox('OpenAI fallback', data.openai_fallback),
        statusBox('OpenClaw', data.openclaw),
        statusBox('Real publishing', data.real_publishing_enabled ? 'enabled' : 'disabled')
      ].join('');
    }

    async function loadPosts() {
      const data = await getJson('/api/posts');
      const posts = data.posts || [];
      document.getElementById('posts').innerHTML = posts.map(post => `
        <button class="post-row" onclick="loadPost(${post.id})">
          <strong>#${post.id} ${post.topic}</strong>
          <span class="meta">${post.status} · ${post.platform} · ${post.provider || 'unknown'}</span>
        </button>
      `).join('') || '<div class="meta">No generated posts yet.</div>';
    }

    async function loadPost(id) {
      const data = await getJson(`/api/posts/${id}`);
      if (!data.found) {
        document.getElementById('detail').textContent = data.error || 'Post not found.';
        return;
      }
      selectedPost = data.post;
      renderDetail();
    }

    function renderDetail() {
      const post = selectedPost;
      const image = post.image_url ? `<img src="${post.image_url}" alt="${post.image_file || 'Selected image'}">` : '<div class="meta">No image selected.</div>';
      document.getElementById('detail').innerHTML = `
        <div class="meta">ID: ${post.id}</div>
        <div class="meta">Created: ${post.created_at}</div>
        <div class="meta">Status: <strong>${post.status}</strong></div>
        <div class="meta">Provider: ${post.provider || 'unknown'}</div>
        <div class="meta">File: ${post.file_path || ''}</div>
        <div class="meta">Image: ${post.image_file || ''}</div>
        <div class="actions">
          <button class="primary" onclick="approvePost()">Approve</button>
          <button class="danger" onclick="rejectPost()">Reject</button>
          <button onclick="schedulePost()">Mark scheduled</button>
          <button onclick="regeneratePost()">Regenerate</button>
          <button onclick="copyCaption()">Copy caption</button>
          <select id="targetPlatform">
            <option value="instagram">Instagram</option>
            <option value="facebook">Facebook</option>
            <option value="x">X</option>
          </select>
          <button onclick="publishPost()">Mark published</button>
        </div>
        ${image}
        <pre id="captionText">${post.content || ''}</pre>
        <div class="meta">Approved at: ${post.approved_at || ''}</div>
        <div class="meta">Published at: ${post.published_at || ''}</div>
        <div class="meta">Target platform: ${post.target_platform || ''}</div>
        <pre>${post.publish_result || ''}</pre>
      `;
    }

    async function action(path, options) {
      if (!selectedPost) return;
      const data = await getJson(`/api/posts/${selectedPost.id}/${path}`, options || {method: 'POST'});
      if (!data.success) {
        alert(data.error || 'Action failed.');
        return;
      }
      await loadPosts();
      if (data.post) {
        selectedPost = data.post;
        renderDetail();
      } else if (data.regenerated) {
        await loadPost(data.regenerated.id);
      }
    }

    function approvePost() { action('approve'); }
    function rejectPost() { action('reject'); }
    function schedulePost() { action('schedule'); }
    function regeneratePost() { action('regenerate'); }
    function publishPost() {
      const platform = document.getElementById('targetPlatform').value;
      action('publish', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({platform})
      });
    }
    function copyCaption() {
      if (selectedPost) navigator.clipboard.writeText(selectedPost.content || '');
    }

    loadStatus();
    loadPosts();
    setInterval(loadStatus, 30000);
  </script>
</body>
</html>
"""
