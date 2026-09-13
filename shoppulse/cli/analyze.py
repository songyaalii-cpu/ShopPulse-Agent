"""Local JSON/Markdown CLI for the analytics graph."""

import argparse
import json

from shoppulse.agents import create_analytics_graph


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    result = create_analytics_graph().invoke({"original_query": args.query})["final_answer"]
    if args.format == "markdown" and isinstance(result.get("summary"), str):
        print(result["summary"])
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
