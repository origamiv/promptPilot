#!/usr/bin/env python3
"""Helper for run_agent.sh — fetches agent info from DB and prints shell variables."""

import argparse
import json
import os
import sys


def load_env(path: str):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shortname", required=True)
    parser.add_argument("--write-credentials", action="store_true",
                        help="Write claude_credentials to ~/.claude/.credentials.json")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    load_env(os.path.join(script_dir, ".env.local"))
    load_env(os.path.join(script_dir, ".env"))

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        print("ERROR: psycopg not available", file=sys.stderr)
        sys.exit(1)

    db_kwargs = dict(
        host=os.environ.get("PP_DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("PP_DB_PORT", "5432")),
        dbname=os.environ.get("PP_DB_DATABASE", ""),
        user=os.environ.get("PP_DB_USER", ""),
        password=os.environ.get("PP_DB_PASSWORD", ""),
        sslmode=os.environ.get("PP_DB_SSLMODE", "prefer"),
    )
    schema = os.environ.get("PP_DB_SCHEMA", "public")

    try:
        conn = psycopg.connect(**db_kwargs, row_factory=dict_row)
    except Exception as e:
        print(f"ERROR: DB connection failed: {e}", file=sys.stderr)
        sys.exit(1)

    with conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT a.id, a.shortname AS provider,
                       aa.id       AS account_id,
                       aa.token,
                       aa.login_mode,
                       aa.claude_credentials
                FROM {schema}.agents a
                LEFT JOIN {schema}.agents_accounts aa
                       ON aa.agent_id = a.id
                      AND aa.is_active = TRUE
                      AND aa.status = 1
                WHERE a.shortname = %s
                  AND (a.deleted_at IS NULL OR a.deleted_at > NOW())
                ORDER BY aa.id ASC
                LIMIT 1
            """, (args.shortname,))
            row = cur.fetchone()

    conn.close()

    if not row:
        print(f"ERROR: agent '{args.shortname}' not found or has no active account", file=sys.stderr)
        sys.exit(1)

    provider     = row["provider"] or args.shortname
    token        = row["token"] or ""
    login_mode   = row["login_mode"] or "token"
    claude_creds = row["claude_credentials"]

    env_vars = {}

    if provider in ("claude", "claude-z"):
        if login_mode == "claude_credentials" and claude_creds:
            if args.write_credentials:
                creds_dir = os.path.expanduser("~/.claude")
                os.makedirs(creds_dir, exist_ok=True)
                creds_path = os.path.join(creds_dir, ".credentials.json")
                data = claude_creds if isinstance(claude_creds, dict) else json.loads(claude_creds)
                with open(creds_path, "w") as f:
                    json.dump(data, f)
        else:
            if token:
                env_vars["ANTHROPIC_API_KEY"] = token

    elif provider == "openclaude":
        if token:
            env_vars["ANTHROPIC_API_KEY"] = token
        base_url = os.environ.get("PP_OPENCLAUDE_BASE_URL", "")
        if not base_url:
            print("ERROR: PP_OPENCLAUDE_BASE_URL is not set in .env", file=sys.stderr)
            sys.exit(1)
        env_vars["ANTHROPIC_BASE_URL"] = base_url

    elif provider == "codex":
        if token:
            env_vars["OPENAI_API_KEY"] = token

    elif provider == "cursor":
        if token:
            env_vars["CURSOR_API_KEY"] = token

    elif provider == "qwen":
        if token:
            env_vars["DASHSCOPE_API_KEY"] = token

    else:
        if token:
            env_vars["OPENAI_API_KEY"] = token

    import shlex
    print(f"AGENT_PROVIDER={shlex.quote(provider)}")
    for k, v in env_vars.items():
        print(f"{k}={shlex.quote(v)}")


if __name__ == "__main__":
    main()
