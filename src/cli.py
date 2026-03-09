"""CLI entry point for auto-apply."""

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .config import load_config, validate_config
from .db import init_db, get_stats, upsert_job

app = typer.Typer(
    name="auto-apply",
    help="Automated job application tool. Reads jobs from Google Sheets, "
         "tailors your resume with AI, and applies automatically.",
    add_completion=False,
)
console = Console()


@app.command()
def config():
    """Validate and display current configuration."""
    cfg = load_config()
    issues = validate_config(cfg)

    # Display config
    table = Table(title="Configuration", show_header=True)
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Applicant Name", cfg.env.applicant_name or "[red]NOT SET[/red]")
    table.add_row("Resume Path", cfg.env.resume_path or "[red]NOT SET[/red]")
    table.add_row("Google Sheet ID", cfg.env.google_sheet_id[:20] + "..." if cfg.env.google_sheet_id else "[red]NOT SET[/red]")
    table.add_row("OpenAI API Key", "****" + cfg.env.openai_api_key[-4:] if cfg.env.openai_api_key else "[red]NOT SET[/red]")
    table.add_row("SMTP Email", "[dim]skipped[/dim]")
    table.add_row("AI Model", cfg.ai.model)
    table.add_row("Max Applications/Run", str(cfg.apply.limit))
    table.add_row("Enabled Portals", ", ".join(cfg.apply.portals))
    table.add_row("Browser Headless", str(cfg.browser.headless))
    table.add_row("Delay Between Apps", f"{cfg.apply.delay}s (±50%)")

    console.print(table)

    if issues:
        console.print()
        console.print(Panel(
            "\n".join(f"[yellow]⚠[/yellow]  {issue}" for issue in issues),
            title="[red]Configuration Issues[/red]",
            border_style="red",
        ))
        console.print("\nCopy [cyan].env.example[/cyan] to [cyan].env[/cyan] and fill in your values.")
    else:
        console.print("\n[green]✓ Configuration looks good![/green]")


