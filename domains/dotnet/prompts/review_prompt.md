Review pull request {pr_number} in repository {owner}/{repo}.

Requirements:
- Analyze changed files independently.
- Prefer many precise findings over broad summaries.
- Do not report style nits unless they clearly violate the checklist or create risk.
- Keep code_snippet short and directly relevant.
- If you need evidence for tests or dependencies, call tools to verify instead of guessing.
- Use `.sln` and `.csproj` contents when you need to understand project boundaries, references, and test projects.
