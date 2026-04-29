"""
Flask web application for the Program Research Agent.

Provides a simple form UI for triggering research runs and a results
page for checking status and downloading output files.
"""

import os

from flask import Flask, redirect, render_template, request, url_for
from redis import Redis
from rq import Queue

from .worker import run_research_job

# Default list of org email addresses for the "your email" dropdown.
# Override with a comma-separated env var if needed.
ORG_EMAILS = [
    e.strip()
    for e in os.environ.get("ORG_EMAILS", "").split(",")
    if e.strip()
]

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# Simple auth
AUTH_PASSWORD = os.environ.get("APP_PASSWORD", "")

# Redis / RQ setup
redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
redis_conn = Redis.from_url(redis_url)
queue = Queue("research", connection=redis_conn)


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------

@app.before_request
def check_auth():
    """Simple password gate. Skip if no APP_PASSWORD is set."""
    if not AUTH_PASSWORD:
        return  # no auth configured
    if request.path.startswith("/static"):
        return
    if request.path == "/login" or request.path == "/health":
        return
    if request.cookies.get("auth") == AUTH_PASSWORD:
        return
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == AUTH_PASSWORD:
            resp = redirect(url_for("index"))
            resp.set_cookie("auth", AUTH_PASSWORD, httponly=True, samesite="Lax")
            return resp
        error = "Wrong password"
    return render_template("login.html", error=error)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return {"status": "ok"}


@app.route("/", methods=["GET"])
def index():
    """Render the research form."""
    return render_template("index.html", org_emails=ORG_EMAILS)


@app.route("/submit", methods=["POST"])
def submit():
    """Accept form data and enqueue a research job."""
    program = request.form["program"].strip()
    state_code = request.form["state"].strip().lower()
    white_label = request.form["white_label"].strip().lower()
    email = request.form.get("email", "").strip()
    if email == "_other":
        email = request.form.get("email_other", "").strip()

    # Collect source URLs (up to 5 fields, skip blanks)
    source_urls = [
        url.strip()
        for i in range(1, 6)
        if (url := request.form.get(f"source_url_{i}", "").strip())
    ]

    if not program or not state_code or not white_label or not source_urls or not email:
        return render_template(
            "index.html",
            error="All fields are required: program, state, white label, email, and at least one source URL.",
            form=request.form,
            org_emails=ORG_EMAILS,
        )

    job = queue.enqueue(
        run_research_job,
        program=program,
        state_code=state_code,
        white_label=white_label,
        source_urls=source_urls,
        email=email,
        job_timeout="30m",  # research can take a while
    )

    return redirect(url_for("results", job_id=job.id))


@app.route("/results/<job_id>")
def results(job_id):
    """Show job status and download links when complete."""
    from rq.job import Job

    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception:
        return render_template("results.html", error="Job not found.", job_id=job_id)

    status = job.get_status()

    # Build context for template
    ctx = {
        "job_id": job_id,
        "status": status,
        "meta": job.meta,
        "error": None,
        "files": [],
    }

    if status == "failed":
        ctx["error"] = str(job.exc_info) if job.exc_info else "Unknown error"
    elif status == "finished":
        result = job.result or {}
        ctx["summary"] = result.get("summary", "")
        ctx["emailed_to"] = result.get("emailed_to")

    return render_template("results.html", **ctx)


@app.route("/jobs")
def jobs_list():
    """Show recent jobs."""
    from rq.job import Job
    from rq.registry import FinishedJobRegistry, StartedJobRegistry, FailedJobRegistry

    recent = []

    for registry_cls, label in [
        (StartedJobRegistry, "running"),
        (FinishedJobRegistry, "finished"),
        (FailedJobRegistry, "failed"),
    ]:
        registry = registry_cls(queue=queue)
        for job_id in registry.get_job_ids()[:20]:
            try:
                job = Job.fetch(job_id, connection=redis_conn)
                recent.append({
                    "id": job_id,
                    "status": label,
                    "program": job.meta.get("program", "?"),
                    "state": job.meta.get("state_code", "?"),
                    "enqueued_at": job.enqueued_at,
                })
            except Exception:
                pass

    # Also grab queued jobs
    for job in queue.jobs[:10]:
        recent.append({
            "id": job.id,
            "status": "queued",
            "program": job.meta.get("program", "?"),
            "state": job.meta.get("state_code", "?"),
            "enqueued_at": job.enqueued_at,
        })

    recent.sort(key=lambda j: j.get("enqueued_at") or "", reverse=True)

    return render_template("jobs.html", jobs=recent)


# ---------------------------------------------------------------------------
# Entry point (dev)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
