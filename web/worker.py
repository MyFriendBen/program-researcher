"""
RQ worker function that runs the research workflow and emails results.

This is the function that gets enqueued by the Flask app and executed
by the worker dyno.
"""

import asyncio
import os
import smtplib
import traceback
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from rq import get_current_job


# ---------------------------------------------------------------------------
# Email helpers
# ---------------------------------------------------------------------------

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")  # Gmail address or service account
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")  # Gmail app password
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")


def send_results_email(
    to_email: str,
    program: str,
    state_code: str,
    output_dir: Path,
    summary: str,
    status: str,
) -> None:
    """
    Email the ticket_content files (and summary) to the user who
    triggered the research run.
    """
    subject = f"Program Researcher: {program.upper()} ({state_code.upper()}) — {status}"

    # Build the email
    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = to_email
    msg["Subject"] = subject

    # Body text
    if status == "completed":
        body = (
            f"Research for {program.upper()} ({state_code.upper()}) finished successfully.\n\n"
            f"The three draft artifacts are attached:\n"
            f"  - initial_config.json  (program config)\n"
            f"  - test_cases.json      (JSON test cases)\n"
            f"  - ticket.md            (ticket summary)\n\n"
            f"Post these to the program's Linear ticket as described in the runbook.\n\n"
            f"---\n\n"
            f"{summary}"
        )
    else:
        body = (
            f"Research for {program.upper()} ({state_code.upper()}) finished with status: {status}.\n\n"
            f"Check the summary below for details. You may want to re-run or investigate.\n\n"
            f"---\n\n"
            f"{summary}"
        )

    msg.attach(MIMEText(body, "plain"))

    # Attach files from ticket_content/ directory (the three key deliverables)
    ticket_dir = output_dir / "ticket_content"
    attached_count = 0

    if ticket_dir.exists():
        for filepath in sorted(ticket_dir.iterdir()):
            if filepath.is_file():
                _attach_file(msg, filepath)
                attached_count += 1

    # Also attach the summary markdown
    summary_path = output_dir / "SUMMARY.md"
    if summary_path.exists():
        _attach_file(msg, summary_path)
        attached_count += 1

    # If ticket_content didn't exist (e.g. failure), attach whatever we have
    if attached_count == 0:
        for filepath in sorted(output_dir.iterdir()):
            if filepath.is_file() and filepath.suffix in (".json", ".md", ".txt"):
                _attach_file(msg, filepath)

    # Send
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        if SMTP_PASSWORD:
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(EMAIL_FROM, [to_email], msg.as_string())


def _attach_file(msg: MIMEMultipart, filepath: Path) -> None:
    """Attach a single file to the email."""
    part = MIMEBase("application", "octet-stream")
    part.set_payload(filepath.read_bytes())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        f"attachment; filename={filepath.name}",
    )
    msg.attach(part)


# ---------------------------------------------------------------------------
# Main job function
# ---------------------------------------------------------------------------

def run_research_job(
    program: str,
    state_code: str,
    white_label: str,
    source_urls: list[str],
    email: str,
) -> dict:
    """
    Execute a research run and email the results.

    This function is called by the RQ worker. It:
    1. Updates job metadata so the status page can show progress
    2. Calls the async run_research() function
    3. Emails the output files to the requesting user
    4. Returns a status summary
    """
    job = get_current_job()

    # Store metadata for the status page
    job.meta["program"] = program
    job.meta["state_code"] = state_code
    job.meta["white_label"] = white_label
    job.meta["source_urls"] = source_urls
    job.meta["email"] = email
    job.meta["step"] = "starting"
    job.save_meta()

    try:
        # Import here so the worker process loads the research code
        from program_researcher.graph import run_research

        job.meta["step"] = "running research workflow"
        job.save_meta()

        final_state = asyncio.run(
            run_research(
                program_name=program,
                state_code=state_code,
                white_label=white_label,
                source_urls=source_urls,
                save_outputs=True,
            )
        )

        # Gather results
        output_dir = Path(final_state.output_dir) if final_state.output_dir else None
        summary = ""

        if output_dir and output_dir.exists():
            summary_path = output_dir / "SUMMARY.md"
            if summary_path.exists():
                summary = summary_path.read_text()

        status_value = (
            final_state.status.value
            if hasattr(final_state.status, "value")
            else final_state.status
        )

        # Email the results
        job.meta["step"] = "emailing results"
        job.save_meta()

        if output_dir and output_dir.exists() and SMTP_PASSWORD:
            send_results_email(
                to_email=email,
                program=program,
                state_code=state_code,
                output_dir=output_dir,
                summary=summary,
                status=status_value,
            )
            job.meta["emailed"] = True
        elif not SMTP_PASSWORD:
            job.meta["emailed"] = False
            job.meta["email_skip_reason"] = "SMTP not configured"

        job.meta["step"] = "complete"
        job.meta["workflow_status"] = status_value
        job.save_meta()

        return {
            "status": status_value,
            "summary": summary,
            "emailed_to": email if SMTP_PASSWORD else None,
        }

    except Exception as e:
        job.meta["step"] = "failed"
        job.meta["error"] = str(e)
        job.meta["traceback"] = traceback.format_exc()
        job.save_meta()

        # Try to send a failure notification
        try:
            if SMTP_PASSWORD:
                fail_msg = MIMEMultipart()
                fail_msg["From"] = EMAIL_FROM
                fail_msg["To"] = email
                fail_msg["Subject"] = (
                    f"Program Researcher FAILED: {program.upper()} ({state_code.upper()})"
                )
                fail_msg.attach(MIMEText(
                    f"The research run for {program.upper()} ({state_code.upper()}) failed.\n\n"
                    f"Error: {e}\n\n"
                    f"You can re-try from the web form.",
                    "plain",
                ))
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                    server.starttls()
                    server.login(SMTP_USER, SMTP_PASSWORD)
                    server.sendmail(EMAIL_FROM, [email], fail_msg.as_string())
        except Exception:
            pass  # don't mask the original error

        raise
