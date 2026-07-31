# core

Shared orchestration, result models, auth, persistence, and job management for the review platform.

This layer should stay framework-agnostic. It should not know whether a review target is .NET, Python, or React beyond the pack chosen at runtime.