@app.command()
def status():
    """Show application statistics from local database."""
    init_db()
    stats = get_stats()

    if stats["total_jobs"] == 0:
        console.print("[yellow]No jobs tracked yet.[/yellow] Run [cyan]auto-apply run[/cyan] to get started.")
        return

    table = Table(title="Application Statistics", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green", justify="right")

    table.add_row("Total Jobs Tracked", str(stats["total_jobs"]))
    table.add_row("Last 24 Hours", str(stats["last_24h"]))

    for status_name, count in stats.get("by_status", {}).items():
        table.add_row(f"Status: {status_name}", str(count))

    for method, count in stats.get("by_method", {}).items():
        table.add_row(f"Method: {method}", str(count))

    console.print(table)


@app.command()
def run(
    dry_run: bool = typer.Option(False, "--dry-run", help="Scrape and tailor but don't submit"),
    confirm: bool = typer.Option(True, "--confirm/--no-confirm", help="Pause for confirmation before each submission"),
    portal: str = typer.Option(None, "--portal", help="Only process jobs from this portal type"),
    limit: int = typer.Option(None, "--limit", help="Override max applications per run"),
):
    """Run the full pipeline: read sheet → scrape → tailor → apply."""
    init_db()
    cfg = load_config()
    issues = validate_config(cfg)

    if issues:
        console.print("[red]Configuration errors must be fixed before running:[/red]")
        for issue in issues:
            console.print(f"  [yellow]⚠[/yellow]  {issue}")
        raise typer.Exit(1)

    from .sheets.reader import read_jobs
    from .sheets.writer import update_job_status
    from .scraper import scrape_job
    from .documents.resume_parser import parse_resume
    from .ai.tailor import tailor_resume
    from .ai.cover_letter import generate_cover_letter
    from .documents.pdf_generator import save_pdf
    from .applicator import apply_to_job
    from .models import ApplicationStatus, TailoredDocuments
    from .db import has_successful_application, record_application
    import re

    if dry_run:
        console.print("[yellow]DRY RUN MODE[/yellow] — will generate materials but not submit\n")

    max_apps = limit or cfg.apply.limit
    console.print(f"Reading jobs from sheet (limit: {max_apps})...\n")
    jobs = read_jobs(cfg)

    if not jobs:
        console.print("[yellow]No pending jobs found.[/yellow]")
        return

    # Filter by portal if specified
    if portal:
        jobs = [j for j in jobs if j.portal_type and j.portal_type.value == portal]
        if not jobs:
            console.print(f"[yellow]No jobs found for portal: {portal}[/yellow]")
            return

    jobs = jobs[:max_apps]
    console.print(f"Processing [green]{len(jobs)}[/green] job(s)...\n")

    resume_text = parse_resume(cfg.env.resume_path)
    applied = 0

    for job in jobs:
        console.rule(f"[cyan]{job.company or job.url}[/cyan]")

        # Skip duplicates
        if has_successful_application(job.url):
            console.print("[dim]Already applied — skipping.[/dim]")
            continue

        # Scrape if needed
        if not job.description:
            console.print("Scraping job description...")
            try:
                job = scrape_job(job)
                upsert_job(url=job.url, company=job.company, role=job.role,
                           portal_type=job.portal_type.value if job.portal_type else "",
                           description=job.description or "")
            except Exception as e:
                console.print(f"[red]Scrape failed: {e}[/red]")
                continue

        console.print(f"Role: [green]{job.role}[/green] at [cyan]{job.company}[/cyan]")

        # Tailor
        safe_company = re.sub(r"[^\w]", "_", job.company or "Company")[:40]
        resume_path = f"data/resumes/{cfg.env.applicant_name.replace(' ', '_')}_Resume_{safe_company}.pdf"
        cl_path = f"data/cover_letters/{cfg.env.applicant_name.replace(' ', '_')}_CoverLetter_{safe_company}.pdf"

        console.print("Tailoring resume and cover letter...")
        try:
            tailored = tailor_resume(cfg, resume_text, job.description or "", job.company, job.role)
            cover_letter = generate_cover_letter(cfg, resume_text, job.description or "",
                                                  job.company, job.role, cfg.env.applicant_name)
            save_pdf(tailored, resume_path)
            save_pdf(cover_letter, cl_path)
        except Exception as e:
            console.print(f"[red]AI tailoring failed: {e}[/red]")
            continue

        docs = TailoredDocuments(
            resume_text=tailored,
            cover_letter_text=cover_letter,
            resume_path=resume_path,
            cover_letter_path=cl_path,
        )

        if dry_run:
            console.print(f"[yellow]DRY RUN:[/yellow] Skipping submission.")
            console.print(f"  Resume: {resume_path}")
            console.print(f"  Cover letter: {cl_path}")
            update_job_status(cfg, job, ApplicationStatus.TAILORED)
            continue

        # Apply
        console.print("Opening browser to apply...")
        try:
            result = apply_to_job(job, docs, cfg, confirm=confirm)
        except NotImplementedError as e:
            console.print(f"[yellow]Skipped:[/yellow] {e}")
            continue

        job_id = upsert_job(url=job.url, company=job.company, role=job.role,
                            portal_type=job.portal_type.value if job.portal_type else "")
        record_application(
            job_id=job_id,
            status=result.status.value,
            method=result.method.value if result.method else "",
            resume_path=resume_path,
            cover_letter_path=cl_path,
            screenshot_path=result.screenshot_path or "",
            error_message=result.error_message or "",
        )
        update_job_status(cfg, job, result.status, method=result.method.value if result.method else "")

        if result.status == ApplicationStatus.APPLIED:
            console.print(f"[green]✓ Applied![/green]")
            applied += 1
        else:
            console.print(f"[red]✗ Failed: {result.error_message}[/red]")

    console.print(f"\n[green]Done.[/green] Applied to {applied}/{len(jobs)} job(s).")


@app.command()
def scrape():
    """Read jobs from Google Sheet and scrape their descriptions."""
    init_db()
    cfg = load_config()
    issues = validate_config(cfg)

    if issues:
        console.print("[red]Fix configuration issues first:[/red]")
        for issue in issues:
            console.print(f"  [yellow]⚠[/yellow]  {issue}")
        raise typer.Exit(1)

    from .sheets.reader import read_jobs
    from .sheets.writer import update_job_status, write_scraped_summary
    from .scraper import scrape_job
    from .models import ApplicationStatus

    console.print("Reading jobs from Google Sheet...")
    jobs = read_jobs(cfg)

    if not jobs:
        console.print("[yellow]No pending jobs found in sheet.[/yellow]")
        return

    console.print(f"Found [green]{len(jobs)}[/green] pending job(s). Scraping...\n")

    table = Table(show_header=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Company", style="cyan")
    table.add_column("Role", style="green")
    table.add_column("Portal", style="magenta")
    table.add_column("Status", style="dim")

    for job in jobs:
        try:
            job = scrape_job(job)
            status_text = "[green]scraped[/green]"
            # Save to DB
            upsert_job(url=job.url, company=job.company, role=job.role,
                       portal_type=job.portal_type.value if job.portal_type else "",
                       description=job.description or "")
            # Write company/role back to sheet if they were empty
            update_job_status(cfg, job, ApplicationStatus.SCRAPED)
            # Write description summary to notes column
            if job.description:
                write_scraped_summary(cfg, job, job.description[:500])
        except Exception as e:
            status_text = f"[red]failed: {e}[/red]"
            upsert_job(url=job.url, company=job.company, role=job.role,
                       portal_type=job.portal_type.value if job.portal_type else "")

        table.add_row(
            str(job.row_number),
            job.company or "—",
            job.role or "—",
            job.portal_type.value if job.portal_type else "unknown",
            status_text,
        )

    console.print(table)
    console.print("\n[green]Done.[/green] Run [cyan]auto-apply status[/cyan] to see DB summary.")


@app.command()
def tailor(job_url: str = typer.Argument(..., help="URL of the job to tailor materials for")):
    """Generate tailored resume and cover letter for a specific job."""
    init_db()
    cfg = load_config()
    issues = validate_config(cfg)

    if issues:
        console.print("[red]Fix configuration issues first:[/red]")
        for issue in issues:
            console.print(f"  [yellow]⚠[/yellow]  {issue}")
        raise typer.Exit(1)

    from .documents.resume_parser import parse_resume
    from .ai.tailor import tailor_resume
    from .ai.cover_letter import generate_cover_letter
    from .documents.pdf_generator import save_pdf
    from .scraper import scrape_job
    from .scraper.detector import detect_portal
    from .models import Job, ApplicationStatus
    from .sheets.reader import read_jobs
    from .db import upsert_job
    import re

    # Find the job — check sheet first, then build a minimal Job from URL
    console.print("Looking up job details...")
    jobs = read_jobs(cfg, skip_applied=False)
    job = next((j for j in jobs if j.url == job_url or job_url in j.url), None)

    if not job:
        job = Job(row_number=0, url=job_url, portal_type=detect_portal(job_url))

    # Scrape if description is missing
    if not job.description:
        console.print("Scraping job description...")
        job = scrape_job(job)

    console.print(f"Job: [cyan]{job.role}[/cyan] at [green]{job.company}[/green]\n")

    # Parse resume
    console.print("Parsing resume...")
    resume_text = parse_resume(cfg.env.resume_path)

    # Tailor resume
    console.print("Tailoring resume with Claude...")
    tailored_resume = tailor_resume(
        config=cfg,
        resume_text=resume_text,
        job_description=job.description or "",
        company=job.company,
        role=job.role,
    )

    # Generate cover letter
    console.print("Generating cover letter with Claude...")
    cover_letter = generate_cover_letter(
        config=cfg,
        resume_text=resume_text,
        job_description=job.description or "",
        company=job.company,
        role=job.role,
        name=cfg.env.applicant_name,
    )

    # Save PDFs
    safe_company = re.sub(r"[^\w]", "_", job.company or "Company")
    resume_path = f"data/resumes/{cfg.env.applicant_name.replace(' ', '_')}_Resume_{safe_company}.pdf"
    cl_path = f"data/cover_letters/{cfg.env.applicant_name.replace(' ', '_')}_CoverLetter_{safe_company}.pdf"

    console.print("Saving PDFs...")
    save_pdf(tailored_resume, resume_path)
    save_pdf(cover_letter, cl_path)

    # Update DB
    job_id = upsert_job(url=job.url, company=job.company, role=job.role,
                        portal_type=job.portal_type.value if job.portal_type else "")

    console.print(f"\n[green]Done![/green]")
    console.print(f"  Resume:       [cyan]{resume_path}[/cyan]")
    console.print(f"  Cover letter: [cyan]{cl_path}[/cyan]")
    console.print("\nReview the PDFs before applying. Run [cyan]auto-apply run[/cyan] to submit.")


def main():
    app()


if __name__ == "__main__":
    main()
