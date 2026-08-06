# code-review-agent-platform

A generic, API-first code review platform that can power review agents across multiple domains such as .NET, Python, React, QA, and database reviews.

The goal is to keep the review engine domain-agnostic while loading domain-specific review packs and standards at runtime.

## What this repo owns

- API contract for triggering a review
- Shared review result schema
- Domain routing and selection
- Async job handling for CI/CD triggers
- Provider integrations such as Bitbucket webhooks or pipeline calls

## Contract shape

This platform uses the same final review result shape as the current .NET agent:

- `run_id`
- `pr_number`
- `status`
- `summary.total_findings`
- `summary.high_or_critical`
- `findings[]`

That keeps the output stable while the input trigger becomes API-driven.

## Suggested folder layout

```text
code-review-agent-platform/
├── api/
│   └── openapi.yaml
├── core/
├── domains/
│   ├── dotnet/
│   ├── python/
│   ├── react/
│   ├── qa/
│   └── database/
└── README.md
```

## Next step

Implement the review service behind the API contract, then plug Bitbucket actions into `POST /reviews`.

---

# Architecture & Implementation Documentation

Status: reflects the code as of 2026-08-06. Written for review purposes — see "Observations & Improvement Opportunities" at the end for gaps found while documenting.

## 1. Purpose

An API-first platform that reviews a GitHub pull request against domain-specific coding standards (`.NET`, `Python`, `React`, `QA`, `Database`) using an LLM agent, and returns a structured pass/fail result with findings.

## 2. High-Level Flow

```mermaid
sequenceDiagram
    participant Client
    participant API as app.py (FastAPI)
    participant Router as core/router.py
    participant Standards as core/standards_loader.py
    participant Agent as generic_agent.py
    participant LLM as OpenAI (strands Agent)
    participant GitHub as GitHub REST API

    Client->>API: POST /reviews {owner, repo, pr_number, framework}
    API->>Router: resolve_frameworks(framework_hint)
    Router-->>API: [framework,...]
    API->>Router: get_framework_packs(frameworks)
    Router->>Standards: get_standards_content(framework)
    Standards->>GitHub: GET raw standards markdown
    Standards-->>Router: standards text
    Router-->>API: FrameworkPack(s)
    API->>Agent: run_agent(owner, repo, pr, standards_content, prompt_dir, ...)
    Agent->>Agent: build_agent() -> Agent(model, tools, system_prompt, structured_output_model)
    Agent->>LLM: system_prompt + review_prompt (+ standards)
    LLM->>GitHub: tool calls (get_pr_files, get_pr_diff, get_repo_files, find_repo_files, get_repo_file_content)
    GitHub-->>LLM: PR/repo data
    LLM-->>Agent: ReviewResult (structured_output)
    Agent-->>API: normalized ReviewResult
    API-->>Client: 200 ReviewResult (or 500 on exception)
```

## 3. Entry Points

| Entry point | Purpose |
|---|---|
| [app.py](app.py) | FastAPI service exposing `POST /reviews`. |
| [run_agent.py](run_agent.py) | CLI runner for local/manual review runs (`--owner --repo --pr --framework`). |
| [api/openapi.yaml](api/openapi.yaml) | Documented contract, including endpoints not yet implemented (see below). |

Both `app.py` and `run_agent.py` converge on the same core pipeline: `core/router.py` → `core/standards_loader.py` → `generic_agent.run_agent`.

## 4. Core Components

### 4.1 `core/router.py` — Framework resolution & pack loading
- `resolve_frameworks(repo_files, framework_hint)`: if a hint other than `"auto"` is given, splits it on commas (supports multi-domain reviews, e.g. `"python,qa"`). If `"auto"`, infers from repo file names (`package.json` → react, `requirements.txt`/`pyproject.toml` → python, `.sln`/`.csproj` → dotnet). Defaults to `dotnet` if nothing matches.
- `get_framework_pack(framework)`: maps a framework name to a `FrameworkPack` (name, prompt dir under `domains/<name>/prompts`, module name — always `"generic_agent"`, and standards content fetched via `get_standards_content`).
- `combine_standards(packs)`: concatenates standards text from multiple packs under `## <name>` headers, used for multi-domain reviews.
- Supported domains: `python`, `react`, `qa`/`quality-assurance`, `database`/`db`/`mssql`, and default `dotnet`.

