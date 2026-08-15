import argparse
import json

from application.review_service import run_review
from infrastructure.logging_config import configure_logging


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Run the code review agent")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--framework", default="dotnet")
    parser.add_argument("--run-id", default="LOCAL_RUN")
    args = parser.parse_args()

    result = run_review(
        args.owner,
        args.repo,
        args.pr,
        run_id=args.run_id,
        framework_hint=args.framework,
    )
    print(json.dumps(result.model_dump(), indent=2))


if __name__ == "__main__":
    main()
