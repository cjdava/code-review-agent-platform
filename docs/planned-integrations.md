# Planned Integrations — Draft for Grooming

Status: **draft / not yet implemented**. Captured from a design discussion on 2026-08-13. Intended to be groomed further (e.g. with Kiro or similar spec tools) before implementation.

## Phase 1 — PR-created webhook → auto-review (Bitbucket)

**Trigger:** a pull request is opened/updated in **Bitbucket** — this is the actual target provider for this integration.

**Goal:** automatically call the existing review pipeline (`POST /reviews` logic) instead of requiring a manual API call.

**Important:** this repo's tooling currently only supports GitHub (`tools/github_tools.py` calls `api.github.com` exclusively). Since the real target is Bitbucket, this plan includes **extending the platform with Bitbucket support** as a prerequisite, not an optional later step.

### New pieces needed

- **Bitbucket provider tools** — new equivalents of the 5 existing GitHub tools (`get_pr_files`, `get_pr_diff`, `get_repo_files`, `find_repo_files`, `get_repo_file_content` / `list_repo_file_paths`) built against the Bitbucket REST API (Cloud or Server/Data Center — needs confirming which), since Bitbucket's auth scheme, diff format, and PR object shape all differ from GitHub's.
- `POST /webhooks/bitbucket` in [app.py](../app.py) — receives Bitbucket's pull request webhook event (e.g. `pullrequest:created` / `pullrequest:updated`), verifies the request signature/secret, extracts `owner` / `repo` (workspace/project + repo slug for Bitbucket) / `pr_number`, and invokes the same pipeline `/reviews` uses today.
- **Async processing is required.** Webhook receivers typically expect a fast response, but a real review takes 30s+ (observed in testing). This is the natural place to finally implement the `202` accepted flow already documented in [api/openapi.yaml](../api/openapi.yaml) but never built. See "Async processing & run tracking design" below for how to implement the `run_id` / process tracking piece without building a bespoke service.
- **Result delivery:** post findings back as a PR comment (new tool, e.g. `post_pr_comment`, via Bitbucket's PR comments API) instead of only returning JSON that nobody looks at.
- **Idempotency:** dedupe by commit SHA so repeated "updated" events don't trigger redundant, paid OpenAI runs.
- **Provider seam:** extract a small `GitProvider` interface (shared method signatures for PR files/diff/repo tree/file content) so `GitHubProvider` (already built, used for local/personal testing) and the new `BitbucketProvider` can both plug into `generic_agent.py` via `owner` / `repo` + a `provider` field, without duplicating the agent-building logic.

### Async processing & run/process tracking design

The goal: `POST /webhooks/bitbucket` responds immediately with a `run_id` (a process/job identifier), the review runs in the background, and something lets you check status/result later — conceptually the same role a "Process Service" plays (start a process, get an ID back, poll or get notified of completion). A few options, roughly ordered from lightest to most managed:

1. **In-process background task + status store (simplest, works today)**
   - FastAPI `BackgroundTasks` (or a lightweight in-process thread) runs the review after returning `{"run_id": ..., "status": "queued"}` immediately.
   - A small status store (e.g. a DynamoDB table `run_id -> {status, result, timestamps}`, or even a local SQLite table for a single-instance deployment) backs `GET /reviews/{run_id}`.
   - Downside: no built-in retry, no cross-instance durability if `app.py` runs on more than one instance/container, and a crash mid-review loses that run's state.

2. **SQS queue + worker + DynamoDB status table (decoupled, still self-built)**
   - Webhook handler pushes a message (`owner`, `repo`, `pr_number`, `run_id`) onto an SQS queue and immediately returns `202` with the `run_id`.
   - A separate worker (Lambda, or an ECS/Fargate task) consumes the queue, runs the review, and writes status/result to DynamoDB keyed by `run_id`.
   - `GET /reviews/{run_id}` just reads from DynamoDB. This is durable and scales, but it's still infrastructure you build and operate yourselves — closer to "build our own Process Service on AWS primitives" than reusing something managed.

3. **AWS Step Functions (closest managed equivalent to a "Process Service")**
   - Starting a Step Functions execution (`StartExecution`) returns an **execution ARN** — this can serve directly as the `run_id`/process id.
   - Status is queryable anytime via `DescribeExecution` (`RUNNING` / `SUCCEEDED` / `FAILED` / `TIMED_OUT`), with built-in execution history, retries, and timeouts — essentially a managed version of what an internal "Process Service" provides, without building or maintaining the tracking store yourselves.
   - The webhook handler would start an execution (a state machine step invokes the review logic, e.g. via a Lambda task), return the execution ARN as `run_id` immediately, and `GET /reviews/{run_id}` would call `DescribeExecution` under the hood.
   - Best fit if the team wants a managed "process tracking" answer rather than rolling a custom DynamoDB/SQS setup.

4. **Amazon Bedrock AgentCore Runtime's built-in async task tracking (if we pursue AgentCore hosting)**
   - AgentCore Runtime (see the earlier "deploy to AWS" discussion) has native async support via the `bedrock-agentcore` SDK: call `app.add_async_task(...)` when a task starts and `app.complete_async_task(task_id)` when it finishes; the platform tracks task state and reports it through the required `/ping` health endpoint (`Healthy` / `HealthyBusy`) automatically.
   - The `runtimeSessionId` used to invoke the agent doubles as the process identifier, and `InvokeAgentRuntime`/session status calls let you check on it — so if we deploy there, we effectively get "process tracking" for free instead of building any of options 1–3.
   - Only worth it if/when we actually move hosting to AgentCore Runtime; not a reason to adopt AgentCore on its own.

**Recommendation for grooming:** start with option 1 for a quick working version, but if the team wants a real answer to "how do we track process status" without hand-rolling it, **Step Functions (option 3)** is the most direct AWS-native replacement for a bespoke Process Service. Revisit if/when AgentCore Runtime hosting (option 4) is adopted, since that would make it moot.

### Notes / risks carried over from architecture review

- Current tools call `api.github.com` exclusively — none of it works against Bitbucket without the new provider tools above. This is a **second provider integration**, not just "add a webhook."
- Ties directly into existing README observations: #2 (no auth on `/reviews` — a webhook needs its own signature-based auth instead), and #4 (API/spec drift — this finally implements the documented-but-missing async flow).

## Phase 2 — PR-approved → auto-update service documentation

**Motivation:** developers often forget to manually update application documentation after a change ships. The idea is to have the agent keep a separate docs repo up to date automatically when a PR is approved.

**Status:** blocked on team decisions — format and structure not yet discussed. Treat this as a second agent workflow, not a small add-on to Phase 1.

### Open questions to resolve before implementation

1. **Docs repo location** — is it a separate repo from the app repo? If so, the agent needs a second `owner/repo` target and separate credentials/permissions.
2. **Safety model** — should the agent open a **PR against the docs repo** for a human to merge (safer, recommended), or commit directly (riskier — unreviewed auto-generated doc changes could introduce inaccuracies into docs people trust)?
3. **Scope of "documentation"** — per-service README updates? API reference? Architecture diagrams? This determines what context the agent needs (just the diff, or the whole changed service's code).
4. **Trigger reliability** — `pull_request_review` webhook event with `state: approved`. For a multi-approver workflow, should this fire on *first* approval, or only once the PR is merged?

### Likely shape once questions are answered

Mirrors the pattern already proven in this repo:
- A new prompt pack (`domains/docs/prompts/`) defining the docs-agent's persona and workflow.
- A new structured output model describing "proposed doc changes" (analogous to `ReviewResult` in [generic_agent.py](../generic_agent.py)).
- New tools to read the docs repo, create a branch, commit changes, and open a PR — reusing the same `Agent` / `structured_output_model` pattern used for reviews.

## Suggested sequencing

1. Groom Phase 2's open questions with the team.
2. Extend the platform with Bitbucket provider support (new tools + `/webhooks/bitbucket` + async processing + PR comment delivery) — self-contained, well-scoped, no blocked decisions.
3. Implement Phase 2 once format/structure and safety model are agreed.

Note: local/personal testing can continue against GitHub in the meantime (already working end-to-end), since the `GitProvider` seam lets both providers coexist.