### 4.2 `core/standards_loader.py` — Remote standards fetch
- `get_standards_content(framework, standards_repo_url=None)`: maps framework → file path in the `best-practices` repo (e.g. `backend/python-standards.md`, `qa/playwright-standards.md`), builds a raw GitHub URL, and does a blocking `requests.get` (10s timeout) each call. No caching. Raises on network failure (`response.raise_for_status()` / `requests.RequestException`).
- Default repo: `https://raw.githubusercontent.com/cjdava/best-practices/main`, overridable via `STANDARDS_REPO_URL` env var.

### 4.3 `generic_agent.py` — Agent construction & execution
Domain-agnostic; all domains reuse this module (only the `prompt_dir` and `standards_content` differ).

- **Models** (Pydantic):
  - `Finding`: rule, category, severity (`LOW|MEDIUM|HIGH|CRITICAL`), file, start_line/end_line (`>=1`, validated `end_line >= start_line`), description, code_snippet.
  - `ReviewSummary`: total_findings, high_or_critical.
  - `ReviewResult`: run_id, pr_number, status (`PASS|FAIL`), summary, findings[].
- **Prompt building**:
  - `build_system_prompt(prompt_dir)`: reads `system_prompt.md` from the domain's prompt dir (defaults to `prompts/` under the repo root if none given/exists).
  - `build_review_prompt(owner, repo, pr_number, standards_content, prompt_dir)`: reads `review_prompt.md`, formats `{owner}/{repo}/{pr_number}` placeholders, appends a `Standards:` block if provided.
- **`build_agent(prompt_dir, review_domain)`**: constructs a `strands.Agent` with:
  - Model: `OpenAIModel` (`settings.openai_model`, temperature 0, seed 42 — deterministic).
  - Tools: `get_pr_files`, `get_pr_diff`, `get_repo_files`, `find_repo_files`, `get_repo_file_content` (all from `tools/github_tools.py`).
  - `structured_output_model=ReviewResult` — forces the LLM response into the schema.
  - `callback_handler=None`, `load_tools_from_directory=False`.
