# Planned Integrations — Draft for Grooming

Status: **draft / not yet implemented**. Captured from a design discussion on 2026-08-13. Intended to be groomed further (e.g. with Kiro or similar spec tools) before implementation.

## Near-term — Async execution & result persistence (applies to the existing `/reviews` endpoint, not just the future Bitbucket webhook)

**Motivation:** `POST /reviews` currently blocks synchronously for 30s+ while the agent runs (real network + LLM latency observed in testing), and the `ReviewResult` is only ever returned in the HTTP response body — nothing is persisted, so there's no way to look up a past run's result later. This is already flagged in the README's observations (API/spec drift: `202`/`GET /reviews/{run_id}` are documented in `api/openapi.yaml` but never implemented).

Needed pieces:

- **Async execution:** return `202 {run_id, status: "queued"}` immediately and run the review via **AWS Lambda Durable Functions** — a Lambda function using the AWS Durable Execution SDK where workflow steps (run review, save result) are wrapped in `steps` for automatic checkpointing/retry, and any pause between steps uses `waits` that suspend the function without incurring compute charges. The durable execution ID serves as `run_id`. See "Async processing & run/process tracking design" further below for the full option comparison.
- **Result persistence:** save the `ReviewResult` (plus run status/timestamps) to **DynamoDB** instead of discarding it after the response is sent. Minimum viable shape: a `reviews` table with `run_id` as the partition key, storing `owner`, `repo`, `pr_number`, `framework`, `status`, `summary`, `findings` (serialised JSON), `created_at`, `completed_at`.
  - Fits the existing clean-architecture boundary as a new adapter: `infrastructure/review_repository.py` — `application/review_service.run_review` calls a `save_result(result)` method after the agent finishes, and `GET /reviews/{run_id}` reads from it via a `get_result(run_id)` method.
  - DynamoDB pairs naturally with **Lambda Durable Functions** (both AWS-native, IAM-based auth, no connection pool to manage) and keeps `run_id` as the lookup key end-to-end. `GET /reviews/{run_id}` reads from DynamoDB once the durable function writes the result.
- **`GET /reviews/{run_id}`**: already documented, never implemented — becomes the read path once results are persisted.

## Near-term — Review quality feedback / reward signal for the agent

**Motivation:** nothing today captures whether a given `ReviewResult` was actually good. A bad review (false positives, missed real issues, wrong severity) goes completely unflagged, and there's no signal that feeds back into improving future runs.

