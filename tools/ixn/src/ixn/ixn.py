from .IxNetwork import IxNetwork
from dotenv import load_dotenv

import argparse
import sys
import traceback
from ixnetwork_restpy import ConnectionError


def parse_opts():
    parser = argparse.ArgumentParser(
        description="""Tool to configure and run TSN scenarios. It takes a
        topology and traffic configuration as input""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    commands = parser.add_subparsers(
        help="Subcommand we want to run", dest="commands", required=True
    )

    # Parent parser for use by multiple subcommands
    parser_base = argparse.ArgumentParser(add_help=False)

    parser_base.add_argument(
        "--session-name",
        default="",
        type=str,
        required=True,
        help="""Specify session name. This must be a unique name""",
    )

    parser_base.add_argument(
        "--dry-run",
        action="store_true",
        required=False,
        help="""If set then we only interact with the session without
        affecting the actual traffic or other active users""",
    )

    parser_base.add_argument(
        "-l",
        "--log",
        type=str,
        required=False,
        help="""Path to the log file to use. Default
                               will be the session name with an appended
                               timestamp""",
    )

    parser_base.add_argument(
        "--verbosity",
        choices=["none", "info", "warning", "request", "request_response", "all"],
        required=False,
        help="""Verbosity level for logging.""",
    )

    # Parser for create sub-command
    parser_create = commands.add_parser(
        "create",
        parents=[parser_base],
        help="""Creates a session and configures the network devices for the
        desired setup""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser_create.add_argument(
        "--topology",
        type=str,
        required=True,
        help="""Path to YAML file that defines the
                               endpoint toplogy""",
    )

    parser_create.add_argument(
        "--traffic",
        type=str,
        required=True,
        help="""Path to YAML file that defines the
                               traffic items for this session""",
    )

    parser_create.add_argument(
        "-f",
        "--force-port-ownership",
        action="store_true",
        required=False,
        help="""If set, then take ownership of the ports forcefully
        if necessary""",
    )

    parser_create.set_defaults(func=create_session)

    # Parser for run sub-command
    parser_run = commands.add_parser(
        "run",
        parents=[parser_base],
        help="""Runs a previously created session""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser_run.add_argument(
        "-t",
        "--run-time-sec",
        type=float,
        required=False,
        default=10.0,
        help="""The run time for this scenario in seconds""",
    )

    parser_run.set_defaults(func=run_session)

    # Parser for stop sub-command
    parser_stop = commands.add_parser(
        "stop",
        parents=[parser_base],
        help="""Stops a previously started session""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser_stop.set_defaults(func=stop_session)

    # Parser for validate sub-command
    parser_validate = commands.add_parser(
        "validate",
        parents=[parser_base],
        help="""Validates a session that is currently running""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser_validate.add_argument(
        "--test-func",
        required=True,
        help="""The function in the IxValidate class to use for validation""",
    )

    parser_validate.set_defaults(func=validate_session)

    return parser.parse_args()


def create_session(args):
    """Entry function to create a session"""
    ix_network = _create_ix_network(args)
    ix_network.create_session(
        args.topology, args.traffic, args.dry_run, args.force_port_ownership
    )


def run_session(args):
    """Entry function to create a session"""
    ix_network = _create_ix_network(args)
    ix_network.run_session(args.run_time_sec, args.dry_run)


def stop_session(args):
    """Entry function to create a session"""
    ix_network = _create_ix_network(args)
    ix_network.stop_session(args.dry_run)


def validate_session(args):
    """Entry function to create a session"""
    ix_network = _create_ix_network(args)
    ix_network.validate_session(validation_func=args.test_func)


def _create_ix_network(args):
    return IxNetwork(
        args.session_name,
        args.verbosity,
        args.log,
    )


def main():
    try:
        load_dotenv()
        opts = parse_opts()
        opts.func(opts)
    except ConnectionError as e:
        print("Error: " + str(e))
        sys.exit(1)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