- **`normalize_review_result(result, run_id, pr_number)`**: de-duplicates findings by `(file, start_line, rule)`, sorts them, recomputes `high_or_critical` count and `status` (`FAIL` if any HIGH/CRITICAL) — i.e., the LLM-provided status/summary are discarded and recomputed server-side (good: don't trust LLM arithmetic).
- **`run_agent(...)`**: orchestrates build → invoke → normalize. Raises `ValueError` if `result.structured_output` is `None`.

### 4.4 `tools/github_tools.py` — GitHub REST integration (agent tool calls)
All tools use `@tool(context=True)` (strands), a shared `_github_headers()` (Bearer token from `settings.github_token`), and return a `{"status": "success"|"error", "content": [...]}` envelope.

| Tool | Endpoint | Notes |
|---|---|---|
| `get_pr_files` | `GET /repos/{owner}/{repo}/pulls/{pr}/files` | Returns filename/status/additions/deletions/changes only. |
| `get_pr_diff` | `GET /repos/{owner}/{repo}/pulls/{pr}` with diff Accept header | Truncates to first 8000 chars. |
| `get_repo_files` | `GET .../git/trees/HEAD?recursive=1` | Returns up to 1000 blob paths. |
| `find_repo_files` | same tree endpoint | Client-side filter by substring/suffix, limit clamped to 1000. |
| `get_repo_file_content` | `GET .../contents/{path}?ref=HEAD` | Base64-decodes content, truncates to `max_chars` (clamped ≤ 50000). |

### 4.5 `domains/<name>/prompts/` — Per-domain prompt packs
Each domain (`dotnet`, `python`, `react`, `qa`, `database`) has `system_prompt.md` (persona, rules, severity rubric, mandatory workflow) and `review_prompt.md` (per-PR instructions/template). The `.NET` pack is the most developed — it has an explicit multi-step workflow for test-coverage/dependency analysis using `.sln`/`.csproj` inspection.

### 4.6 `config.py` — Settings
`pydantic-settings` `Settings` loaded from `.env`: `openai_api_key` (SecretStr, required), `github_token` (SecretStr, required), `openai_model` (default `gpt-4.1-mini`), `log_level` (default `INFO`), `request_timeout` (default 30s). No `.env` file present in repo (expected to be supplied locally).

### 4.7 `api/openapi.yaml` — API contract
Documents `POST /reviews` (sync `200` or async `202`) and `GET /reviews/{run_id}`. Only `POST /reviews` returning `200` synchronously is implemented in [app.py](app.py); async acceptance and the `GET` lookup are not implemented.

## 5. Data Model Summary

```mermaid
classDiagram
    class ReviewResult {
      run_id: str
      pr_number: int
      status: PASS|FAIL
      summary: ReviewSummary
      findings: Finding[]
    }
    class ReviewSummary {
      total_findings: int
      high_or_critical: int
    }
    class Finding {
      rule: str
      category: str
      severity: LOW|MEDIUM|HIGH|CRITICAL
      file: str
      start_line: int
      end_line: int
      description: str
      code_snippet: str
    }
    ReviewResult --> ReviewSummary
    ReviewResult --> "many" Finding
```

Note: this schema is duplicated in three places — `generic_agent.py`, `app.py`, and `api/openapi.yaml` — and must be kept in sync manually.

## 6. Tests

- [tests/test_router.py](tests/test_router.py): framework detection/resolution, pack construction for `qa`/`database`, multi-framework resolution.
- [tests/test_standards_loader.py](tests/test_standards_loader.py): only covers the network-failure path.
- No tests exist for `generic_agent.py`, `app.py`, or `tools/github_tools.py`.

## 7. Observations & Improvement Opportunities

These are things worth reviewing/discussing, not yet changed:

1. **Error handling leaks internals**: [app.py](app.py) `create_review` catches `Exception` broadly and returns `str(exc)` as the HTTP 500 detail — this can leak stack/internal info to API callers (OWASP A05/A09). Consider logging the full exception server-side and returning a generic message to clients.
2. **No authentication/authorization** on `POST /reviews` in `app.py` — anyone who can reach the service can trigger reviews (which consume OpenAI + GitHub API quota) and read repo content via the agent's tools. Consider an API key or OAuth layer.
3. **Dynamic import is dead code**: `app.py` does `module = __import__(primary_pack.module_name); runner = getattr(module, "run_agent")` but `module_name` is always `"generic_agent"` for every pack in `router.py`. This could just be a direct `generic_agent.run_agent` import/call.
4. **API contract vs implementation drift**: `api/openapi.yaml` documents `202` async responses and `GET /reviews/{run_id}`, but only synchronous `POST /reviews` exists. Either implement the async path or trim the spec to match reality.
5. **No caching for standards content**: `core/standards_loader.get_standards_content` does a blocking network fetch to GitHub on every single review request, with no retry/backoff/caching. This adds latency and a hard external dependency/failure point per request.
6. **Ref `"HEAD"` in GitHub Contents API**: `get_repo_file_content` and `get_repo_files`/`find_repo_files` use `HEAD` as the git ref/tree SHA. GitHub's REST API generally expects a branch name, tag, or commit SHA, not the literal string `HEAD` — worth verifying this actually resolves the default branch reliably rather than erroring.
7. **Schema triplication**: `Finding`/`ReviewSummary`/`ReviewResult` are hand-duplicated in `generic_agent.py`, `app.py`, and `api/openapi.yaml`. A drift here (e.g., a new severity value) would silently break one layer. Consider sharing one Pydantic model set and generating the OpenAPI schema from it.
8. **Thin test coverage**: no tests exercise `generic_agent.run_agent`, `normalize_review_result` (dedup/status logic), the FastAPI endpoint, or the GitHub tool functions (including their error paths).
9. **Secrets in logs**: `logging.basicConfig(level=settings.log_level)` in `generic_agent.py` is fine, but there's no explicit redaction guard if request/response payloads (which could include tokens in headers via `requests` exceptions) are ever logged directly.
10. **Supply-chain trust on standards content**: standards markdown is fetched at runtime from a remote GitHub repo and injected directly into the LLM system/review prompt. If that upstream repo is compromised or the URL is overridden (`STANDARDS_REPO_URL` / CLI `--standards-repo-url`), arbitrary prompt content could be injected into the agent's instructions.
11. **`run_agent.py` default framework mismatch**: CLI defaults `--framework` to `dotnet` while `app.py`'s `ReviewRequest.framework` defaults to `"auto"` — inconsistent default behavior between the two entry points.