**Status:** needs grooming — this is a research/design question (what "reward" means, who provides feedback, how it's scored) more than a ready-to-build engineering task.

Draft pieces to groom:

- A feedback mechanism for a human reviewer to mark a completed review as good/bad, or per-finding as correct/incorrect/false-positive — e.g. a `POST /reviews/{run_id}/feedback` endpoint, or a reaction on the PR comment once Phase 1's "post findings back as a PR comment" work lands.
- Persist that feedback alongside the stored `ReviewResult` (same `infrastructure/review_repository.py` piece above) so it can be queried/aggregated later.
- Open question — what "reward" means here. Options to groom, roughly lightest to heaviest:
  1. Observability/metrics only (e.g. "% of reviews flagged bad by domain") — no automated adjustment. Likely the right starting point.
  2. A scoring signal used to A/B test or manually tune prompts per domain pack (`domains/<name>/prompts/`) over time.
  3. Input to a future fine-tuning/RLHF-style pass, if the platform ever trains a model instead of only prompting one.
- None of this should block Phase 1/2 below — it's a parallel workstream once feedback capture (option 1) is groomed.

## Phase 1 — PR-created webhook → auto-review (Bitbucket)

**Trigger:** a pull request is opened/updated in **Bitbucket** — this is the actual target provider for this integration.

**Goal:** automatically call the existing review pipeline (`POST /reviews` logic) instead of requiring a manual API call.

**Important:** this repo's tooling currently only supports GitHub (`infrastructure/github_client.py` calls `api.github.com` exclusively). Since the real target is Bitbucket, this plan includes **extending the platform with Bitbucket support** as a prerequisite, not an optional later step.

### New pieces needed

- **Bitbucket provider tools** — new equivalents of the 5 existing GitHub tools (`get_pr_files`, `get_pr_diff`, `get_repo_files`, `find_repo_files`, `get_repo_file_content` / `list_repo_file_paths`) built against the Bitbucket REST API (Cloud or Server/Data Center — needs confirming which), since Bitbucket's auth scheme, diff format, and PR object shape all differ from GitHub's.
- `POST /webhooks/bitbucket` in [api/routes.py](../api/routes.py) — receives Bitbucket's pull request webhook event (e.g. `pullrequest:created` / `pullrequest:updated`), verifies the request signature/secret, extracts `owner` / `repo` (workspace/project + repo slug for Bitbucket) / `pr_number`, and invokes the same use case `application/review_service.run_review` uses today.
- **Async processing is required.** Webhook receivers typically expect a fast response, but a real review takes 30s+ (observed in testing). This is the natural place to finally implement the `202` accepted flow already documented in [api/openapi.yaml](../api/openapi.yaml) but never built — reuse the same async execution + persistence work from the "Near-term" section above rather than building it twice. See "Async processing & run tracking design" below for how to implement the `run_id` / process tracking piece without building a bespoke service.
- **Result delivery:** post findings back as a PR comment (new tool, e.g. `post_pr_comment`, via Bitbucket's PR comments API) instead of only returning JSON that nobody looks at.
- **Idempotency:** dedupe by commit SHA so repeated "updated" events don't trigger redundant, paid OpenAI runs.
- **Provider seam:** extract a small `GitProvider` interface (shared method signatures for PR files/diff/repo tree/file content) so `GitHubProvider` (already built, used for local/personal testing) and the new `BitbucketProvider` can both plug into `infrastructure/agent_runner.py` via `owner` / `repo` + a `provider` field, without duplicating the agent-building logic.


### Async processing & run/process tracking design

The goal: the API handler responds immediately with a `run_id`, the review runs in the background, and `GET /reviews/{run_id}` lets you check status/result later. Options, roughly lightest to most managed:

1. **In-process background task + DynamoDB (simplest, works today)**
   - FastAPI `BackgroundTasks` runs the review after returning `{"run_id": ..., "status": "queued"}` immediately; writes result to DynamoDB on completion.
   - No built-in retry; a crash mid-review loses that run's state. Viable as a spike before real infra is provisioned.

2. **SQS + Lambda worker + DynamoDB (decoupled, durable delivery)**
   - API handler enqueues a message onto SQS and returns `202`; a Lambda function with an SQS event-source mapping consumes it, runs the review, writes to DynamoDB.
   - SQS provides at-least-once delivery and a dead-letter queue, but Lambda compute runs continuously during the full review — no sleep-without-compute.

3. **AWS Lambda Durable Functions + DynamoDB (decided)**
   - Uses the [AWS Durable Execution SDK](https://docs.aws.amazon.com/durable-execution/) (Python), available in Lambda natively. Business logic is written as normal sequential Python code using two primitives:
     - `steps` — wrap compute work (e.g. fetch standards, run agent, save result) with automatic checkpointing and built-in retry. This is the only primitive needed for the initial async review flow.
     - `waits` — relevant once the reward/feedback feature lands: a completed review could pause for a human rating signal before the workflow continues, without incurring compute charges during that idle period.
   - The durable execution ID serves as `run_id`. Can execute for up to one year.
   - Unlike Step Functions, workflow logic lives in code (not a graph DSL/visual designer), which keeps it version-controlled alongside the rest of the application and avoids a separate orchestration service.
   - Writes final `ReviewResult` to DynamoDB; `GET /reviews/{run_id}` reads from there.

4. **AWS Step Functions + Lambda + DynamoDB**
   - Step Functions state machine orchestrates Lambda tasks; execution ARN is the `run_id`; `Wait` states pause without compute. Fully managed with zero maintenance and native integrations to 220+ AWS services.
   - Better fit if the workflow needs visual design or cross-service orchestration beyond what a Lambda-native SDK provides. Not chosen here since Lambda Durable Functions keeps everything in code.

5. **Amazon Bedrock AgentCore Runtime (if we pursue AgentCore hosting)**
   - Built-in async task tracking via the `bedrock-agentcore` SDK. Only relevant if hosting moves to AgentCore Runtime; not a reason to adopt it on its own.

**Decided:** option 3 — **Lambda Durable Functions + DynamoDB**. DynamoDB was already chosen for result persistence above.

**Recommendation for grooming:** option 1 (in-process background task + DynamoDB) is the right spike before Lambda Durable infra is provisioned — the DynamoDB persistence layer is identical, so it's a straight swap of the async compute piece when ready.

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
- A new structured output model describing "proposed doc changes" (analogous to `ReviewResult` in [domain/models.py](../domain/models.py)).
- New tools to read the docs repo, create a branch, commit changes, and open a PR — reusing the same `Agent` / `structured_output_model` pattern used for reviews.

## Suggested sequencing

1. Groom the review feedback/reward-signal open questions (near-term section above) — start with observability-only (option 1) as the low-risk first step.
2. Build async execution + result persistence for the existing `/reviews` endpoint (near-term section above) — unblocks both the Bitbucket webhook's async requirement and `GET /reviews/{run_id}`.
3. Groom Phase 2's open questions with the team.
4. Extend the platform with Bitbucket provider support (new tools + `/webhooks/bitbucket` + PR comment delivery, reusing the async/persistence work from step 2) — self-contained, well-scoped, no blocked decisions.
5. Implement Phase 2 once format/structure and safety model are agreed.

Note: local/personal testing can continue against GitHub in the meantime (already working end-to-end), since the `GitProvider` seam lets both providers coexist.
