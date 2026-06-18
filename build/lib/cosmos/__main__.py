"""Command-line interface for CoSMoS.

Usage::

    python -m cosmos run <scenario> [options]
    python -m cosmos validate <scenario> [options]

Options::

    --path       Path to the CoSMoS run folder (or set COSMOS_PATH env var)
    --config     Configuration file name (default: config.toml)
    --cycle      Starting cycle (e.g. 20231213_00z)
    --last-cycle Last cycle to process (e.g. 20231215_00z)

Examples::

    python -m cosmos run tyndall_forecast --path=c:\\work\\cosmos\\run_folder
    python -m cosmos validate my_scenario --config=config_local.toml
    set COSMOS_PATH=c:\\work\\cosmos\\run_folder && python -m cosmos run my_scenario
"""

import argparse
import os
import sys


def main() -> None:
    """Parse arguments and run the requested CoSMoS command."""
    parser = argparse.ArgumentParser(
        prog="cosmos",
        description="CoSMoS — Coastal Storm Modelling System",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # -- Shared arguments --------------------------------------------------

    def add_common_args(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("scenario", help="Scenario name")
        sub.add_argument(
            "--path",
            default=None,
            help="Path to the CoSMoS run folder (default: COSMOS_PATH env var)",
        )
        sub.add_argument(
            "--config",
            default="config.toml",
            help="Configuration file name (default: config.toml)",
        )

    # -- run ---------------------------------------------------------------

    run_parser = subparsers.add_parser("run", help="Run a scenario")
    add_common_args(run_parser)
    run_parser.add_argument(
        "--cycle", default=None, help="Starting cycle (e.g. 20231213_00z)"
    )
    run_parser.add_argument("--last-cycle", default=None, help="Last cycle to process")

    # -- validate ----------------------------------------------------------

    validate_parser = subparsers.add_parser(
        "validate", help="Validate a scenario without running"
    )
    add_common_args(validate_parser)

    # -- post-process ------------------------------------------------------

    pp_parser = subparsers.add_parser("post-process", help="Post-process model results")
    add_common_args(pp_parser)
    pp_parser.add_argument("--cycle", default=None, help="Cycle to post-process")
    pp_parser.add_argument(
        "--models",
        default="all",
        help='Model names to post-process, comma-separated, or "all"',
    )

    # -- webviewer ---------------------------------------------------------

    wv_parser = subparsers.add_parser(
        "webviewer", help="Build the web viewer without running models"
    )
    add_common_args(wv_parser)
    wv_parser.add_argument(
        "--cycle", default=None, help="Cycle to build web viewer for"
    )

    # -- Parse -------------------------------------------------------------

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Resolve run folder path
    run_path = args.path or os.environ.get("COSMOS_PATH")
    if not run_path:
        print(
            "Error: No run folder path provided. "
            "Use --path or set the COSMOS_PATH environment variable."
        )
        sys.exit(1)

    if not os.path.exists(run_path):
        print(f"Error: Run folder does not exist: {run_path}")
        sys.exit(1)

    # Initialize CoSMoS
    from .cosmos import cosmos

    cosmos.initialize(run_path, config_file=args.config)

    # Dispatch command
    if args.command == "validate":
        ok = cosmos.validate(args.scenario)
        sys.exit(0 if ok else 1)

    elif args.command == "run":
        cosmos.run(
            args.scenario,
            cycle=args.cycle,
            last_cycle=args.last_cycle,
        )

    elif args.command == "post-process":
        models = args.models
        if models != "all":
            models = [m.strip() for m in models.split(",")]
        cosmos.post_process(args.scenario, model=models, cycle=args.cycle)

    elif args.command == "webviewer":
        cosmos.make_webviewer(args.scenario, cycle=args.cycle)


if __name__ == "__main__":
    main()
