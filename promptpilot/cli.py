"""CLI interface."""

import click

from . import db
from .models import TaskCreate, TaskStatus


def _status_color(status: str) -> str:
    return {
        "pending": "white",
        "running": "cyan",
        "completed": "green",
        "failed": "red",
        "rate_limited": "yellow",
        "cancelled": "magenta",
    }.get(status, "white")


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """PromptPilot — AI Prompt Scheduler"""
    if ctx.invoked_subcommand is None:
        # Default: launch tray app when run without arguments
        from .tray import run_tray
        run_tray()


@cli.command()
@click.argument("prompt", required=False)
@click.option("-f", "--file", "file_path", type=click.Path(exists=True), help="File with prompts (one per line)")
@click.option("-p", "--priority", default=5, type=click.IntRange(1, 10), help="Priority 1-10 (1=highest)")
@click.option("-a", "--at", "scheduled_at", help="Schedule time (ISO format, e.g. 2026-03-25T03:00)")
@click.option("-d", "--dir", "working_dir", help="Working directory for claude execution")
@click.option("-c", "--cli", "provider", default=None, help="CLI provider: claude, claude-z, or custom command")
@click.option("-r", "--max-retries", default=5, type=int, help="Max retries on rate limit")
def add(prompt, file_path, priority, scheduled_at, working_dir, provider, max_retries):
    """Add a task (or multiple from file)."""
    from datetime import datetime

    prompts = []
    if file_path:
        with open(file_path) as f:
            prompts = [line.strip() for line in f if line.strip()]
    elif prompt:
        prompts = [prompt]
    else:
        click.echo("Provide a prompt or --file")
        return

    dt = datetime.fromisoformat(scheduled_at) if scheduled_at else None

    for p in prompts:
        task = db.create_task(TaskCreate(
            prompt=p,
            working_dir=working_dir,
            provider=provider,
            priority=priority,
            scheduled_at=dt,
            max_retries=max_retries,
        ))
        cli_info = f" [{provider}]" if provider else ""
        time_info = f" at {dt}" if dt else ""
        click.echo(f"  #{task.id} [P{priority}]{cli_info}{time_info} {p[:70]}")

    click.echo(click.style(f"\n{len(prompts)} task(s) added.", fg="green"))


@cli.command("list")
@click.option("-s", "--status", type=click.Choice([s.value for s in TaskStatus]), help="Filter by status")
@click.option("-n", "--limit", default=20, help="Number of tasks to show")
def list_tasks(status, limit):
    """List tasks."""
    st = TaskStatus(status) if status else None
    tasks = db.list_tasks(status=st, limit=limit)

    if not tasks:
        click.echo("No tasks found.")
        return

    click.echo(f"{'ID':>5}  {'Status':<13}  {'P':>1}  {'Retries':>7}  Prompt")
    click.echo("-" * 80)
    for t in tasks:
        prompt_short = t.prompt[:50].replace("\n", " ")
        status_str = click.style(f"{t.status.value:<13}", fg=_status_color(t.status.value))
        click.echo(f"{t.id:>5}  {status_str}  {t.priority:>1}  {t.retry_count:>3}/{t.max_retries:<3}  {prompt_short}")


@cli.command()
@click.argument("task_id", type=int)
def status(task_id):
    """Show task details."""
    task = db.get_task(task_id)
    if not task:
        click.echo(f"Task #{task_id} not found.")
        return

    click.echo(f"Task #{task.id}")
    click.echo(f"  Status:    {click.style(task.status.value, fg=_status_color(task.status.value))}")
    click.echo(f"  Provider:  {task.provider or 'claude (default)'}")
    click.echo(f"  Priority:  {task.priority}")
    click.echo(f"  Created:   {task.created_at}")
    if task.scheduled_at:
        click.echo(f"  Scheduled: {task.scheduled_at}")
    if task.started_at:
        click.echo(f"  Started:   {task.started_at}")
    if task.completed_at:
        click.echo(f"  Completed: {task.completed_at}")
    click.echo(f"  Retries:   {task.retry_count}/{task.max_retries}")
    if task.next_run_at:
        click.echo(f"  Next run:  {task.next_run_at}")
    click.echo(f"\n  Prompt:\n    {task.prompt}")
    if task.result:
        click.echo(f"\n  Result:\n    {task.result[:500]}")
    if task.error:
        click.echo(f"\n  Error:\n    {task.error[:500]}")


@cli.command()
@click.argument("task_id", type=int)
def cancel(task_id):
    """Cancel a pending/rate_limited task."""
    if db.cancel_task(task_id):
        click.echo(click.style(f"Task #{task_id} cancelled.", fg="yellow"))
    else:
        click.echo("Cannot cancel (task not found or already running/completed).")


@cli.command()
@click.argument("task_id", type=int)
def delete(task_id):
    """Delete a task."""
    if db.delete_task(task_id):
        click.echo(f"Task #{task_id} deleted.")
    else:
        click.echo("Task not found.")


