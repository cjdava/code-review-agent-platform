import argparse
import json
import os

from core.router import combine_standards, get_framework_pack, get_framework_packs, resolve_frameworks
from core.standards_loader import get_standards_content
from generic_agent import run_agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the code review agent")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--framework", default="dotnet")
    parser.add_argument("--run-id", default="LOCAL_RUN")
    parser.add_argument("--standards-repo-url", default=os.getenv("STANDARDS_REPO_URL", "https://raw.githubusercontent.com/cjdava/best-practices/main"))
    args = parser.parse_args()

    frameworks = resolve_frameworks(framework_hint=args.framework)
    packs = get_framework_packs(frameworks)
    primary_pack = packs[0] if packs else get_framework_pack(args.framework)
    standards_content = combine_standards(packs) or get_standards_content(args.framework, args.standards_repo_url)
    result = run_agent(
        args.owner,
        args.repo,
        args.pr,
        run_id=args.run_id,
        framework=frameworks[0],
        standards_content=standards_content,
        prompt_dir=primary_pack.prompt_dir,
        review_domain=primary_pack.name,
    )
    print(json.dumps(result.model_dump(), indent=2))


if __name__ == "__main__":
    main()
