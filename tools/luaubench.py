#!/usr/bin/env python3
"""Luau CodeBench v0.3.0 runner.

Commands:
  doctor       Check local Luau tools.
  prepare      Create a clean model-facing workspace.
  run-model    Run a model through an OpenAI-compatible chat-completions endpoint.
  evaluate     Evaluate an already-finished workspace.

The automated adapter speaks the common OpenAI-compatible Chat Completions
protocol. Providers only configure base URL, authentication, and model ID.
The benchmark never requires a provider model-list endpoint during a run.
"""
from __future__ import annotations

import argparse
import copy
import difflib
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "tasks"
RUNS = ROOT / "runs"
DEFAULT_ENV_FILE = ROOT / ".env"


def load_dotenv(path: Path) -> None:
    """Load a small dotenv file without overriding variables already in the shell."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        if key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] == '"':
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = value[1:-1]
        elif len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        os.environ[key] = value


def dotenv_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def save_dotenv_values(path: Path, updates: dict[str, str]) -> None:
    """Update selected keys while preserving all other .env lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(updates)
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if key in remaining:
            output.append(f"{key}={dotenv_quote(remaining.pop(key))}")
        else:
            output.append(line)
    if output and output[-1].strip():
        output.append("")
    for key, value in remaining.items():
        output.append(f"{key}={dotenv_quote(value)}")
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    for key, value in updates.items():
        os.environ[key] = value


def get_env_file(args: argparse.Namespace) -> Path:
    chosen = getattr(args, "env_file", None) or os.getenv("LUAUBENCH_ENV_FILE")
    return Path(chosen).expanduser().resolve() if chosen else DEFAULT_ENV_FILE


def get_http_backend(args: argparse.Namespace) -> str:
    return (getattr(args, "http_backend", None) or os.getenv("LUAUBENCH_HTTP_BACKEND") or "auto").strip()


def get_model_id(args: argparse.Namespace) -> str:
    model = getattr(args, "model", None) or os.getenv("LUAUBENCH_MODEL")
    if not model:
        raise SystemExit("No model selected. Run `python tools/luaubench.py menu` or set LUAUBENCH_MODEL in .env.")
    return str(model).strip()


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_task(task_name: str) -> tuple[Path, dict[str, Any]]:
    task_dir = TASKS / task_name
    if not task_dir.is_dir():
        raise SystemExit(f"Unknown task: {task_name}")
    manifest = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    return task_dir, manifest


