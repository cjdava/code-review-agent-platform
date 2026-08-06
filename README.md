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