@cli.command()
@click.option("--days", default=7, help="Delete tasks older than N days")
def purge(days):
    """Delete old completed/failed/cancelled tasks."""
    count = db.purge_old(days)
    click.echo(f"Purged {count} task(s).")


@cli.command("move-ready")
@click.option("--days", default=7, show_default=True, type=int, help="Move completed+done tasks older than N days")
def move_ready(days):
    """Move completed tasks from ref-status 'done' to hidden ref-status 'ready' (for cron)."""
    moved = db.move_completed_done_to_ready(before_days=days)
    click.echo(f"Moved to ready: {moved} task(s).")


@cli.command()
def stats():
    """Show task statistics."""
    s = db.get_stats()
    click.echo(f"  Pending:      {s.pending}")
    click.echo(f"  Running:      {s.running}")
    click.echo(f"  Rate Limited: {s.rate_limited}")
    click.echo(f"  Completed:    {s.completed}")
    click.echo(f"  Failed:       {s.failed}")
    click.echo(f"  Cancelled:    {s.cancelled}")
    click.echo(f"  Total:        {s.total}")


@cli.command()
@click.argument("action", required=False, default="list")
@click.argument("name", required=False)
@click.option("--cmd", "cmd_template", help='Command template, e.g. "myai --run {prompt}"')
@click.option("--desc", default="", help="Description")
@click.option("--env", "env_vars", multiple=True, help='Env vars: KEY=VALUE (repeat for multiple)')
def provider(action, name, cmd_template, desc, env_vars):
    """Manage CLI providers. Actions: list, add, remove.

    \b
    Examples:
      pp provider                              # list all
      pp provider add myai --cmd "myai {prompt}"
      pp provider remove myai
    """
    from .config import DEFAULT_CLI, load_providers, save_provider, remove_provider

    if action == "list" or (action is None and name is None):
        provs = load_providers()
        click.echo("Available providers:\n")
        for pname, info in provs.items():
            default = " (default)" if pname == DEFAULT_CLI else ""
            pdesc = info.get("description", "")
            click.echo(f"  {click.style(pname, fg='cyan')}{default}")
            if pdesc:
                click.echo(f"    {pdesc}")
            click.echo(f"    cmd: {info['cmd']}")
            click.echo()
        click.echo("  Add custom: pp provider add <name> --cmd \"<command> {prompt}\"")
        click.echo("  Config:     ~/.promptpilot/providers.json")

    elif action == "add":
        if not name:
            click.echo("Usage: pp provider add <name> --cmd \"<command> {prompt}\"")
            return
        if not cmd_template:
            # Default: treat name as the command, just append {prompt}
            cmd_template = f"{name} {{prompt}}"
        if "{prompt}" not in cmd_template:
            cmd_template += " {prompt}"
        env = {}
        for kv in env_vars:
            if "=" in kv:
                k, v = kv.split("=", 1)
                env[k.strip()] = v.strip()
        save_provider(name, cmd_template, desc, env=env)
        click.echo(click.style(f"Provider '{name}' added: {cmd_template}", fg="green"))
        if env:
            click.echo(f"  Env: {', '.join(env.keys())}")

    elif action == "remove":
        if not name:
            click.echo("Usage: pp provider remove <name>")
            return
        if remove_provider(name):
            click.echo(f"Provider '{name}' removed.")
        else:
            click.echo(f"Provider '{name}' not found in custom providers.")

    else:
        click.echo(f"Unknown action: {action}. Use: list, add, remove")


@cli.command()
def worker():
    """Start the worker (executes queued tasks)."""
    from .worker import run_worker
    run_worker()


@cli.command("poll-limits")
def poll_limits():
    """Poll and refresh limits for agent accounts (for cron)."""
    from .limits import refresh_limits_for_provider

    rows = db.list_agent_accounts_for_limits(limit=5000)
    if not rows:
        click.echo("No agent accounts found.")
        return

    updated = 0
    skipped_manual = 0
    skipped_inactive = 0
    skipped_unknown = 0

    for row in rows:
        account_id = int(row["id"])
        status = int(row.get("status") or 0)
        if status == 2:
            skipped_manual += 1
            continue
        if not bool(row.get("is_active")):
            skipped_inactive += 1
            continue

        agent_key = str(row.get("agent_shortname") or row.get("agent_name") or "").strip().lower()
        provider = None
        if "codex" in agent_key:
            provider = "codex"
        elif "claude" in agent_key:
            provider = "claude"
        if not provider:
            skipped_unknown += 1
            continue

        limits = refresh_limits_for_provider(provider, token=row.get("token"))
        if not limits:
            continue

        db.update_agent_account_limits(
            account_id,
            status=limits.get("status"),
            percent_5h=limits.get("percent_5h"),
            percent_7d=limits.get("percent_7d"),
            balance_tokens=limits.get("balance_tokens"),
            reset_5h=limits.get("reset_5h"),
            reset_7d=limits.get("reset_7d"),
        )
        updated += 1

    click.echo(
        f"Limits polled: updated={updated}, skipped_manual_status2={skipped_manual}, skipped_inactive={skipped_inactive}, skipped_unknown_agent={skipped_unknown}"
    )


