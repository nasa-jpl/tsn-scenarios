from io import StringIO
import fileinput
from http.cookiejar import CookieJar
import os
from pathlib import Path
import sys
import time
from typing import TextIO

import requests
import jinja2
from yaspin import yaspin, Spinner

PortMap = list[dict[str, str]]


class IstaxError(Exception):
    def __init__(self, message):
        super().__init__(message)


class Istax:
    host: str

    def __init__(
        self, host: str, username: str, password: str, proxy: str, quiet: bool = True
    ):
        self.ll = IstaxLowLevel(host, username, password, proxy)
        self.host = host
        self.quiet = quiet

    def upload(
        self,
        files: list[str],
        dry_run: bool = False,
        merge: bool = False,
        filename: str = "running-config",
    ) -> None:
        paths = self.expand_paths(files)

        # Concat inputs and insure only one end statement
        config = StringIO()
        for line in fileinput.input(paths):
            if line != "end\n":
                config.write(line)
        config.write("end\n")
        config.seek(0)

        if dry_run:
            ports = self.dummy_port_map()
        else:
            with Progress("logging in", self.quiet):
                self.ll.login()
            with Progress("fetching port map", self.quiet):
                ports = self.ll.get_port_map()

        config = self.render_config(ports, config)

        if dry_run:
            print(config.read())
        else:
            with Progress("uploading config", self.quiet):
                self.ll.config_upload(filename, merge, config)
            if filename == "running-config":
                with Progress("activating config", self.quiet):
                    self.ll.config_activate_status()

    def activate(self, filename: str):
        with Progress("logging in", self.quiet):
            self.ll.login()
        with Progress("activating config", self.quiet):
            self.ll.config_activate(filename)

    def download(self, filename: str):
        with Progress("logging in", self.quiet):
            self.ll.login()
        with Progress("downloading config", self.quiet):
            self.ll.config_download(filename)

    def search_path(self):
        project_root = self.get_project_root()
        return os.path.join(project_root, "scenarios", "istax")

    def render_config(self, ports: PortMap, config) -> StringIO:
        search_path = self.search_path()
        loader = jinja2.FileSystemLoader(search_path)
        environment = jinja2.Environment(loader=loader, trim_blocks=True, keep_trailing_newline=True)
        template = environment.from_string(config.read())
        data = {"hostname": self.host, "ports": ports}
        rendered_template = template.render(data)
        return StringIO(rendered_template)

    def get_project_root(self):
        for p in Path(__file__).parents:
            if (p / ".git").is_dir():
                return p

        raise RuntimeError("Could not find project root")

    def dummy_port_map(self) -> PortMap:
        return [{"name": f"DummyEthernet 1/{i}"} for i in range(1, 10)]

    def expand_paths(self, paths: list[str]) -> list[str]:
        """
        Expand paths relative to cwd then relative to search path.
        """
        search_path = self.search_path()

        paths = [Path(path) for path in paths]
        for i, path in enumerate(paths):
            if path.is_absolute():
                if not path.is_file():
                    raise OSError(f"path '{path}' is not a file")
            elif path.is_file():
                # path relative to cwd: use as is
                pass
            else:
                search_relative_path = Path(search_path) / path
                if search_relative_path.is_file():
                    paths[i] = search_relative_path
                else:
                    raise OSError(f"path '{path}' not found")

        return paths

    def get_psfp_gate_status(self):
        result = self.ll._json_rpc_call("psfp.status.gate.get")
        status = [
            {"GateClosedDueToInvalidRx": entry["val"]["GateClosedDueToInvalidRx"]}
            for entry in result
        ]
        return status

    def clear_psfp_gate_closed_due_to_invalid_rx(self, stream_id: int):
        self.ll._json_rpc_call(
            "psfp.control.gate_clear.set",
            stream_id,
            {"ClearGateClosedDueToInvalidRx": True},
        )


