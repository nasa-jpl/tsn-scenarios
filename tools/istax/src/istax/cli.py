import argparse
import os
import sys

import argcomplete
import dotenv
import requests

from istax import Istax, IstaxError

ENVAR_PROXY = "ISTAX_PROXY"


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def parse_opts():
    parser = argparse.ArgumentParser(
        prog="istax",
        description="IStaX configuration tool",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--username", "-u", default="admin", help="host username")
    parser.add_argument("--password", "-p", default="", help="host password")
    parser.add_argument(
        "--proxy",
        "-x",
        type=parse_proxy,
        metavar="[HOST:]PORT",
        default=os.environ.get(ENVAR_PROXY),
        help="proxy requests through a SOCKS5 proxy. HOST part defaults to localhost.",
    )

    commands = parser.add_subparsers(dest="command")

    activate = commands.add_parser(
        "activate",
        help="activate a stored configuration",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    activate.add_argument("host", help="hostname or IP address of the switch")
    activate.add_argument(
        "filename",
        help="switch filename to activate",
    )

    download = commands.add_parser(
        "download",
        aliases=["dl"],
        help="download the running configuration",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    download.add_argument(
        "--output", "-o", help="output file"
    ).completer = (  # ty: ignore[unresolved-attribute] on completer
        argcomplete.FilesCompleter
    )
    download.add_argument(
        "--filename",
        "-f",
        default="running-config",
        help="switch filename to download",
    )
    download.add_argument("host", help="hostname or IP address of the switch")

    upload = commands.add_parser(
        "upload",
        aliases=["ul"],
        help="upload the running configuration",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    upload.add_argument(
        "--dry-run",
        "-n",
        action=argparse.BooleanOptionalAction,
        help="print config with a dummy port map without uploading",
    )
    upload.add_argument(
        "--merge",
        "-m",
        action=argparse.BooleanOptionalAction,
        help="merge uploaded configuration with running configuration instead of replacing it",
    )
    upload.add_argument(
        "--filename",
        "-f",
        default="running-config",
        help="switch filename to upload to",
    )
    upload.add_argument("host", help="hostname or IP address of the switch")
    upload.add_argument(
        "files",
        nargs="*",
        help="configuration file, multiple files are concatenated.",
    ).completer = (  # ty: ignore[unresolved-attribute] on completer
        argcomplete.FilesCompleter
    )

    argcomplete.autocomplete(parser)

    return parser, parser.parse_args()


def parse_proxy(proxy: str) -> str:
    if "://" in proxy:
        return proxy
    if proxy.isdecimal():
        return f"localhost:{proxy}"
    else:
        return f"socks5h://{proxy}"


def main_raw():
    dotenv.load_dotenv()
    parser, opts = parse_opts()
    match opts.command:
        case "activate":
            Istax(
                host=opts.host,
                username=opts.username,
                password=opts.password,
                proxy=opts.proxy,
            ).activate(opts.filename)
        case "download":
            Istax(
                host=opts.host,
                username=opts.username,
                password=opts.password,
                proxy=opts.proxy,
            ).download(opts.filename)
        case "upload":
            Istax(
                host=opts.host,
                username=opts.username,
                password=opts.password,
                proxy=opts.proxy,
            ).upload(
                files=opts.files,
                dry_run=opts.dry_run,
                merge=opts.merge,
                filename=opts.filename,
            )
        case _:
            parser.print_help(file=sys.stderr)



def main():
    try:
        main_raw()
    except (
        requests.exceptions.ConnectionError  # ty: ignore[unresolved-attribute] on exceptions
    ) as e:
        eprint("error: " + str(e))
        sys.exit(1)
    except IstaxError as e:
        eprint("error: " + str(e))
        if e.__cause__ is not None:
            eprint(f"cause: {e.__cause__}")
        sys.exit(1)


if __name__ == "__main__":
    main()
