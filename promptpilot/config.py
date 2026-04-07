"""Configuration settings."""

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional


def _load_dotenv():
    """Load .env file into os.environ (only for keys not already set).

    Search order:
      1. Directory of pp.exe  (when running as PyInstaller bundle)
      2. Current working directory
      3. ~/.promptpilot/.env  (permanent user config)
    """
    candidates = []

    if getattr(sys, "frozen", False):
        # Running as pp.exe — look next to the binary first
        candidates.append(Path(sys.executable).parent / ".env")

    candidates.append(Path.cwd() / ".env")
    candidates.append(Path.home() / ".promptpilot" / ".env")

    for env_file in candidates:
        if env_file.exists():
            try:
                with open(env_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            key, _, value = line.partition("=")
                            key = key.strip()
                            value = value.strip().strip('"').strip("'")
                            if key and key not in os.environ:
                                os.environ[key] = value
            except OSError:
                pass
            break  # use the first .env found


# Load .env BEFORE reading any os.environ values
_load_dotenv()


def _parse_duration_seconds(raw_value: str, default: int) -> int:
    """Parse duration in seconds.

    Supports plain seconds ("900") and values with units:
    s/sec/сек, m/min/мин, h/hour/час.
    """
    value = (raw_value or "").strip().lower()
    if not value:
        return default

    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([a-zа-я.]*)", value)
    if not match:
        return default

    amount = float(match.group(1))
    unit = match.group(2).strip(".")

    if unit in ("", "s", "sec", "secs", "second", "seconds", "сек", "с"):
        multiplier = 1
    elif unit in ("m", "min", "mins", "minute", "minutes", "мин", "м"):
        multiplier = 60
    elif unit in ("h", "hr", "hrs", "hour", "hours", "ч", "час", "часа", "часов"):
        multiplier = 3600
    else:
        return default

    return max(1, int(amount * multiplier))

# Database
DB_DIR = Path(os.environ.get("PP_DATA_DIR", Path.home() / ".promptpilot"))
DB_PATH = DB_DIR / "promptpilot.db"

# PostgreSQL
PG_DSN = os.environ.get("PP_DB_DSN", "")
PG_HOST = os.environ.get("PP_DB_HOST", os.environ.get("DB_HOST", "127.0.0.1"))
PG_PORT = int(os.environ.get("PP_DB_PORT", os.environ.get("DB_PORT", "5432")))
PG_DATABASE = os.environ.get("PP_DB_DATABASE", os.environ.get("DB_DATABASE", "postgres"))
PG_USER = os.environ.get("PP_DB_USER", os.environ.get("DB_USERNAME", "postgres"))
PG_PASSWORD = os.environ.get("PP_DB_PASSWORD", os.environ.get("DB_PASSWORD", ""))
PG_SSLMODE = os.environ.get("PP_DB_SSLMODE", "prefer")
PG_SCHEMA = os.environ.get("PP_DB_SCHEMA", "hubstaff")
PG_TASKS_TABLE = os.environ.get("PP_DB_TASKS_TABLE", "promptpilot_tasks")
PG_SETTINGS_TABLE = os.environ.get("PP_DB_SETTINGS_TABLE", "promptpilot_settings")

# Worker
POLL_INTERVAL = int(os.environ.get("PP_POLL_INTERVAL", "5"))
TASK_TIMEOUT = int(os.environ.get("PP_TASK_TIMEOUT", "300"))
CLAUDE_TASK_TIMEOUT = int(os.environ.get("PP_CLAUDE_TASK_TIMEOUT", "900"))
AGENT_TIMEOUT = _parse_duration_seconds(os.environ.get("AGENT_TIMEOUT", ""), 0)
BASE_DELAY = int(os.environ.get("PP_BASE_DELAY", "60"))
MAX_DELAY = int(os.environ.get("PP_MAX_DELAY", "3600"))
MAX_RETRIES = int(os.environ.get("PP_MAX_RETRIES", "5"))
AGENT_USER = os.environ.get("AGENT_USER", "").strip()

# Queue (RabbitMQ)
QUEUE_CONNECTION = os.environ.get("PP_QUEUE_CONNECTION", os.environ.get("QUEUE_CONNECTION", "rabbitmq")).strip().lower()
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "127.0.0.1")
RABBITMQ_PORT = int(os.environ.get("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.environ.get("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.environ.get("RABBITMQ_PASSWORD", "guest")
RABBITMQ_VHOST = os.environ.get("RABBITMQ_VHOST", "/")
RABBITMQ_HEARTBEAT = int(os.environ.get("PP_RABBITMQ_HEARTBEAT", "30"))
RABBITMQ_PREFETCH = int(os.environ.get("PP_RABBITMQ_PREFETCH", "1"))
RABBITMQ_QUEUE_PREFIX = os.environ.get("PP_RABBITMQ_QUEUE_PREFIX", "pp_").strip() or "pp_"

# Default CLI command
DEFAULT_CLI = os.environ.get("PP_DEFAULT_CLI", "claude")

# CLI providers — name -> command template with {prompt} placeholder
# Can be overridden/extended via ~/.promptpilot/providers.json
CLAUDE_EXE = os.environ.get(
    "PP_CLAUDE_EXE",
    str(Path.home() / ".local" / "bin" / ("claude.exe" if os.name == "nt" else "claude")),
)

def _cursor_agent_cmd() -> str:
    """Return command to invoke cursor-agent.

    On Windows the npm runner (runner.mjs) spawns the vendor .cmd file without
    shell:true and gets EINVAL.  We bypass it by calling the vendor node.exe +
    index.js directly.  Falls back to 'cursor-agent' if vendor not found.
    """
    try:
        sdk_root = Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "@nothumanwork" / "cursor-agents-sdk"
        manifest = json.loads((sdk_root / "vendor" / "manifest.json").read_text())
        vendor_dir = (sdk_root / manifest["path"]).parent
        node_exe = vendor_dir / "node.exe"
        index_js = vendor_dir / "index.js"
        if node_exe.exists() and index_js.exists():
            return f"{node_exe} {index_js}"
    except Exception:
        pass
    return "cursor-agent"


def _find_rg_dir() -> str:
    """Find ripgrep (rg) directory from Windows registry PATH if not in current PATH."""
    import shutil
    import subprocess as _sp
    if shutil.which("rg"):
        return ""
    try:
        result = _sp.run(
            ["powershell", "-Command", '[System.Environment]::GetEnvironmentVariable("PATH","User")'],
            capture_output=True, text=True, timeout=5,
        )
        for entry in result.stdout.strip().split(";"):
            entry = entry.strip()
            if entry and Path(entry, "rg.exe").exists():
                return entry
    except Exception:
        pass
    return ""


BUILTIN_PROVIDERS = {
    "claude": {
        "cmd": f"{CLAUDE_EXE} -p --verbose --output-format stream-json {{prompt}}",
        "description": "Claude Code (Anthropic)",
        "supports_skills": True,
    },
    "claude-z": {
        "cmd": f"{CLAUDE_EXE} -p --verbose --output-format stream-json {{prompt}}",
        "description": "Claude Code (GLM)",
        "supports_skills": True,
        "env": {
            "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
            "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-4.7",
            "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-4.7",
        },
    },
    "codex": {
        # Use no-sandbox mode by default to avoid bwrap incompatibilities
        # on older Linux hosts (e.g. "bwrap: unknown option --argv0").
        "cmd": "codex exec --dangerously-bypass-approvals-and-sandbox {prompt}",
        "description": "OpenAI Codex",
        "supports_skills": False,
    },
    "qwen": {
        "cmd": "qwen -p {prompt}",
        "description": "Qwen Code",
        "supports_skills": False,
    },
    "cursor": {
        "cmd": f"{_cursor_agent_cmd()} --print --output-format text -f {{prompt}}",
        "description": "Cursor Agent",
        "supports_skills": False,
        "env": {
            "CURSOR_API_KEY": os.environ.get("CURSOR_API_KEY", ""),
            "PATH": os.pathsep.join(filter(None, [_find_rg_dir(), os.environ.get("PATH", "")])),
        },
    },
}


def _providers_file() -> Path:
    return DB_DIR / "providers.json"


def load_providers() -> dict:
    """Load providers: built-in + user overrides from providers.json.

    When a custom provider overrides a built-in one, it inherits supports_skills
    from the built-in if not explicitly set (so claude-z stays skill-capable even
    if the custom entry in providers.json doesn't repeat the flag).
    """
    providers = dict(BUILTIN_PROVIDERS)
    user_file = _providers_file()
    if user_file.exists():
        try:
            with open(user_file) as f:
                custom = json.load(f)
            for name, info in custom.items():
                if name in providers and "supports_skills" not in info:
                    info = dict(info)
                    info["supports_skills"] = providers[name].get("supports_skills", False)
                providers[name] = info
        except (json.JSONDecodeError, OSError):
            pass
    return providers


def save_provider(name: str, cmd: str, description: str = "", env: dict = None):
    """Save a custom provider to providers.json."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    user_file = _providers_file()
    custom = {}
    if user_file.exists():
        try:
            with open(user_file) as f:
                custom = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    entry = {"cmd": cmd, "description": description}
    if env:
        entry["env"] = env
    custom[name] = entry
    with open(user_file, "w") as f:
        json.dump(custom, f, indent=2)


def remove_provider(name: str) -> bool:
    """Remove a custom provider from providers.json."""
    user_file = _providers_file()
    if not user_file.exists():
        return False
    try:
        with open(user_file) as f:
            custom = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
    if name not in custom:
        return False
    del custom[name]
    with open(user_file, "w") as f:
        json.dump(custom, f, indent=2)
    return True


def build_cmd(provider: str, prompt: str, skip_permissions: bool = False, session_id: str = None, model: str = None, system_prompt: str = None):
    """Build the full command list for a provider + prompt."""
    providers = load_providers()
    if provider in providers:
        template = providers[provider]["cmd"]
    else:
        template = f"{provider} {{prompt}}"
    marker = "\x00PROMPT\x00"
    parts = template.replace("{prompt}", marker).split()
    cmd = [prompt if p == marker else p for p in parts]
    # Insert extra flags before the prompt argument
    extras = []
    if model:
        extras += ["--model", model]
    if session_id:
        extras += ["--resume", session_id]
    if system_prompt and providers.get(provider, {}).get("supports_skills", False):
        # Pass worker system prompt at true system level (replaces AGENTS.md/CLAUDE.md).
        extras += ["--system-prompt", system_prompt]
    if skip_permissions:
        # Provider-specific "skip permissions" flags:
        # - Claude Code: --dangerously-skip-permissions
        # - Codex CLI:  --dangerously-bypass-approvals-and-sandbox
        if provider == "codex":
            extras.append("--dangerously-bypass-approvals-and-sandbox")
        elif providers.get(provider, {}).get("supports_skills", False):
            extras.append("--dangerously-skip-permissions")
    if extras:
        # Avoid duplicating simple flags already present in provider template.
        # Note: --system-prompt and --model take values, so skip simple dedup for them.
        deduped = []
        i = 0
        while i < len(extras):
            flag = extras[i]
            if flag in ("--system-prompt", "--model", "--resume") and i + 1 < len(extras):
                deduped += [flag, extras[i + 1]]
                i += 2
            elif flag not in cmd:
                deduped.append(flag)
                i += 1
            else:
                i += 1
        prompt_idx = cmd.index(prompt)
        cmd[prompt_idx:prompt_idx] = deduped
    return cmd


def get_provider_env(provider: str) -> dict:
    """Get extra environment variables for a provider (merged with current env)."""
    providers = load_providers()
    extra = providers.get(provider, {}).get("env", {})
    if not extra:
        return os.environ.copy()
    env = os.environ.copy()
    # Skip empty values — don't override existing env vars with empty strings
    env.update({k: v for k, v in extra.items() if v})
    return env


def _parse_frontmatter(path: Path) -> dict:
    """Parse YAML-style frontmatter (---...---) from a markdown file."""
    try:
        content = path.read_text(encoding="utf-8-sig")  # utf-8-sig handles BOM
    except (UnicodeDecodeError, OSError):
        try:
            content = path.read_text(encoding="cp1251")
        except (UnicodeDecodeError, OSError):
            return {}
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    result = {}
    for line in content[3:end].splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def get_skills(working_dir: str = None) -> list:
    """Return list of available Claude Code skills from ~/.claude/commands/ and plugins.

    Each item: {name, description, argument_hint, source}
    Skills are invoked as /skill-name [args] when passed as a task prompt to Claude Code.
    Only relevant for providers with supports_skills=True (claude, claude-z).
    """
    skills = []
    seen = set()

    def _add_from_dir(dir_path: Path, source: str):
        """Scan dir_path for skill definitions in two layouts:
        - Flat:  <dir>/<skill-name>.md        (name = file stem)
        - Subdir: <dir>/<skill-name>/<any>.md  (name = subdirectory name)
        """
        if not dir_path.is_dir():
            return
        # Flat .md files directly in the directory
        for cmd_file in sorted(dir_path.glob("*.md")):
            if cmd_file.name.lower() == "readme.md":
                continue
            name = cmd_file.stem
            if name.upper() == "SKILL":
                continue  # this is a subdir-style file, skip here
            if name in seen:
                continue
            seen.add(name)
            fm = _parse_frontmatter(cmd_file)
            skills.append({
                "name": name,
                "description": fm.get("description", ""),
                "argument_hint": fm.get("argument-hint", ""),
                "source": source,
            })
        # Subdir-style: <dir>/<skill-name>/*.md (Claude uses directory name as skill name)
        for sub in sorted(dir_path.iterdir()):
            if not sub.is_dir():
                continue
            if sub.name.endswith(".disabled"):
                continue
            md_files = sorted(sub.glob("*.md"))
            if not md_files:
                continue
            name = sub.name
            if name in seen:
                continue
            seen.add(name)
            fm = _parse_frontmatter(md_files[0])
            skills.append({
                "name": name,
                "description": fm.get("description", ""),
                "argument_hint": fm.get("argument-hint", ""),
                "source": source,
            })

    # Global user commands/skills (~/.claude/commands/ and ~/.claude/skills/)
    _add_from_dir(Path.home() / ".claude" / "commands", "user")
    _add_from_dir(Path.home() / ".claude" / "skills", "user")

    # Plugin commands — scan all directories named "commands" under ~/.claude/plugins/
    plugins_dir = Path.home() / ".claude" / "plugins"
    if plugins_dir.is_dir():
        for cmd_dir in sorted(plugins_dir.rglob("commands")):
            if cmd_dir.is_dir():
                plugin_name = cmd_dir.parent.name
                _add_from_dir(cmd_dir, f"plugin:{plugin_name}")

    # Project-local commands/skills
    if working_dir:
        _add_from_dir(Path(working_dir) / ".claude" / "commands", "local")
        _add_from_dir(Path(working_dir) / ".claude" / "skills", "local")

    return skills


def _claude_user_skill_roots() -> list[tuple[str, Path]]:
    """Return mutable user skill roots: ~/.claude/commands and ~/.claude/skills."""
    base = Path.home() / ".claude"
    return [
        ("commands", base / "commands"),
        ("skills", base / "skills"),
    ]


def ensure_skill_dirs() -> None:
    """Ensure mutable user skill directories exist."""
    for _, root in _claude_user_skill_roots():
        root.mkdir(parents=True, exist_ok=True)


def _is_under_skill_roots(path: Path) -> bool:
    """Check that path is under one of mutable user skill roots."""
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for _, root in _claude_user_skill_roots():
        try:
            if resolved == root.resolve() or root.resolve() in resolved.parents:
                return True
        except OSError:
            continue
    return False


def _pick_skill_frontmatter_source(path: Path) -> Optional[Path]:
    """Pick markdown file used to read skill metadata for file/dir entries."""
    if path.is_file():
        return path
    if path.is_dir():
        md_files = sorted(path.glob("*.md"))
        if md_files:
            return md_files[0]
    return None


def list_managed_user_skills() -> list[dict]:
    """Return mutable user skills with filesystem paths and enable/disable state."""
    rows: list[dict] = []
    seen: set[str] = set()

    def _append_row(name: str, root_name: str, source_path: Path, enabled: bool, layout: str):
        dedupe_key = f"{root_name}:{name}:{layout}:{source_path.name}"
        if dedupe_key in seen:
            return
        seen.add(dedupe_key)
        fm_source = _pick_skill_frontmatter_source(source_path)
        fm = _parse_frontmatter(fm_source) if fm_source else {}
        rows.append(
            {
                "name": name,
                "description": fm.get("description", ""),
                "argument_hint": fm.get("argument-hint", ""),
                "source": "user",
                "location": root_name,
                "layout": layout,
                "enabled": enabled,
                "path": str(source_path.resolve()),
            }
        )

    for root_name, root in _claude_user_skill_roots():
        if not root.is_dir():
            continue

        for item in sorted(root.iterdir()):
            if item.is_file():
                filename = item.name
                low = filename.lower()
                if low == "readme.md":
                    continue
                if low.endswith(".md"):
                    stem = item.stem
                    if stem.upper() == "SKILL":
                        continue
                    _append_row(stem, root_name, item, True, "file")
                    continue
                if low.endswith(".md.disabled"):
                    stem = filename[: -len(".md.disabled")]
                    if stem and stem.upper() != "SKILL":
                        _append_row(stem, root_name, item, False, "file")
                    continue

            if item.is_dir():
                dirname = item.name
                is_disabled = dirname.endswith(".disabled")
                name = dirname[: -len(".disabled")] if is_disabled else dirname
                if not name:
                    continue
                md_files = sorted(item.glob("*.md"))
                if not md_files:
                    continue
                _append_row(name, root_name, item, not is_disabled, "directory")

    rows.sort(key=lambda x: (x["name"].lower(), x["location"], x["layout"]))
    return rows


def _validate_mutable_skill_path(path: str) -> Path:
    raw_text = str(path or "").strip()
    if not raw_text:
        raise ValueError("path is required")
    raw = Path(raw_text)
    resolved = raw.resolve()
    if not _is_under_skill_roots(resolved):
        raise ValueError("Path is outside of mutable skill directories")
    if not resolved.exists():
        raise ValueError("Skill path does not exist")
    return resolved


def set_skill_enabled(path: str, enabled: bool) -> dict:
    """Enable/disable a mutable user skill by renaming file/dir."""
    target = _validate_mutable_skill_path(path)
    name = target.name
    changed = False

    if target.is_file():
        if name.endswith(".md.disabled") and enabled:
            new_path = target.with_name(name[: -len(".disabled")])
            target.rename(new_path)
            target = new_path
            changed = True
        elif name.endswith(".md") and not enabled:
            new_path = target.with_name(name + ".disabled")
            target.rename(new_path)
            target = new_path
            changed = True
    elif target.is_dir():
        if name.endswith(".disabled") and enabled:
            new_path = target.with_name(name[: -len(".disabled")])
            target.rename(new_path)
            target = new_path
            changed = True
        elif (not name.endswith(".disabled")) and not enabled:
            new_path = target.with_name(name + ".disabled")
            target.rename(new_path)
            target = new_path
            changed = True
    else:
        raise ValueError("Unsupported skill path type")

    return {"path": str(target.resolve()), "enabled": bool(enabled), "changed": changed}


# Projects root — optional directory whose subdirectories are offered as project choices
PROJECTS_ROOT = os.environ.get("PP_PROJECTS_ROOT", "")

# Optional password required to create tasks via Telegram bot
TASK_PASSWORD = os.environ.get("PP_TASK_PASSWORD", "")

# Server
HOST = os.environ.get("PP_HOST", "127.0.0.1")
PORT = int(os.environ.get("PP_PORT", "8420"))
APP_TIMEZONE = os.environ.get("PP_TIMEZONE", "UTC")