@cli.command("poll-limits-all")
def poll_limits_all():
    """Poll limits for ALL agent accounts: active + inactive with credentials (for cron)."""
    import json as _json
    from .limits import fetch_claude_limits, fetch_codex_limits
    from .relogin import _try_switch_noninteractive

    rows = db.list_agent_accounts_for_limits_all(limit=5000)
    if not rows:
        click.echo("No agent accounts found.")
        return

    # Группируем по agent_id: для каждого агента отдельно фаза 1 и фаза 2
    agents: dict[int, dict] = {}
    for row in rows:
        aid = int(row["agent_id"])
        if aid not in agents:
            agents[aid] = {"active": None, "inactive": []}
        if bool(row.get("is_active")):
            agents[aid]["active"] = row
        else:
            agents[aid]["inactive"].append(row)

    updated_active = 0
    updated_inactive = 0
    skipped_no_creds = 0
    skipped_failed = 0
    skipped_unknown = 0

    def _save_limits(account_id: int, limits: dict) -> None:
        db.update_agent_account_limits(
            account_id,
            status=limits.get("status"),
            percent_5h=limits.get("percent_5h"),
            percent_7d=limits.get("percent_7d"),
            balance_tokens=limits.get("balance_tokens"),
            reset_5h=limits.get("reset_5h"),
            reset_7d=limits.get("reset_7d"),
        )

    def _agent_key(row: dict) -> str:
        return str(row.get("agent_shortname") or row.get("agent_name") or "").strip().lower()

    def _extract_token(row: dict) -> str:
        token = str(row.get("token") or "").strip()
        if token:
            return token
        creds = row.get("claude_credentials")
        if isinstance(creds, str):
            try:
                creds = _json.loads(creds)
            except Exception:
                creds = None
        if isinstance(creds, dict):
            token = str((creds.get("claudeAiOauth") or {}).get("accessToken") or "").strip()
        return token

    def _has_credentials(row: dict) -> bool:
        creds = row.get("claude_credentials")
        if isinstance(creds, str):
            try:
                creds = _json.loads(creds)
            except Exception:
                creds = None
        if isinstance(creds, dict) and creds:
            return True
        return bool(str(row.get("token") or "").strip())

    # ── Фаза 1: активные аккаунты ────────────────────────────────────────────
    for aid, group in agents.items():
        active = group.get("active")
        if not active:
            continue
        account_id = int(active["id"])
        key = _agent_key(active)

        if "claude" in key:
            token = _extract_token(active)
            if not token:
                skipped_no_creds += 1
                continue
            limits = fetch_claude_limits(token=token)
            if limits:
                _save_limits(account_id, limits)
                updated_active += 1
            else:
                skipped_failed += 1

        elif "codex" in key:
            limits = fetch_codex_limits()
            if limits:
                _save_limits(account_id, limits)
                updated_active += 1
            else:
                skipped_failed += 1

        else:
            skipped_unknown += 1

    # ── Фаза 2: неактивные аккаунты с сохранёнными credentials ───────────────
    for aid, group in agents.items():
        original_active = group.get("active")
        original_active_id = int(original_active["id"]) if original_active else None
        switched = False  # был ли смен активного аккаунта в этом агенте

        for inactive in group["inactive"]:
            key = _agent_key(inactive)
            if "claude" not in key:
                skipped_unknown += 1
                continue
            if not _has_credentials(inactive):
                skipped_no_creds += 1
                continue

            result = _try_switch_noninteractive(inactive)
            if result and result.get("ok"):
                updated_inactive += 1
                switched = True
            else:
                skipped_failed += 1

        # Восстанавливаем исходный активный аккаунт
        if switched and original_active_id:
            db.set_agent_account_active(original_active_id, True)

    click.echo(
        f"Limits polled: active={updated_active}, inactive={updated_inactive}, "
        f"skipped_no_creds={skipped_no_creds}, skipped_failed={skipped_failed}, "
        f"skipped_unknown_agent={skipped_unknown}"
    )


@cli.command()
def bot():
    """Start the Telegram bot (requires PP_TG_TOKEN env var)."""
    from .bot import run_bot
    run_bot()


@cli.command()
def tray():
    """Start the system tray launcher (default when run without arguments)."""
    from .tray import run_tray
    run_tray()


@cli.command()
@click.option("-h", "--host", default=None, help="Host (default: 127.0.0.1)")
@click.option("-p", "--port", default=None, type=int, help="Port (default: 8420)")
def server(host, port):
    """Start the web UI server."""
    import uvicorn
    from .config import HOST, PORT

    h = host or HOST
    p = port or PORT
    from .api import app
    click.echo(f"PromptPilot UI: http://{h}:{p}")
    uvicorn.run(app, host=h, port=p, log_level="info")


if __name__ == "__main__":
    cli()
