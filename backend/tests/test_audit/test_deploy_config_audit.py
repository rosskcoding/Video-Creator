"""
Deploy + repo hardening audit tests.

These tests assert the presence of security/operational fixes in repo-level
deployment artifacts (shell scripts, Caddy config, etc.) to prevent regressions.
"""

from pathlib import Path
import re


# This file lives at: <repo>/backend/tests/test_audit/test_deploy_config_audit.py
# repo root is therefore parents[3].
REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_deploy_sh_does_not_source_env_or_mask_pull_errors() -> None:
    text = _read("deploy/deploy.sh")

    # .env must be treated as data, not code
    assert 'source "$ENV_FILE"' not in text

    # Don't mask pull failures with `|| true`
    assert " pull || true" not in text

    # Health check must not be a loose grep
    assert 'grep -q "healthy"' not in text
    assert "docker inspect --format" in text


def test_backup_sh_marks_env_backup_as_plaintext_and_avoids_source() -> None:
    text = _read("deploy/backup.sh")

    assert 'source "$ENV_FILE"' not in text
    assert "plaintext" in text.lower()
    assert "chmod 600" in text


def test_restore_sh_avoids_source() -> None:
    text = _read("deploy/restore.sh")
    assert 'source "$ENV_FILE"' not in text


def test_caddyfile_has_modern_security_headers_and_no_x_xss_protection() -> None:
    text = _read("Caddyfile")

    assert "Content-Security-Policy" in text
    assert "Permissions-Policy" in text
    assert "Cross-Origin-Opener-Policy" in text
    assert "Cross-Origin-Embedder-Policy" in text

    # Deprecated header should not be present
    assert "X-XSS-Protection" not in text


def test_deployment_md_discourages_curl_pipe_bash() -> None:
    text = _read("DEPLOYMENT.md")

    # Hard ban: any `curl ... | bash` examples (pipe-to-shell)
    assert re.search(r"curl[^\n]*\|\s*bash", text) is None

    # Preferred flow: download → review → run
    assert "-o setup-server.sh" in text
    assert "less setup-server.sh" in text


def test_agents_use_safe_subprocess_and_dotenv_loading_pattern() -> None:
    video_creator = _read("agents/video_creator.py")
    narrator = _read("agents/narrator.py")
    root_workflow = _read("workflow.py")

    # Avoid shell parsing / quoting pitfalls
    assert "shlex.split" not in video_creator

    # Prefer JSON structure; do not use pickle (RCE risk)
    assert "structure.json" in video_creator
    assert "import pickle" not in video_creator
    assert "pickle.load" not in video_creator
    assert "pickle.dump" not in video_creator
    assert "import pickle" not in root_workflow
    assert "pickle.load" not in root_workflow
    assert "pickle.dump" not in root_workflow

    # dotenv should not be loaded per-slide/per-call
    load_pos = narrator.find("load_dotenv()")
    narrate_pos = narrator.find("async def narrate")
    assert load_pos != -1 and narrate_pos != -1 and load_pos < narrate_pos

    # Must not block event loop with sync I/O
    assert "run_in_executor" in narrator


