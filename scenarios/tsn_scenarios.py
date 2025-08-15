import ixnetwork.IxNetwork


def main():
    parser = argparse.ArgumentParser(
        description=
        'Tool to configure and run TSN scenarios. It takes a topology and traffic configuration as input',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    subparsers = parser.add_subparsers(help='Subcommand we want to run')

    # Parent parser for use by multiple subcommands
    base_create_run_parser = argparse.ArgumentParser(add_help=False)
    base_create_run_parser.add_argument(
        '--api-server-ip',
        default='',
        type=str,
        required=False,
        help=
        """Specify the IP address of the lander. Used only with --fsw-autoboot option"""
    )

    # Parser for create sub-command
    parser_create = subparsers.add_parser(
        'create',
        help=
        """Creates a session and configures the network devices for the desired setup""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser_create.add_argument('-b',
                               '--rover-binary',
                               type=str,
                               required=False,
                               help="""Path to rover binary""")
    parser_create.add_argument('-B',
                               '--base-station-binary',
                               type=str,
                               required=False,
                               help="""Path to base station binary""")
    parser_create.add_argument('-d',
                               '--rover-dictionary',
                               type=str,
                               required=False,
                               help="""Path to rover dictionary""")
    parser_create.add_argument('-D',
                               '--base-station-dictionary',
                               type=str,
                               required=False,
                               help="""Path to base station dictionary""")
    parser_create.add_argument(
        '-p',
        '--rover-parameters',
        nargs='+',
        required=False,
        help=
        """List of rover PrmDb.dat files. It must either be only 1 value or the same as number of targets"""
    )
    parser_create.add_argument('-P',
                               '--base-station-parameters',
                               type=str,
                               required=False,
                               help="""Base station PrmDb.dat file.""")
    parser_create.add_argument(
        '-t',
        '--targets',
        type=str,
        required=True,
        nargs='+',
        help=
        """The targets to include in the configuration. See 'list-targets' command for choices"""
    )
    parser_create.add_argument('-o',
                               '--output-file',
                               type=str,
                               required=True,
                               help="""Output YAML file""")
    parser_create.add_argument(
        '--pse-kernel',
        type=str,
        default=
        './cadre-pse/formation-sensing/kernel/signed_distance_field.cl.voxl.bin',
        required=False,
        help="""Optional specification of PSE OpenCL kernel file.
                                Default is to assume script is is run from cadre-fsw directory and find default file."""
    )
    parser_create.add_argument('--ground-tools',
                               type=str,
                               required=False,
                               help="""Location of ground tools binaries.""")
    parser_create.add_argument(
        '--tasknets-dir',
        type=str,
        default='./cadre-pse/strategic-planner/tasknets/cmd_prod/tasknets',
        required=False,
        help="""Directory containing mexec tasknets for the base station""")
    parser_create.add_argument(
        '--base-station-pse-seq-dir',
        type=str,
        default=
        './cadre-pse/strategic-planner/tasknets/cmd_prod/sequences/base_station',
        required=False,
        help="""Directory containing PSE sequences for the base station""")
    parser_create.add_argument(
        '--rover-pse-seq-dir',
        type=str,
        default=
        './cadre-pse/strategic-planner/tasknets/cmd_prod/sequences/rover',
        required=False,
        help="""Directory containing PSE sequences for rovers""")
    parser_create.add_argument(
        '--moondb-params',
        type=str,
        default='./cadre-pse/moon-db/configs',
        required=False,
        help="""Directory containing MoonDb parameters""")
    parser_create.add_argument(
        '--flight-seq-dir',
        type=str,
        default='./config/bin',
        required=False,
        help="""Directory containing pre-built flight sequences""")
    parser_create.add_argument(
        '--mcb-seq-dir',
        type=str,
        default='./config/mcb-systems-engineering/bin',
        required=False,
        help=
        """Location of directories containing rover sequence files. konfigurator will search 
                                     in that location for target specific directories named according to the targets table. 
                                     See 'konfigurator list-targets'""")
    parser_create.add_argument(
        '--startup-scripts-dir',
        type=str,
        default='./fprime-cadre/FprimeCadre/StartUp',
        required=False,
        help=
        """Directory containing the set of .bash startup scripts for FSW autoboot"""
    )
    parser_create.add_argument(
        '--gpr-cmd-dir',
        type=str,
        default='./config/cadre-flight-sequences/gpr_utils',
        required=False,
        help="""Directory containing the set of GPR command scripts""")
    parser_create.add_argument(
        '--rover-hashes-file',
        type=str,
        default='',
        required=False,
        help="""Path to rover hashes.txt file for ASSERT file ids""")
    parser_create.add_argument(
        '--base-station-hashes-file',
        type=str,
        default='',
        required=False,
        help="""Path to base station hashes.txt file for ASSERT file ids""")
    parser_create.add_argument(
        '--common-parameter-file',
        action='store_true',
        required=False,
        help="""Use one parameter file for all agents""")
    parser_create.add_argument(
        '--legacy-fsw',
        action='store_true',
        required=False,
        help=
        """Indicate if FSW <= Release 3.1 since this results in different file-paths"""
    )
    parser_create.set_defaults(func=create_config)

    # Parser for edit sub-command
    parser_edit = subparsers.add_parser(
        'edit',
        help="""Edit an existing konfig and create new yaml""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser_edit.add_argument(
        '-c',
        '--config',
        type=str,
        required=True,
        help="""Path to the yaml config file we want to edit""")
    parser_edit.add_argument('-o',
                             '--output-file',
                             type=str,
                             required=True,
                             help="""Output YAML file""")
    parser_edit.add_argument(
        "--set",
        metavar="TARGET.SECTION=VALUE",
        nargs='+',
        required=True,
        help=
        """Set a number of key-value pairs, where the key is a konfig TARGET.SECTION.
        e.g. "fm-1.mode_manager_sequences". Value is the new SRC location of the file(s).
                                   Do not put spaces before or after the = sign. """
    )
    parser_edit.set_defaults(func=edit_config)

    # Parser for validate sub-command
    parser_validate = subparsers.add_parser(
        'validate', help="""Validates that a yaml is valid""")
    parser_validate.add_argument(
        '-c',
        '--config',
        type=str,
        required=True,
        help="""Path to the yaml config file we want to validate""")
    parser_validate.add_argument('-r',
                                 '--refresh',
                                 action='store_true',
                                 required=False,
                                 default=False,
                                 help="""Update the konfig md5sums""")
    parser_validate.set_defaults(func=validate_config)

    # Parser for copy sub-command
    parser_upload = subparsers.add_parser(
        'upload',
        help="""Uploads a YAML config and its relevant files to cadrestor""")
    parser_upload.add_argument(
        '-c',
        '--config',
        type=str,
        required=True,
        help="""Path to the yaml config file we want to copy""")
    parser_upload.add_argument(
        '-u',
        '--user',
        type=str,
        required=False,
        help=
        """Optional username to use for the target machine. Defaults to current user"""
    )
    parser_upload.add_argument('-r',
                               '--remote-host',
                               default='cadredev',
                               type=str,
                               required=False,
                               help="""Upload configs to a remote host""")
    parser_upload.add_argument('-n',
                               '--name',
                               type=str,
                               required=False,
                               help="""New name for uploaded YAML config""")
    parser_upload.add_argument(
        '-d',
        '--destination',
        default='/data/testbeds/file-store',
        type=str,
        required=False,
        help=
        """Path to where the files will be copied. Will be copied to remote host if --remote-host is given"""
    )
    parser_upload.add_argument(
        '-L',
        '--yaml-location',
        default='/data/testbeds/konfigs',
        type=str,
        required=False,
        help="""Path to where the YAML config will be copied.""")
    parser_upload.set_defaults(func=upload_config)

    # Parent parser for deploy and run
    base_deploy_run_parser = argparse.ArgumentParser(add_help=False)
    # Base parser for deploy and run
    base_deploy_run_parser.add_argument(
        '-c',
        '--config',
        type=str,
        required=True,
        help="""Path to the yaml config file we want to deploy""")
    base_deploy_run_parser.add_argument(
        '-J',
        '--jumphost',
        type=str,
        default='',
        required=False,
        help=
        """Argument to forward to -J flag for ssh and scp which controls which
                                intermediate hops to use.  The default is to use no intermediate jump host,
                                so no -J will be passed to ssh and scp. If you are running on your local
                                machine and need to access the device through cadredev, then you would use
                                -J cadredev. If you are already on the same network as the device, you should
                                omit this option altogether.""")
    base_deploy_run_parser.add_argument(
        '-u',
        '--user',
        default='root',
        type=str,
        required=False,
        help="""Optional username to use for the target machine""")
    base_deploy_run_parser.add_argument(
        '--no-seqs',
        action='store_true',
        default=False,
        required=False,
        help=
        """If set, then do not deploy ModeManager and FPManager sequence files"""
    )
    base_deploy_run_parser.add_argument(
        '--ignore-md5sum',
        action='store_true',
        default=False,
        required=False,
        help="""Ignore the file md5sums when deploying and running a config.
                                              This is useful when you are doing development and just want to
                                              keep running the same config over and over"""
    )
    base_deploy_run_parser.add_argument(
        '--base-station',
        type=str,
        default='',
        required=False,
        help="""Target that will be assigned as the base station.
                                     If not given, then the first target in the config file is used"""
    )
    base_deploy_run_parser.add_argument(
        '--leader',
        type=str,
        default='',
        required=False,
        help="""Target that will be assigned as the leader.
                                     If not given, then the first target in the config file is used."""
    )

    base_deploy_run_parser.add_argument(
        '--base-station-is-rover',
        action='store_true',
        default=False,
        required=False,
        help=
        """If set, then base-station-is-rover flag is sent to FSW CLI args""")
    base_deploy_run_parser.add_argument(
        '--keep-moondb',
        action='store_true',
        default=False,
        required=False,
        help=
        """If set, then don't remove the previous moondb sqlite files prior to deploying"""
    )

    base_deploy_run_parser.add_argument(
        '--trace',
        required=False,
        action='store_true',
        default=False,
        help="""Run FSW with kernel scheduler trace""")

    base_deploy_run_parser.add_argument(
        '--tasknet-name',
        required=False,
        default='30/fs_flight.bin',
        help=
        """Name of tasknet file to use, relative to /data/cadre/util/pse/tasknets/gen"""
    )

    base_deploy_run_parser.add_argument(
        '--init-mode',
        required=False,
        default='',
        type=str,
        help="""Init mode to write to disk for ModeManager.
        Possible values: init, safe, egress, nominal, gpr, autonomy,
        autogpr, pre_sleep, cleanup, test""")

    # Parser for deploy sub-command
    parser_deploy = subparsers.add_parser(
        'deploy',
        help="""Deploys files from yaml to a set of agents""",
        parents=[base_deploy_run_parser])
    parser_deploy.add_argument(
        '-o',
        '--base-port',
        default=8000,
        type=int,
        required=False,
        help=
        """Optional base network port to allow non-default port usage. All port assignments
        for agents will be calculated to start from <base_port> + AGENT_ID * 100"""
    )
    parser_deploy.add_argument(
        '-L',
        '--log-dir',
        type=str,
        required=False,
        help=
        """Path to logs root folder which is where the timestamped run log folder
                            will go.  Defaults to '/data/testbeds/dm'.""")
    parser_deploy.add_argument(
        '--fsw-autoboot',
        action='store_true',
        default=False,
        required=False,
        help=
        """This option enables creation and deployment of FSW autoboot scripts"""
    )
    parser_deploy.add_argument(
        '--lander-ip',
        default='',
        type=str,
        required=False,
        help=
        """Specify the IP address of the lander. Used only with --fsw-autoboot option"""
    )
    parser_deploy.add_argument(
        '--vnv',
        default=True,
        type=bool,
        required=False,
        help=
        """When running deploy subcommand, always assuming it is for VNV testing
        purposes which sets up the necessary logging directories""")

    parser_deploy.add_argument('--gdb',
                               default='True',
                               type=str,
                               required=False,
                               help="""Run FSW using gdb""")

    parser_deploy.add_argument(
        '--no-rsvp',
        required=False,
        action='store_true',
        default=False,
        help="""Flag to skip automatic setup and launch of RSVP""")

    parser_deploy.add_argument(
        '-l',
        '--local-only',
        required=False,
        action='store_true',
        default=False,
        help="""Flag to run locally from /proj and not /data""")

    parser_deploy.set_defaults(func=deploy_config)

    # Parser for run sub-command
    parser_run = subparsers.add_parser(
        'run',
        parents=[base_deploy_run_parser],
        help="""Deploy and then run a config on a set of agents""")

    parser_run.add_argument(
        '-g',
        '--gdb',
        action='store_true',
        default=False,
        required=False,
        help="""Run FSW executable in debug mode with gdb. This does not verify
        that gdb is installed on the host""")
    parser_run.add_argument(
        '-L',
        '--log-dir',
        default='./logs',
        type=str,
        required=False,
        help=
        """Path to logs root folder which is where the timestamped test log folder
                            will go.  Defaults to './logs'.""")
    parser_run.add_argument(
        '-o',
        '--base-port',
        default=8000,
        type=int,
        required=False,
        help=
        """Optional base network port to allow non-default port usage. All port assignments
                            for agents will be calculated to start from <base_port> + AGENT_ID * 100"""
    )
    parser_run.add_argument(
        '-r',
        '--rsvp-lite-enable',
        action='store_true',
        default=False,
        required=False,
        help="""Sets up the required port connections for RSVP-lite""")
    parser_run.add_argument(
        '-t',
        '--cadre-ground-dir',
        default='./cadre-ground/build/bin/',
        required=False,
        help="""Specifies the location of the cadre-ground tools""")
    parser_run.add_argument(
        '--chroot-cmd',
        default='./bookworm',
        required=False,
        help="""Command to use for entering the chroot prior to executing FSW"""
    )

    parser_run.set_defaults(func=run_config)

    # Parser for cleanup sub-command
    parser_cleanup = subparsers.add_parser(
        'cleanup',
        help=
        """Remove unneeded files from the targets to put them into a clean state for deployment"""
    )

    parser_cleanup.add_argument(
        '-J',
        '--jumphost',
        type=str,
        default='',
        required=False,
        help=
        """Argument to forward to -J flag for ssh and scp which controls which
                                intermediate hops to use.  The default is to use no intermediate jump host,
                                so no -J will be passed to ssh and scp. If you are running on your local
                                machine and need to access the device through cadredev, then you would use
                                -J cadredev. If you are already on the same network as the device, you should
                                omit this option altogether.""")

    parser_cleanup.add_argument(
        '-u',
        '--user',
        default='root',
        type=str,
        required=False,
        help=
        """Optional username to use for the target machine. Defaults to current user"""
    )

    parser_cleanup.add_argument(
        '-t',
        '--targets',
        type=str,
        required=True,
        nargs='+',
        help=
        """The targets to include cleanup. See 'list-targets' command for choices"""
    )

    parser_cleanup.set_defaults(func=cleanup)

    # Parser for list-targets sub-command
    parser_list_targets = subparsers.add_parser(
        'list-targets', help="""List the supported targets""")
    parser_list_targets.set_defaults(func=list_targets)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
