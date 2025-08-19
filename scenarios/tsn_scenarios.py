#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests[socks]>=2.32.4",
#   "ixnetwork-restpy >= 1.7.0",
#   "python-dotenv >= 1.1.1",
#   "pyyaml",
# ]
# ///
#

from ixnetwork.IxNetwork import IxNetwork
import argparse


def create_session(args):
    """Entry function to create a session"""
    ix_session = IxNetwork(args.api_server_ip, args.chassis_ip,
                           args.chassis_slot_number, args.session_name)

    ix_session.create_session(args.topology, args.traffic, args.log,
                              args.dry_run, args.force_port_ownership,
                              args.verbosity)


def run_session(args):
    """Entry function to create a session"""
    ix_session = IxNetwork(args.api_server_ip, args.chassis_ip,
                           args.chassis_slot_number, args.session_name)

    ix_session.run_session(args.run_time_sec, args.dry_run)


def main():
    parser = argparse.ArgumentParser(
        description=
        'Tool to configure and run TSN scenarios. It takes a topology and traffic configuration as input',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    subparsers = parser.add_subparsers(help='Subcommand we want to run')

    # Parent parser for use by multiple subcommands
    parser_base = argparse.ArgumentParser(add_help=False)
    parser_base.add_argument(
        '--api-server-ip',
        default='192.168.1.21',
        type=str,
        required=False,
        help="""Specify the IP address of the RestAPI server""")

    parser_base.add_argument(
        '--chassis-ip',
        default='192.168.1.21',
        type=str,
        required=False,
        help="""Specify the IP address of the Ixia chassis""")

    parser_base.add_argument('--chassis-slot-number',
                             default=1,
                             type=int,
                             required=False,
                             help="""Specify the Ixia chassis slot number""")

    parser_base.add_argument(
        '--session-name',
        default='',
        type=str,
        required=True,
        help="""Specify session name. This must be a unique name""")

    parser_base.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        required=False,
        help="""If set then we only interact with the session without
        affecting the actual traffic or other active users""")

    # Parser for create sub-command
    parser_create = subparsers.add_parser(
        'create',
        parents=[parser_base],
        help="""Creates a session and configures the network devices for the
        desired setup""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser_create.add_argument('--topology',
                               type=str,
                               required=True,
                               help="""Path to YAML file that defines the
                               endpoint toplogy""")

    parser_create.add_argument('--traffic',
                               type=str,
                               required=True,
                               help="""Path to YAML file that defines the
                               traffic items for this session""")

    parser_create.add_argument(
        '-f',
        '--force-port-ownership',
        action='store_true',
        required=False,
        help="""If set, then take ownership of the ports forcefully
        if necessary""")

    parser_create.add_argument('-l',
                               '--log',
                               type=str,
                               required=False,
                               help="""Path to the log file to use. Default
                               will be the session name with an appended
                               timestamp""")

    parser_create.add_argument('--verbosity',
                               choices=[
                                   "none", "info", "warning", "request",
                                   "request_response", "all"
                               ],
                               required=False,
                               help="""Verbosity level for logging.""")

    parser_create.set_defaults(func=create_session)

    # Parser for run sub-command
    parser_run = subparsers.add_parser(
        'run',
        parents=[parser_base],
        help="""Runs a previously created session""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser_run.add_argument(
        '-t',
        '--run-time-sec',
        type=float,
        required=False,
        default=10.0,
        help="""The run time for this scenario in seconds""")

    parser_run.set_defaults(func=run_session)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
