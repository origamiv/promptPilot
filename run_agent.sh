#!/usr/bin/env bash
# run_agent.sh — unified agent launcher
# Usage: ./run_agent.sh --agent <shortname> [options] [extra agent args...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${SCRIPT_DIR}/.venv/bin/python"
HELPER="${SCRIPT_DIR}/run_agent_helper.py"

# ── Defaults ────────────────────────────────────────────────────────────────
AGENT_SHORTNAME=""
PROMPT=""
SYSTEM_PROMPT=""
SYSTEM_PROMPT_FILE=""
YOLO=0
MODEL=""
WORKDIR=""
EXTRA_ARGS=()

# ── Argument parsing ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --agent)               AGENT_SHORTNAME="$2"; shift 2 ;;
        --prompt)              PROMPT="$2";           shift 2 ;;
        --system-prompt)       SYSTEM_PROMPT="$2";    shift 2 ;;
        --system-prompt-file)  SYSTEM_PROMPT_FILE="$2"; shift 2 ;;
        --yolo)                YOLO=1;                shift   ;;
        --model)               MODEL="$2";            shift 2 ;;
        --workdir)             WORKDIR="$2";          shift 2 ;;
        *)                     EXTRA_ARGS+=("$1");    shift   ;;
    esac
done

if [[ -z "$AGENT_SHORTNAME" ]]; then
    echo "Error: --agent <shortname> is required" >&2
    echo "Usage: $0 --agent <shortname> [--prompt <text>] [--system-prompt <text>]" >&2
    echo "          [--system-prompt-file <path>] [--yolo] [--model <model>]" >&2
    echo "          [--workdir <path>] [extra agent args...]" >&2
    exit 1
fi

# ── Load .env ────────────────────────────────────────────────────────────────
load_env() {
    local file="$1"
    [[ -f "$file" ]] || return 0
    while IFS='=' read -r key val; do
        [[ -z "$key" || "$key" == \#* ]] && continue
        key="${key// /}"
        [[ -z "${!key+x}" ]] && export "$key"="$val"
    done < "$file"
}
load_env "${SCRIPT_DIR}/.env.local"
load_env "${SCRIPT_DIR}/.env"

CLAUDE_EXE="${PP_CLAUDE_EXE:-/usr/local/bin/claude}"

# ── Fetch agent info from DB ─────────────────────────────────────────────────
HELPER_FLAGS=("--shortname" "$AGENT_SHORTNAME")
# Write claude_credentials to file if needed
HELPER_FLAGS+=("--write-credentials")

AGENT_VARS="$("$PYTHON" "$HELPER" "${HELPER_FLAGS[@]}")"
if [[ $? -ne 0 ]]; then
    echo "$AGENT_VARS" >&2
    exit 1
fi

eval "$AGENT_VARS"

PROVIDER="${AGENT_PROVIDER:-$AGENT_SHORTNAME}"

# ── System prompt ─────────────────────────────────────────────────────────────
if [[ -n "$SYSTEM_PROMPT_FILE" ]]; then
    if [[ ! -f "$SYSTEM_PROMPT_FILE" ]]; then
        echo "Error: system prompt file not found: $SYSTEM_PROMPT_FILE" >&2
        exit 1
    fi
    SYSTEM_PROMPT="$(cat "$SYSTEM_PROMPT_FILE")"
fi

# ── --yolo → provider-specific flag ──────────────────────────────────────────
YOLO_FLAG=""
if [[ "$YOLO" -eq 1 ]]; then
    case "$PROVIDER" in
        codex)
            YOLO_FLAG="--dangerously-bypass-approvals-and-sandbox"
            ;;
        claude|claude-z|openclaude)
            YOLO_FLAG="--dangerously-skip-permissions"
            ;;
        *)
            echo "Warning: --yolo not supported for provider '$PROVIDER', ignoring" >&2
            ;;
    esac
fi

# ── Build command ─────────────────────────────────────────────────────────────
CMD=()

case "$PROVIDER" in
    claude|claude-z|openclaude)
        CMD=("$CLAUDE_EXE" "-p" "--verbose" "--output-format" "stream-json")
        [[ -n "$MODEL" ]]         && CMD+=("--model" "$MODEL")
        [[ -n "$SYSTEM_PROMPT" ]] && CMD+=("--system-prompt" "$SYSTEM_PROMPT")
        [[ -n "$YOLO_FLAG" ]]     && CMD+=("$YOLO_FLAG")
        CMD+=("${EXTRA_ARGS[@]}")
        [[ -n "$PROMPT" ]]        && CMD+=("$PROMPT")
        ;;

    codex)
        CMD=("codex" "exec")
        # codex already has --dangerously-bypass-approvals-and-sandbox in default template;
        # add only if --yolo was explicitly requested and it's not a duplicate
        [[ -n "$YOLO_FLAG" ]]     && CMD+=("$YOLO_FLAG")
        [[ -n "$MODEL" ]]         && CMD+=("--model" "$MODEL")
        CMD+=("${EXTRA_ARGS[@]}")
        [[ -n "$PROMPT" ]]        && CMD+=("$PROMPT")
        ;;

    qwen)
        CMD=("qwen" "-p")
        [[ -n "$MODEL" ]]         && CMD+=("--model" "$MODEL")
        CMD+=("${EXTRA_ARGS[@]}")
        [[ -n "$PROMPT" ]]        && CMD+=("$PROMPT")
        ;;

    cursor)
        CMD=("cursor-agent" "--print" "--output-format" "text" "-f")
        [[ -n "$MODEL" ]]         && CMD+=("--model" "$MODEL")
        CMD+=("${EXTRA_ARGS[@]}")
        [[ -n "$PROMPT" ]]        && CMD+=("$PROMPT")
        ;;

    *)
        # Generic: treat provider as executable name
        CMD=("$PROVIDER")
        [[ -n "$MODEL" ]]         && CMD+=("--model" "$MODEL")
        [[ -n "$SYSTEM_PROMPT" ]] && CMD+=("--system-prompt" "$SYSTEM_PROMPT")
        [[ -n "$YOLO_FLAG" ]]     && CMD+=("$YOLO_FLAG")
        CMD+=("${EXTRA_ARGS[@]}")
        [[ -n "$PROMPT" ]]        && CMD+=("$PROMPT")
        ;;
esac

# ── Working directory ─────────────────────────────────────────────────────────
if [[ -n "$WORKDIR" ]]; then
    cd "$WORKDIR"
fi

# ── Run ───────────────────────────────────────────────────────────────────────
exec "${CMD[@]}"
