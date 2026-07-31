# code-review-agent-platform

A generic, API-first code review platform that can power .NET, Python, and React review agents.

The goal is to keep the review engine framework-agnostic while loading framework-specific best-practices packs at runtime.

## What this repo owns

- API contract for triggering a review
- Shared review result schema
- Framework routing and selection
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
├── frameworks/
│   ├── dotnet/
│   ├── python/
│   └── react/
└── README.md
```

## Next step

Implement the review service behind the API contract, then plug Bitbucket actions into `POST /reviews`.