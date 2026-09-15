"""Command-line entry point for the query-to-page agent."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from scripts import workflow_state as workflow

from .pipeline import PipelineError, analyze, generate_briefs, initialize, run_qa
from .provider import DeepSeekClient, FixtureClient, JsonModel, ProviderError


def _model(args: argparse.Namespace) -> JsonModel:
    if args.fixture_json:
        return FixtureClient(Path(args.fixture_json))
    return DeepSeekClient.from_env()


def _handle_init(args: argparse.Namespace) -> dict:
    return initialize(Path(args.config), Path(args.run_dir))


def _handle_analyze(args: argparse.Namespace) -> dict:
    return analyze(Path(args.config), Path(args.run_dir), _model(args))


def _handle_briefs(args: argparse.Namespace) -> dict:
    return generate_briefs(Path(args.run_dir), _model(args))


def _handle_qa(args: argparse.Namespace) -> dict:
    return run_qa(Path(args.run_dir), Path(args.manifest), _model(args))


def _handle_gate(args: argparse.Namespace) -> dict:
    return workflow.decide_gate(args)


def _handle_status(args: argparse.Namespace) -> dict:
    return workflow.load_state(Path(args.run_dir))


def _add_model_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--fixture-json",
        help="Use a local JSON response instead of DeepSeek (for demos/tests)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="q2p",
        description="Turn a query bank into a human-gated 3–5 page batch.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init_parser = commands.add_parser("init", help="Initialize a run and validate all inputs")
    init_parser.add_argument("--config", required=True)
    init_parser.add_argument("--run-dir", required=True)
    init_parser.set_defaults(handler=_handle_init)

    analyze_parser = commands.add_parser(
        "analyze", help="Cluster, map, prioritize, and create the Gate 1 packet"
    )
    analyze_parser.add_argument("--config", required=True)
    analyze_parser.add_argument("--run-dir", required=True)
    _add_model_argument(analyze_parser)
    analyze_parser.set_defaults(handler=_handle_analyze)

    gate_parser = commands.add_parser("gate", help="Record a named human decision")
    gate_parser.add_argument("--run-dir", required=True)
    gate_parser.add_argument("--gate", type=int, choices=(1, 2), required=True)
    gate_parser.add_argument("--decision", choices=("approve", "reject"), required=True)
    gate_parser.add_argument("--reviewer", required=True)
    gate_parser.add_argument("--notes")
    gate_parser.add_argument("--warnings-accepted", nargs="*")
    gate_parser.set_defaults(handler=_handle_gate)

    brief_parser = commands.add_parser(
        "briefs", help="Generate briefs and a draft page manifest after Gate 1"
    )
    brief_parser.add_argument("--run-dir", required=True)
    _add_model_argument(brief_parser)
    brief_parser.set_defaults(handler=_handle_briefs)

    qa_parser = commands.add_parser(
        "qa", help="Run configured checks and create the Gate 2 packet"
    )
    qa_parser.add_argument("--run-dir", required=True)
    qa_parser.add_argument("--manifest", required=True)
    _add_model_argument(qa_parser)
    qa_parser.set_defaults(handler=_handle_qa)

    status_parser = commands.add_parser("status", help="Print the current run state")
    status_parser.add_argument("--run-dir", required=True)
    status_parser.set_defaults(handler=_handle_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except (
        PipelineError,
        ProviderError,
        workflow.WorkflowError,
        OSError,
        subprocess.TimeoutExpired,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