def safe_resolve(root: Path, user_path: str) -> Path:
    root = root.resolve()
    candidate = (root / user_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Path escapes the benchmark workspace") from exc
    return candidate


def snapshot_tree(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        out[rel] = path.read_text(encoding="utf-8", errors="replace")
    return out


def diff_stats(before: dict[str, str], root: Path) -> dict[str, Any]:
    after = snapshot_tree(root)
    added = sorted(set(after) - set(before))
    deleted = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    added_lines = 0
    removed_lines = 0
    for path in changed:
        a = before[path].splitlines()
        b = after[path].splitlines()
        sm = difflib.SequenceMatcher(None, a, b)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag in {"replace", "delete"}:
                removed_lines += i2 - i1
            if tag in {"replace", "insert"}:
                added_lines += j2 - j1
    for path in added:
        added_lines += len(after[path].splitlines())
    for path in deleted:
        removed_lines += len(before[path].splitlines())
    return {
        "files_added": added,
        "files_deleted": deleted,
        "files_changed": changed,
        "files_changed_count": len(added) + len(deleted) + len(changed),
        "lines_added": added_lines,
        "lines_removed": removed_lines,
    }


def resolve_executable(explicit: str | None, names: tuple[str, ...]) -> str | None:
    if explicit:
        p = Path(explicit).expanduser()
        return str(p) if p.exists() else None
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def run_process(exe: str, args: list[str], cwd: Path, timeout: int = 120) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [exe, *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_sec": round(time.monotonic() - started, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": "Process timed out",
            "duration_sec": round(time.monotonic() - started, 3),
            "timeout": True,
        }


def parse_markers(output: str) -> tuple[int, int, list[str], list[str]]:
    passed = re.findall(r"^\[PASS\]\s+(.+)$", output, flags=re.M)
    failed = re.findall(r"^\[FAIL\]\s+(.+)$", output, flags=re.M)
    return len(passed), len(passed) + len(failed), passed, failed


def prepare_workspace(task_name: str, output: Path) -> None:
    task_dir, manifest = load_task(task_name)
    public_dir = task_dir / "public"
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"Output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(public_dir, output, dirs_exist_ok=True)
    (output / "SYSTEM_PROMPT.md").write_text((ROOT / "SYSTEM_PROMPT.md").read_text(encoding="utf-8"), encoding="utf-8")
    clean = copy.deepcopy(manifest)
    clean.pop("hidden", None)
    (output / ".benchmark_manifest.json").write_text(json.dumps(clean, indent=2) + "\n", encoding="utf-8")


def evaluate_task(task_name: str, workspace: Path, luau: str, luau_analyze: str | None, before: dict[str, str] | None) -> dict[str, Any]:
    if task_name != "T01_Cooldown":
        raise SystemExit(f"Official scoring is currently implemented only for T01_Cooldown; {task_name} is a prototype fixture.")
    task_dir, manifest = load_task(task_name)
    workspace = workspace.resolve()
    if (workspace / "hidden").exists():
        raise SystemExit("Refusing to evaluate: hidden/ exists inside model workspace")

    hidden_test_source = resolve_hidden_test(task_name, task_dir)
    evaluator = Path(tempfile.mkdtemp(prefix=f"luaubench_{task_name}_"))
    try:
        shutil.copytree(workspace / "project", evaluator / "project")
        (evaluator / "hidden").mkdir(parents=True, exist_ok=True)
        shutil.copy2(hidden_test_source, evaluator / "hidden" / "HiddenTests.lua")
        shutil.copytree(task_dir / "public" / "tests", evaluator / "public_tests")

        hidden_proc = run_process(luau, [str(evaluator / "hidden" / "HiddenTests.lua")], evaluator)
        public_proc = run_process(luau, [str(evaluator / "public_tests" / "PublicTests.lua")], evaluator)

        h_pass, h_total, h_names, h_failed = parse_markers(hidden_proc["stdout"] + "\n" + hidden_proc["stderr"])
        p_pass, p_total, p_names, p_failed = parse_markers(public_proc["stdout"] + "\n" + public_proc["stderr"])

        static_proc = None
        static_score = 0.0
        module_path = evaluator / "project" / "src" / "ReplicatedStorage" / "CodeBench" / "CooldownService.lua"
        if luau_analyze:
            static_proc = run_process(luau_analyze, [str(module_path)], evaluator)
            static_score = 10.0 if static_proc["ok"] else 0.0

        changes = diff_stats(before or {}, workspace)
        source = module_path.read_text(encoding="utf-8", errors="replace") if module_path.exists() else ""
        required = [
            "function CooldownService.new",
            ":Start(",
            ":IsOnCooldown(",
            ":GetRemaining(",
            ":Clear(",
            ":ClearAll(",
        ]
        api_ok = all(piece in source for piece in required)
        allowed = {"project/src/ReplicatedStorage/CodeBench/CooldownService.lua", "SYSTEM_PROMPT.md", ".benchmark_manifest.json"}
        changed_code_paths = set(changes["files_added"]) | set(changes["files_deleted"]) | set(changes["files_changed"])
        changed_code_paths -= {"SYSTEM_PROMPT.md", ".benchmark_manifest.json"}
        hygiene_ok = changed_code_paths <= allowed - {"SYSTEM_PROMPT.md", ".benchmark_manifest.json"}
        no_forbidden_patterns = not re.search(r"\bTODO\b|task\.spawn|task\.delay|while\s+true\s+do", source)
        invariant_score = 0.0
        invariant_score += 10.0 if api_ok else 0.0
        invariant_score += 5.0 if hygiene_ok else 0.0
        invariant_score += 5.0 if no_forbidden_patterns else 0.0

        score = 0.0
        score += 60.0 * (h_pass / h_total if h_total else 0.0)
        score += invariant_score
        score += 10.0 * (p_pass / p_total if p_total else 0.0)
        score += static_score
        return {
            "task": task_name,
            "task_version": manifest.get("version"),
            "score": round(score, 2),
            "score_breakdown": {
                "hidden_functional": round(60.0 * (h_pass / h_total if h_total else 0.0), 2),
                "invariants": round(invariant_score, 2),
                "public_regression": round(10.0 * (p_pass / p_total if p_total else 0.0), 2),
                "static": round(static_score, 2),
            },
            "hidden": {
                "passed": h_pass,
                "total": h_total,
                "passed_names": h_names,
                "failed_names": h_failed,
                "process": hidden_proc,
            },
            "public": {
                "passed": p_pass,
                "total": p_total,
                "passed_names": p_names,
                "failed_names": p_failed,
                "process": public_proc,
            },
            "static": static_proc,
            "diff": changes,
            "generated_at": now_iso(),
        }
    finally:
        shutil.rmtree(evaluator, ignore_errors=True)


@dataclass
class ModelConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    temperature: float | None
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer"


class OpenAICompatibleClient:
    """Small OpenAI-compatible client with a provider-safe HTTP backend.

    The benchmark speaks one wire protocol so model identity is the variable under
    test. Providers configure only URL/auth/model. On Windows, ``auto`` prefers
    the system curl.exe because some API gateways/WAFs reject Python's default
    urllib client signature even though their documented API supports curl and
    coding agents. This is not a benchmark scoring path; it is only transport.
    """
    def __init__(self, config: ModelConfig, http_backend: str = "auto", curl_path: str | None = None):
        self.provider = config.provider
        self.base_url = config.base_url.rstrip("/")
        self.endpoint = self.base_url + "/chat/completions"
        self.api_key = config.api_key
        self.model = config.model
        self.temperature = config.temperature
        self.auth_header = config.auth_header
        self.auth_prefix = config.auth_prefix
        self.retry_count = 0
        self.retry_sleep_sec = 0.0
        self.curl_path = curl_path or shutil.which("curl.exe") or shutil.which("curl")
        if http_backend not in {"auto", "urllib", "curl"}:
            raise ValueError("http_backend must be auto, urllib, or curl")
        if http_backend == "curl" and not self.curl_path:
            raise RuntimeError("curl backend selected but curl executable was not found")
        if http_backend == "auto":
            self.http_backend = "curl" if self.curl_path and os.name == "nt" else "urllib"
        else:
            self.http_backend = http_backend

    def _headers(self) -> dict[str, str]:
        auth_value = self.api_key if not self.auth_prefix else f"{self.auth_prefix} {self.api_key}"
        return {
            self.auth_header: auth_value,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request_json_urllib(self, url: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))

    def _request_json_curl(self, url: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.curl_path:
            raise RuntimeError("curl backend selected but curl executable was not found")
        body_file = None
        response_file = None
        try:
            response_file = tempfile.NamedTemporaryFile(mode="wb", suffix=".response", delete=False)
            response_file.close()

            # Use normal argv-based curl invocation instead of a curl config file.
            # This avoids Windows curl parsing/escaping differences (notably for
            # --write-out format strings containing %{http_code}).
            cmd = [
                self.curl_path,
                "--silent",
                "--show-error",
                "--connect-timeout", "20",
                "--max-time", "120",
                "--request", method,
                "--write-out", "%{http_code}",
                "--output", response_file.name,
                "--url", url,
            ]
            for key, value in self._headers().items():
                cmd.extend(["--header", f"{key}: {value}"])
            if payload is not None:
                body_file = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False)
                json.dump(payload, body_file, ensure_ascii=False)
                body_file.close()
                cmd.extend(["--data-binary", f"@{body_file.name}"])

            proc = subprocess.run(
                cmd,
                text=True,
                capture_output=True,
                timeout=130,
                encoding="utf-8",
                errors="replace",
            )
            status_text = proc.stdout.strip()
            body = Path(response_file.name).read_text(encoding="utf-8", errors="replace")
            if not re.fullmatch(r"\d{3}", status_text):
                if proc.returncode != 0:
                    raise RuntimeError(f"curl failed with exit code {proc.returncode}: {proc.stderr.strip()}")
                raise RuntimeError(f"curl did not return an HTTP status code. stdout={status_text!r}, stderr={proc.stderr.strip()!r}")
            status = int(status_text)
            if status < 200 or status >= 300:
                exc = urllib.error.HTTPError(url, status, body, {}, None)
                # Stash the response body on the standard exception path.
                exc._luaubench_body = body  # type: ignore[attr-defined]
                raise exc
            try:
                return json.loads(body)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Provider returned non-JSON response (HTTP {status}): {body[:2000]!r}") from exc
        finally:
            if body_file is not None:
                try:
                    Path(body_file.name).unlink(missing_ok=True)
                except OSError:
                    pass
            if response_file is not None:
                try:
                    Path(response_file.name).unlink(missing_ok=True)
                except OSError:
                    pass

    def _request_json(self, url: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.http_backend == "curl":
            return self._request_json_curl(url, method, payload)
        return self._request_json_urllib(url, method, payload)

    def list_models(self) -> dict[str, Any]:
        return self._request_json(f"{self.base_url}/models")

    def check_model(self) -> dict[str, Any]:
        # Some providers expose /models/{id}; others only expose /models.
        # Try the specific endpoint first, then fall back to the collection.
        url = f"{self.base_url}/models/{urllib.parse.quote(self.model, safe='')}"
        try:
            return self._request_json(url)
        except urllib.error.HTTPError as exc:
            if exc.code not in {400, 404, 405}:
                raise
            models = self.list_models()
            data = models.get("data") if isinstance(models, dict) else None
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("id") == self.model:
                        return item
            raise

    def probe_basic_completion(self) -> dict[str, Any]:
        """Minimal inference probe without tools. This isolates endpoint/key/model
        availability from function-calling support.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Reply with exactly: READY"}],
            "max_tokens": 32,
            "temperature": 0,
        }
        return self._post_json_with_retries(self.endpoint, payload)

    def probe_tool_calling(self) -> dict[str, Any]:
        """Perform a real tool-calling completion to verify the benchmark agent path.

        Uses a larger output budget than the original 64-token probe because
        reasoning models may spend completion tokens on internal reasoning before
        emitting the tool call.
        """
        probe_tool = {
            "type": "function",
            "function": {
                "name": "__luaubench_probe",
                "description": "Internal benchmark connectivity probe. Call it exactly once.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": "Call the __luaubench_probe tool exactly once. Do not explain."}
            ],
            "tools": [probe_tool],
            "tool_choice": "required",
            "max_tokens": 1024,
            "temperature": 0,
        }
        return self._post_json_with_retries(self.endpoint, payload)

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        return self._post_json_with_retries(self.endpoint, payload)

    def _post_json_with_retries(self, url: str, payload: dict[str, Any], max_retries: int = 4) -> dict[str, Any]:
        transient_codes = {408, 409, 425, 429, 500, 502, 503, 504}
        last_error: urllib.error.HTTPError | None = None
        for attempt in range(max_retries + 1):
            try:
                return self._request_json(url, "POST", payload)
            except urllib.error.HTTPError as exc:
                if exc.code not in transient_codes or attempt >= max_retries:
                    raise
                last_error = exc
                delay = min(30.0, 2.0 ** attempt)
                self.retry_count += 1
                self.retry_sleep_sec += delay
                time.sleep(delay)
        assert last_error is not None
        raise last_error


def resolve_provider(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    """Resolve one universal OpenAI-compatible endpoint from CLI/.env settings.

    Provider is only a label used in result paths; it never selects a provider preset.
    """
    provider_name = getattr(args, "provider", None) or os.getenv("LUAUBENCH_PROVIDER") or "custom"
    base_url = getattr(args, "base_url", None) or os.getenv("LUAUBENCH_BASE_URL")
    api_key = os.getenv("LUAUBENCH_API_KEY")
    auth_header = getattr(args, "auth_header", None) or os.getenv("LUAUBENCH_AUTH_HEADER") or "Authorization"
    auth_prefix = getattr(args, "auth_prefix", None)
    if auth_prefix is None:
        auth_prefix = os.getenv("LUAUBENCH_AUTH_PREFIX", "Bearer")

    if not base_url:
        raise SystemExit("LUAUBENCH_BASE_URL is missing. Configure .env or pass --base-url.")
    if not api_key:
        raise SystemExit("LUAUBENCH_API_KEY is missing. Configure .env or set the environment variable.")
    return "LUAUBENCH_API_KEY", {
        "provider": str(provider_name),
        "base_url": str(base_url).rstrip("/"),
        "auth_header": str(auth_header),
        "auth_prefix": str(auth_prefix),
    }


def private_tests_root() -> Path:
    raw = os.getenv("LUAUBENCH_PRIVATE_TESTS_DIR", "private-evaluator/tasks")
    path = Path(raw).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def resolve_hidden_test(task_name: str, task_dir: Path) -> Path:
    """Find private hidden test without requiring it to live in the public repository."""
    candidates = [
        private_tests_root() / task_name / "HiddenTests.lua",
        task_dir / "hidden" / "HiddenTests.lua",  # legacy developer checkout support
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    expected = private_tests_root() / task_name / "HiddenTests.lua"
    raise SystemExit(
        "Private hidden tests are not installed. Keep them outside the public repository and "
        "put the evaluator pack under 'private-evaluator/tasks/<TASK>/HiddenTests.lua'. "
        f"Missing: {expected}"
    )


def tool_specs() -> list[dict[str, Any]]:
    def fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {"type": "object", "properties": properties, "required": required},
            },
        }

    return [
        fn("list_files", "List files in the benchmark workspace.", {"path": {"type": "string", "description": "Directory path, usually '.'"}}, []),
        fn("read_file", "Read a UTF-8 text file from the workspace.", {"path": {"type": "string"}}, ["path"]),
        fn("search_files", "Search text across workspace files.", {"query": {"type": "string"}, "path": {"type": "string", "description": "Optional subdirectory"}}, ["query"]),
        fn("write_file", "Write a UTF-8 text file in the workspace.", {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
        fn("run_public_tests", "Run the public tests for the current task.", {}, []),
        fn("run_static_checks", "Run luau-analyze on the task module when available.", {}, []),
        fn("finish", "Declare the task complete. The benchmark will now run hidden tests.", {"summary": {"type": "string"}}, ["summary"]),
    ]


def tool_list_files(workspace: Path, rel: str) -> str:
    base = safe_resolve(workspace, rel)
    if not base.is_dir():
        return f"Not a directory: {rel}"
    result = []
    for p in sorted(base.rglob("*")):
        if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts:
            result.append(p.relative_to(workspace).as_posix())
            if len(result) >= 500:
                break
    return "\n".join(result) if result else "(no files)"


def tool_read_file(workspace: Path, rel: str) -> str:
    path = safe_resolve(workspace, rel)
    if not path.is_file():
        return f"File not found: {rel}"
    text = path.read_text(encoding="utf-8", errors="replace")
    return text if len(text) <= 30000 else text[:30000] + "\n...[truncated]"


def tool_search_files(workspace: Path, query: str, rel: str) -> str:
    base = safe_resolve(workspace, rel)
    hits = []
    for p in sorted(base.rglob("*")):
        if not p.is_file() or ".git" in p.parts or "__pycache__" in p.parts:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), 1):
            if query.lower() in line.lower():
                hits.append(f"{p.relative_to(workspace).as_posix()}:{line_no}: {line.strip()}")
                if len(hits) >= 200:
                    return "\n".join(hits) + "\n...[truncated]"
    return "\n".join(hits) if hits else "No matches."


def tool_write_file(workspace: Path, rel: str, content: str) -> str:
    if rel in {"", ".", ".."}:
        raise ValueError("Invalid path")
    path = safe_resolve(workspace, rel)
    if len(content) > 100000:
        raise ValueError("Refusing to write a file larger than 100k characters")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Wrote {rel} ({len(content)} chars)"


def tool_run_public_tests(workspace: Path, task_name: str, luau: str | None) -> str:
    if not luau:
        return "ERROR: luau executable is not configured."
    task_dir, _ = load_task(task_name)
    temp = Path(tempfile.mkdtemp(prefix="luaubench_public_"))
    try:
        shutil.copytree(workspace / "project", temp / "project")
        (temp / "tests").mkdir()
        shutil.copy2(task_dir / "public" / "tests" / "PublicTests.lua", temp / "tests" / "PublicTests.lua")
        return json.dumps(run_process(luau, [str(temp / "tests" / "PublicTests.lua")], temp), ensure_ascii=False)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def tool_run_static_checks(workspace: Path, luau_analyze: str | None) -> str:
    if not luau_analyze:
        return "ERROR: luau-analyze executable is not configured."
    module = workspace / "project" / "src" / "ReplicatedStorage" / "CodeBench" / "CooldownService.lua"
    return json.dumps(run_process(luau_analyze, [str(module)], workspace), ensure_ascii=False)


def execute_tool(name: str, args: dict[str, Any], workspace: Path, task_name: str, luau: str | None, luau_analyze: str | None) -> tuple[str, bool]:
    if name == "list_files":
        return tool_list_files(workspace, str(args.get("path", "."))), False
    if name == "read_file":
        return tool_read_file(workspace, str(args["path"])), False
    if name == "search_files":
        return tool_search_files(workspace, str(args["query"]), str(args.get("path", "."))), False
    if name == "write_file":
        return tool_write_file(workspace, str(args["path"]), str(args["content"])), False
    if name == "run_public_tests":
        return tool_run_public_tests(workspace, task_name, luau), False
    if name == "run_static_checks":
        return tool_run_static_checks(workspace, luau_analyze), False
    if name == "finish":
        return json.dumps({"finished": True, "summary": str(args.get("summary", ""))}), True
    raise ValueError(f"Unknown tool: {name}")


def run_model(args: argparse.Namespace) -> int:
    if args.task != "T01_Cooldown":
        raise SystemExit(f"Official scoring is currently implemented only for T01_Cooldown; {args.task} is a prototype fixture.")
    task_dir, manifest = load_task(args.task)
    resolve_hidden_test(args.task, task_dir)  # fail before any API usage if the private evaluator is missing
    api_key_env, provider_cfg = resolve_provider(args)
    args.provider = provider_cfg["provider"]
    args.model = get_model_id(args)
    run_id = args.run_id or time.strftime("%Y%m%d_%H%M%S")
    run_dir = (RUNS / args.task / args.provider / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    workspace = run_dir / "workspace"
    prepare_workspace(args.task, workspace)
    before = snapshot_tree(workspace)

    api_key = os.getenv(api_key_env)
    luau = resolve_executable(args.luau, ("luau", "luau.exe"))
    luau_analyze = resolve_executable(args.luau_analyze, ("luau-analyze", "luau-analyze.exe"))
    if not luau:
        raise SystemExit("Luau runtime not found. Run `python tools/luaubench.py doctor` first.")

    client = OpenAICompatibleClient(ModelConfig(
        provider=args.provider,
        base_url=provider_cfg["base_url"],
        api_key=api_key,
        model=args.model,
        temperature=args.temperature,
        auth_header=provider_cfg["auth_header"],
        auth_prefix=provider_cfg["auth_prefix"],
    ), http_backend=get_http_backend(args), curl_path=args.curl_path)
    model_metadata = None  # Optional metadata; not fetched during benchmark runs.
    system = (ROOT / "SYSTEM_PROMPT.md").read_text(encoding="utf-8")
    task_prompt = (task_dir / "public" / "TASK.md").read_text(encoding="utf-8")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": "Use the benchmark tools to complete this task. Do not ask the human to edit files. Call finish only after implementing and testing.\n\nTASK:\n" + task_prompt},
    ]

    meta: dict[str, Any] = {
        "benchmark": "LuauCodeBench",
        "benchmark_version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "task": manifest,
        "provider": args.provider,
        "model": args.model,
        "base_url": client.base_url,
        "model_metadata": model_metadata,
        "model_metadata_note": "Not fetched during benchmark run; catalog access is not required.",
        "http_backend": client.http_backend,
        "run_id": run_id,
        "started_at": now_iso(),
        "time_limit_sec": int(manifest.get("time_limit_sec", 600)),
        "max_tool_calls": int(manifest.get("max_tool_calls", 60)),
        "temperature": args.temperature,
        "score_eligible": True,
    }
    (run_dir / "run.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    transcript = run_dir / "transcript.jsonl"
    transcript.write_text("", encoding="utf-8")

    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    response_models_seen: list[str] = []
    tool_calls = 0
    started = time.monotonic()
    stop_reason = "unknown"

    def log(event: dict[str, Any]) -> None:
        with transcript.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    while True:
        elapsed = time.monotonic() - started
        if elapsed >= meta["time_limit_sec"]:
            stop_reason = "time_limit"
            break
        if tool_calls >= meta["max_tool_calls"]:
            stop_reason = "tool_call_limit"
            break
        try:
            response = client.complete(messages, tool_specs())
        except urllib.error.HTTPError as exc:
            body = getattr(exc, "_luaubench_body", None)
            if body is None:
                body = exc.read().decode("utf-8", errors="replace")
            stop_reason = "infra_error" if exc.code in {408, 425, 429, 500, 502, 503, 504} else "model_api_error"
            meta["error"] = f"HTTP {exc.code}: {body[:2000]}"
            meta["score_eligible"] = False
            break
        except Exception as exc:
            stop_reason = "runner_error"
            meta["error"] = repr(exc)
            break

        response_model = response.get("model")
        if isinstance(response_model, str) and response_model not in response_models_seen:
            response_models_seen.append(response_model)
        usage = response.get("usage") or {}
        for key in usage_total:
            value = usage.get(key)
            if isinstance(value, (int, float)):
                usage_total[key] += value
        choices = response.get("choices") or []
        if not choices:
            stop_reason = "bad_model_response"
            meta["error"] = "No choices in model response"
            break
        message = choices[0].get("message", {})
        log({"time": now_iso(), "type": "assistant", "message": message, "usage": usage})
        messages.append(message)

        calls = message.get("tool_calls") or []
        if not calls:
            messages.append({"role": "user", "content": "Continue. Inspect the workspace, make the implementation, run tests, and call finish when complete."})
            log({"time": now_iso(), "type": "runner", "event": "nudge_plain_text"})
            continue

        finished = False
        for call in calls:
            if tool_calls >= meta["max_tool_calls"]:
                break
            tool_calls += 1
            function = call.get("function") or {}
            name = str(function.get("name", ""))
            raw_args = function.get("arguments") or "{}"
            try:
                parsed = json.loads(raw_args)
                result, is_finished = execute_tool(name, parsed, workspace, args.task, luau, luau_analyze)
                finished = finished or is_finished
            except Exception as exc:
                parsed = raw_args
                result = f"TOOL ERROR: {type(exc).__name__}: {exc}"
            log({"time": now_iso(), "type": "tool", "tool_call_id": call.get("id"), "name": name, "args": parsed, "result": result})
            messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": result})
            if finished:
                break
        if finished:
            stop_reason = "model_finished"
            break

    meta.update({
        "finished_at": now_iso(),
        "duration_sec": round(time.monotonic() - started, 3),
        "tool_calls": tool_calls,
        "usage": usage_total,
        "response_models_seen": response_models_seen,
        "stop_reason": stop_reason,
        "provider_retry_count": client.retry_count,
        "provider_retry_sleep_sec": round(client.retry_sleep_sec, 3),
        "human_intervention": False,
    })
    meta["active_duration_sec"] = round(max(0.0, meta["duration_sec"] - client.retry_sleep_sec), 3)
    (run_dir / "run.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    evaluation = None
    if meta.get("score_eligible", True) and stop_reason not in {"infra_error", "model_api_error", "runner_error"}:
        evaluation = evaluate_task(args.task, workspace, luau, luau_analyze, before)
    result_payload = {"run": meta, "evaluation": evaluation}
    (run_dir / "result.json").write_text(json.dumps(result_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = {
        "run_dir": str(run_dir),
        "score": evaluation["score"] if evaluation else None,
        "hidden": (f"{evaluation['hidden']['passed']}/{evaluation['hidden']['total']}" if evaluation else None),
        "public": (f"{evaluation['public']['passed']}/{evaluation['public']['total']}" if evaluation else None),
        "tool_calls": tool_calls,
        "duration_sec": meta["duration_sec"],
        "stop_reason": stop_reason,
    }
    if meta.get("error"):
        summary["error"] = meta["error"]
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0



def configure_interactively(env_path: Path) -> None:
    print("\
Configure Luau CodeBench API access (.env is local and git-ignored).")
    provider = input(f"Provider label [{os.getenv('LUAUBENCH_PROVIDER', 'custom')}]: ").strip() or os.getenv("LUAUBENCH_PROVIDER", "custom")
    base_default = os.getenv("LUAUBENCH_BASE_URL", "https://example.com/v1")
    base_url = input(f"OpenAI-compatible base URL [{base_default}]: ").strip() or base_default
    current_key = os.getenv("LUAUBENCH_API_KEY", "")
    typed_key = getpass.getpass("API key (input hidden; blank keeps the existing key): ").strip()
    api_key = typed_key or current_key
    if not api_key:
        print("No API key supplied; setup was not saved.")
        return
    model = os.getenv("LUAUBENCH_MODEL", "")
    model = input(f"Default model ID [{model or 'leave blank to choose later'}]: ").strip() or model
    auth_header = input(f"Auth header [{os.getenv('LUAUBENCH_AUTH_HEADER', 'Authorization')}]: ").strip() or os.getenv("LUAUBENCH_AUTH_HEADER", "Authorization")
    auth_prefix = input(f"Auth prefix; usually Bearer [{os.getenv('LUAUBENCH_AUTH_PREFIX', 'Bearer')}]: ").strip()
    if auth_prefix == "":
        auth_prefix = os.getenv("LUAUBENCH_AUTH_PREFIX", "Bearer")
    updates = {
        "LUAUBENCH_PROVIDER": provider,
        "LUAUBENCH_BASE_URL": base_url.rstrip("/"),
        "LUAUBENCH_API_KEY": api_key,
        "LUAUBENCH_AUTH_HEADER": auth_header,
        "LUAUBENCH_AUTH_PREFIX": auth_prefix,
    }
    if model:
        updates["LUAUBENCH_MODEL"] = model
    save_dotenv_values(env_path, updates)
    print(f"Saved local configuration: {env_path}")
    print("The API key is stored in plaintext in .env; keep the file private. It is excluded by .gitignore.")


def build_client_for_menu(args: argparse.Namespace) -> tuple[OpenAICompatibleClient, dict[str, Any]]:
    api_key_env, cfg = resolve_provider(args)
    model = os.getenv("LUAUBENCH_MODEL", "__model_picker__")
    client = OpenAICompatibleClient(
        ModelConfig(
            provider=cfg["provider"], base_url=cfg["base_url"], api_key=os.getenv(api_key_env) or "",
            model=model, temperature=None, auth_header=cfg["auth_header"], auth_prefix=cfg["auth_prefix"]
        ),
        http_backend=get_http_backend(args), curl_path=getattr(args, "curl_path", None)
    )
    return client, cfg


def extract_model_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, list):
        data = response.get("models") if isinstance(response, dict) else None
    if not isinstance(data, list):
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in data:
        if isinstance(item, str):
            model_id, name, metadata = item, item, {}
        elif isinstance(item, dict):
            model_id = item.get("id") or item.get("model") or item.get("name")
            name = item.get("name") or model_id
            metadata = item
        else:
            continue
        if not isinstance(model_id, str) or not model_id or model_id in seen:
            continue
        seen.add(model_id)
        rows.append({"id": model_id, "name": str(name), "metadata": metadata})
    rows.sort(key=lambda row: row["id"].lower())
    return rows


def write_selected_model(env_path: Path, model_id: str) -> None:
    save_dotenv_values(env_path, {"LUAUBENCH_MODEL": model_id})
    print(f"Selected model saved to LUAUBENCH_MODEL: {model_id}")


def select_model_interactively(args: argparse.Namespace) -> str | None:
    env_path = get_env_file(args)
    try:
        client, cfg = build_client_for_menu(args)
    except SystemExit as exc:
        print(str(exc))
        print("Choose Configure first.")
        return None
    print(f"\nProvider: {cfg['provider']}\nBase URL: {cfg['base_url']}\nRequesting GET {cfg['base_url']}/models ...\n")
    rows: list[dict[str, Any]] = []
    try:
        rows = extract_model_rows(client.list_models())
        if not rows:
            print("The endpoint returned no recognizable model list.")
    except Exception as exc:
        body = getattr(exc, "_luaubench_body", None)
        if body is None and isinstance(exc, urllib.error.HTTPError):
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
        print(f"Could not list models: {type(exc).__name__}: {exc}")
        if body:
            print(str(body)[:1200])
        print("Model listing is optional; some gateways block GET /models.")
    if rows:
        print("Available models:")
        for i, row in enumerate(rows, 1):
            metadata = row["metadata"]
            caps = metadata.get("capabilities") if isinstance(metadata, dict) else None
            caps_text = ""
            if isinstance(caps, dict):
                useful = [k for k in ("tools", "reasoning", "vision") if caps.get(k) not in (None, False, "")]
                if useful:
                    caps_text = " | " + ", ".join(f"{k}={caps[k]}" for k in useful)
            print(f"  {i:>3}. {row['id']}{caps_text}")
        print("    0. Enter a model ID manually")
        while True:
            choice = input("Choose number (or 0 for manual entry, blank to cancel): ").strip()
            if not choice:
                return None
            if choice == "0":
                model_id = input("Exact model ID: ").strip()
                if model_id:
                    write_selected_model(env_path, model_id)
                    return model_id
                print("Model ID cannot be empty.")
            elif choice.isdigit() and 1 <= int(choice) <= len(rows):
                model_id = rows[int(choice) - 1]["id"]
                write_selected_model(env_path, model_id)
                return model_id
            else:
                print("Enter a listed number, 0, or blank to cancel.")
    else:
        model_id = input("Enter model ID manually (blank to cancel): ").strip()
        if model_id:
            write_selected_model(env_path, model_id)
            return model_id
    return None


def command_select_model(args: argparse.Namespace) -> int:
    selected = select_model_interactively(args)
    return 0 if selected else 1


def command_menu(args: argparse.Namespace) -> int:
    env_path = get_env_file(args)
    while True:
        provider = os.getenv("LUAUBENCH_PROVIDER", getattr(args, "provider", None) or "generic")
        base_url = os.getenv("LUAUBENCH_BASE_URL", "(not configured)")
        model = os.getenv("LUAUBENCH_MODEL", "(not selected)")
        key_ready = bool(os.getenv("LUAUBENCH_API_KEY"))
        print("\n" + "=" * 58)
        print("Luau CodeBench — CLI")
        print(f"Provider: {provider}")
        print(f"Base URL: {base_url}")
        print(f"API key: {'configured' if key_ready else 'not configured'}")
        print(f"Model: {model}")
        print("=" * 58)
        print("1. Configure API (.env)")
        print("2. List/select model (GET /v1/models)")
        print("3. Check API + tool calling")
        print("4. Run benchmark")
        print("0. Exit")
        choice = input("Select: ").strip()
        if choice == "0":
            return 0
        if choice == "1":
            configure_interactively(env_path)
        elif choice == "2":
            select_model_interactively(args)
        elif choice == "3":
            model_id = os.getenv("LUAUBENCH_MODEL")
            if not model_id:
                print("Select a model first (menu option 2).")
                continue
            try:
                api_key_env, cfg = resolve_provider(args)
                client = OpenAICompatibleClient(ModelConfig(
                    provider=cfg["provider"], base_url=cfg["base_url"], api_key=os.getenv(api_key_env) or "",
                    model=model_id, temperature=None, auth_header=cfg["auth_header"], auth_prefix=cfg["auth_prefix"]
                ), http_backend=get_http_backend(args), curl_path=getattr(args, "curl_path", None))
                basic = client.probe_basic_completion()
                choices = basic.get("choices") or []
                text = ((choices[0].get("message") or {}).get("content") or "") if choices else ""
                print(f"Basic completion: PASS ({str(text)[:80]!r})")
                probe = client.probe_tool_calling()
                calls = (((probe.get("choices") or [{}])[0].get("message") or {}).get("tool_calls") or [])
                if calls:
                    print("Tool calling: PASS")
                else:
                    print("Tool calling: FAIL (no tool_calls in the response)")
            except SystemExit as exc:
                print(f"Configuration problem: {exc}")
                print("Use menu option 1 to configure the API.")
            except Exception as exc:
                body = getattr(exc, "_luaubench_body", None)
                print(f"Probe failed: {type(exc).__name__}: {exc}")
                if body:
                    print(str(body)[:1500])
        elif choice == "4":
            model_id = os.getenv("LUAUBENCH_MODEL")
            if not model_id:
                print("Select a model first (menu option 2).")
                continue
            task = input("Task [T01_Cooldown] (currently calibrated task): ").strip() or "T01_Cooldown"
            if task != "T01_Cooldown":
                print("Only T01_Cooldown has a validated scoring implementation in v0.3.0. Choose T01_Cooldown.")
                continue
            run_args = argparse.Namespace(
                task=task, model=model_id, temperature=0.0, luau=None, luau_analyze=None, run_id=None,
                provider=os.getenv("LUAUBENCH_PROVIDER", "custom"),
                base_url=os.getenv("LUAUBENCH_BASE_URL"),
                auth_header=os.getenv("LUAUBENCH_AUTH_HEADER"), auth_prefix=os.getenv("LUAUBENCH_AUTH_PREFIX"),
                http_backend=get_http_backend(args), curl_path=getattr(args, "curl_path", None), env_file=str(env_path)
            )
            run_model(run_args)
        else:
            print("Unknown choice.")

def command_doctor(args: argparse.Namespace) -> int:
    luau = resolve_executable(args.luau, ("luau", "luau.exe"))
    analyzer = resolve_executable(args.luau_analyze, ("luau-analyze", "luau-analyze.exe"))
    print(f"Python: {sys.version.split()[0]}")
    print(f"Luau: {luau or 'NOT FOUND'}")
    print(f"Luau Analyze: {analyzer or 'NOT FOUND'}")
    print(f"Benchmark root: {ROOT}")
    if not luau:
        print("Install the official Luau Windows binaries, then put luau.exe on PATH or pass --luau PATH_TO_LUAU_EXE.")
    return 0 if luau else 2


def command_prepare(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    prepare_workspace(args.task, output)
    print(f"Prepared: {output}")
    return 0


def command_evaluate(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    luau = resolve_executable(args.luau, ("luau", "luau.exe"))
    analyzer = resolve_executable(args.luau_analyze, ("luau-analyze", "luau-analyze.exe"))
    if not luau:
        raise SystemExit("Luau runtime not found.")
    # Build a pristine baseline from the public fixture so the diff metrics are meaningful.
    baseline_dir = Path(tempfile.mkdtemp(prefix="luaubench_baseline_"))
    try:
        prepare_workspace(args.task, baseline_dir)
        before = snapshot_tree(baseline_dir)
    finally:
        shutil.rmtree(baseline_dir, ignore_errors=True)
    result = evaluate_task(args.task, workspace, luau, analyzer, before=before)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def command_check_api(args: argparse.Namespace) -> int:
    args.model = get_model_id(args)
    api_key_env, provider_cfg = resolve_provider(args)
    args.provider = provider_cfg["provider"]
    client = OpenAICompatibleClient(ModelConfig(
        provider=args.provider,
        base_url=provider_cfg["base_url"],
        api_key=os.getenv(api_key_env) or "",
        model=args.model,
        temperature=None,
        auth_header=provider_cfg["auth_header"],
        auth_prefix=provider_cfg["auth_prefix"],
    ), http_backend=get_http_backend(args), curl_path=args.curl_path)

    def show_http_error(stage: str, exc: urllib.error.HTTPError) -> int:
        body = getattr(exc, "_luaubench_body", None)
        if body is None:
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
        print(f"API probe failed during {stage}: HTTP {exc.code}")
        print(body[:4000])
        if exc.code == 502:
            print("HTTP 502 usually indicates an upstream gateway/provider failure; this run is not scored.")
        return 2

    # Stage 1: plain completion. This isolates key/endpoint/model availability
    # from tool-calling support.
    try:
        basic = client.probe_basic_completion()
    except urllib.error.HTTPError as exc:
        return show_http_error("basic completion", exc)
    except Exception as exc:
        print(f"API probe failed during basic completion: {type(exc).__name__}: {exc}")
        return 2

    basic_choices = basic.get("choices") or []
    if not basic_choices:
        print("API basic completion reached the provider, but it returned no choices.")
        print(json.dumps(basic, indent=2, ensure_ascii=False)[:4000])
        return 2
    basic_msg = basic_choices[0].get("message") or {}
    basic_text = basic_msg.get("content") or ""
    print(f"Basic completion: OK ({basic_text[:80]!r})")

    # Stage 2: actual function calling, matching the agent path used by benchmark runs.
    try:
        response = client.probe_tool_calling()
    except urllib.error.HTTPError as exc:
        return show_http_error("tool calling", exc)
    except Exception as exc:
        print(f"API probe failed during tool calling: {type(exc).__name__}: {exc}")
        return 2

    choices = response.get("choices") or []
    if not choices:
        print("Tool-calling probe failed: provider returned no choices.")
        print(json.dumps(response, indent=2, ensure_ascii=False)[:4000])
        return 2
    message = choices[0].get("message") or {}
    calls = message.get("tool_calls") or []
    if not calls:
        print("Basic inference works, but the model did not return a tool call.")
        print("The route is reachable, but this model/provider combination is not suitable for the agent benchmark runner.")
        return 2
    print(f"API OK. Tool calling works: {args.model}")
    return 0


def command_list_models(args: argparse.Namespace) -> int:
    api_key_env, provider_cfg = resolve_provider(args)
    args.provider = provider_cfg["provider"]
    client = OpenAICompatibleClient(ModelConfig(
        provider=args.provider,
        base_url=provider_cfg["base_url"],
        api_key=os.getenv(api_key_env) or "",
        model="__unused__",
        temperature=None,
        auth_header=provider_cfg["auth_header"],
        auth_prefix=provider_cfg["auth_prefix"],
    ), http_backend=get_http_backend(args), curl_path=args.curl_path)
    try:
        response = client.list_models()
    except urllib.error.HTTPError as exc:
        body = getattr(exc, "_luaubench_body", None)
        if body is None:
            body = exc.read().decode("utf-8", errors="replace")
        print(f"API models request failed: HTTP {exc.code}")
        print(body[:4000])
        if exc.code == 403 and "cloudflare" in body.lower():
            print("NOTE: model listing is optional. Use the provider's model catalog and pass the exact model ID to --model.")
            print("A benchmark run does not call /models; it only needs POST /chat/completions with tool calling.")
        return 2
    except Exception as exc:
        print(f"API models request failed: {type(exc).__name__}: {exc}")
        return 2

    rows = extract_model_rows(response)
    if not rows:
        print(json.dumps(response, indent=2, ensure_ascii=False)[:8000])
        return 0
    for row in rows:
        meta = row["metadata"]
        caps = meta.get("capabilities", {}) if isinstance(meta, dict) else {}
        if not isinstance(caps, dict):
            caps = {}
        tools = caps.get("tools", meta.get("tools", ""))
        reasoning = caps.get("reasoning", meta.get("reasoning", ""))
        vision = caps.get("vision", meta.get("vision", ""))
        context = meta.get("context_length", meta.get("context_window", ""))
        print(f"{row['id']}\ttools={tools}\treasoning={reasoning}\tvision={vision}\tcontext={context}")
    print(f"Models: {len(rows)}")
    return 0


def add_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", default=None, help="Logical provider label; defaults to LUAUBENCH_PROVIDER in .env.")
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible base URL; .env LUAUBENCH_BASE_URL is preferred when set.")
    parser.add_argument("--auth-header", default=None, help="Authentication header, default: Authorization")
    parser.add_argument("--auth-prefix", default=None, help="Authentication prefix, default: Bearer")
    parser.add_argument("--http-backend", choices=["auto", "urllib", "curl"], default=None, help="HTTP transport; defaults to LUAUBENCH_HTTP_BACKEND or auto.")
    parser.add_argument("--env-file", default=None, help="Path to .env file (default: benchmark root/.env).")
    parser.add_argument("--curl", dest="curl_path", default=None, help="Optional path to curl executable.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Luau CodeBench v0.3.0 runner")
    sub = p.add_subparsers(dest="command", required=True)

    ca = sub.add_parser("check-api", help="Validate a provider key and model endpoint")
    ca.add_argument("--model", default=None, help="Model ID; defaults to LUAUBENCH_MODEL in .env.")
    add_provider_args(ca)
    ca.set_defaults(func=command_check_api)

    lm = sub.add_parser("list-models", help="List models exposed by an OpenAI-compatible provider")
    add_provider_args(lm)
    lm.set_defaults(func=command_list_models)

    mm = sub.add_parser("menu", help="Interactive local CLI for API setup, model selection, checks, and runs")
    add_provider_args(mm)
    mm.set_defaults(func=command_menu)

    sm = sub.add_parser("select-model", help="Fetch /models and interactively save the selected model to .env")
    add_provider_args(sm)
    sm.set_defaults(func=command_select_model)

    d = sub.add_parser("doctor", help="Check Python/Luau tooling")
    d.add_argument("--luau")
    d.add_argument("--luau-analyze")
    d.set_defaults(func=command_doctor)

    pr = sub.add_parser("prepare", help="Create a clean model-facing workspace")
    pr.add_argument("task")
    pr.add_argument("output")
    pr.set_defaults(func=command_prepare)

    ev = sub.add_parser("evaluate", help="Evaluate an existing workspace")
    ev.add_argument("task")
    ev.add_argument("workspace")
    ev.add_argument("--luau")
    ev.add_argument("--luau-analyze")
    ev.set_defaults(func=command_evaluate)

    rm = sub.add_parser("run-model", help="Run a model using an OpenAI-compatible chat API")
    rm.add_argument("task")
    rm.add_argument("--model", default=None, help="Model ID; defaults to LUAUBENCH_MODEL in .env.")
    rm.add_argument("--temperature", type=float, default=0.0)
    rm.add_argument("--luau")
    rm.add_argument("--luau-analyze")
    rm.add_argument("--run-id")
    add_provider_args(rm)
    rm.set_defaults(func=run_model)
    return p


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    env_file = get_env_file(args)
    load_dotenv(env_file)
    if hasattr(args, "model") and not getattr(args, "model", None):
        args.model = os.getenv("LUAUBENCH_MODEL")
    raise SystemExit(args.func(args))