class Progress:
    class DevNull:
        closed = False

        def write(*args):
            pass

        def isatty(self):
            return True

        def flush(self):
            pass

    def __init__(self, text, quiet):
        if quiet:
            stream = self.DevNull()
        else:
            stream = sys.stderr
        self.spinner = yaspin(text=text, color="blue", stream=stream)

    def __enter__(self) -> Spinner:
        self.spinner.start()
        return self.spinner

    def __exit__(self, type, value, traceback) -> bool:
        if type is IstaxError:
            self.spinner.red.fail()
            return False
        elif type:
            self.spinner.red.fail()
            return False
        else:
            self.spinner.green.ok()
            return True


class IstaxLowLevel:
    session: requests.Session
    host: str
    username: str
    password: str

    def __init__(self, host: str, username: str, password: str, proxy: str | None):
        self.session = self.create_session(proxy)
        self.host = host
        self.username = username
        self.password = password

    def create_session(self, proxy: str | None) -> requests.Session:
        session = requests.Session()
        session.cookies = CookieJar()

        if proxy:
            proxies = {
                "http": proxy,
                "https": proxy,
            }
            session.proxies.update(proxies)

        return session

    def config_upload(self, filename: str, merge: bool, config: TextIO):
        data = {
            "file_name": filename,
            "merge": str(merge).lower(),
        }

        files = {
            "source_file": config,
        }
        self.session.post(
            f"http://{self.host}/config/icfg_conf_upload", data=data, files=files
        )

    def login(self):
        data = {
            "user": self.username,
            "password": self.password,
        }

        response = self.session.post(f"http://{self.host}/login", data=data)
        if response.status_code != 200:
            raise IstaxError(f"unable to login to '{self.host}'")

    def config_activate(self, filename: str):
        data = {
            "file_name": filename,
        }

        self.session.post(f"http://{self.host}/config/icfg_conf_activate", data=data)

        self.istax_config_activate_status()

    def config_download(self, filename: str):
        data = {
            "file_name": filename,
        }

        response = self.session.post(
            f"http://{self.host}/config/icfg_conf_download", data=data
        )
        print(response.text)

    def config_activate_status(self):
        timeout = time.time() + 90
        while True:
            try:
                response = self.session.get(
                    f"http://{self.host}/config/icfg_conf_activate", timeout=1
                )
            except requests.Timeout:
                if time.time() > timeout:
                    raise IstaxError("timed out waiting for response")
                time.sleep(3)
                continue
            firstline = response.text.partition("\n")[0]
            if firstline == "<html>":
                if time.time() > timeout:
                    raise IstaxError("timed out waiting for response")
                time.sleep(3)
                continue
            elif response.text.partition("\n")[0] == "DONE":
                break
            else:
                raise IstaxError(f"activation failed with:\n{response.text.strip()}")

    def _json_rpc_call(self, method: str, *args):
        data = {
            "method": method,
            "id": "jsonrpc",
            "params": args,
        }

        # WORKAROUND: IStaX returns a bad response header (extraneous and malformed
        # HTTP status line).  This causes urllib to raise an internal exception
        # before it parses the content-length.  Because of this, the post call
        # below blocks until TCP timeout which takes a few seconds.  We can work
        # around this by forcing the server to close the connection after
        # responding with the following header.
        headers = {"Connection": "close"}

        response = self.session.post(
            f"http://{self.host}/json_rpc", json=data, headers=headers
        )

        data = response.json()
        return data["result"]

    def get_port_map(self) -> PortMap:
        result = self._json_rpc_call("port.namemap.get")
        ports = [self.transform_port_name(entry["key"]) for entry in result]
        return ports

    def transform_port_name(self, name: str) -> dict[str, str]:
        (speed, index) = name.split()
        match speed:
            case "Gi":
                return {"name": f"GigabitEthernet {index}"}
            case "10G":
                return {"name": f"10GigabitEthernet {index}"}
            case _:
                raise
