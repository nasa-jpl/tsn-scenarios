from copy import copy
from dataclasses import dataclass
import os
from typing import Literal

from dotenv import load_dotenv
from ixnetwork_restpy import SessionAssistant
import pytest


def pytest_configure():
    pytest.any_test_failed = False


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """
    Set a global on failure so that fixtures can use it to disable cleanup so
    that we can inspect the state of the system.
    """

    report = yield

    if report.when == "call" and report.failed:
        pytest.any_test_failed = True

    return report


def parse_ports(ports: str) -> [int]:
    """
    Parse a list of ports.

    >>> parse_ports("1,2,3")
    [1, 2, 3]

    >>> parse_ports("1, 2, 3")
    [1, 2, 3]

    >>> parse_ports("one, two")
        ...
    ValueError: invalid literal for int() with base 10: 'one'
    """

    tokens = ports.split(",")
    return [int(token.strip()) for token in tokens]


def read_env(
    variables: dict[str, Literal["optional", "required"]],
) -> dict[str, str | None]:
    """
    Read and validate the environment.
    """

    load_dotenv()

    env = {}

    for variable, optionality in variables.items():
        env[variable] = os.getenv(variable)
        match optionality:
            case "optional":
                pass
            case "required":
                assert variable in os.environ

    return env


@dataclass
class Config:
    chassis: str
    username: str
    password: str
    ports: list[int]
    debug: DebugConfig


@pytest.fixture(scope="session")
def config():
    """
    Load configuration from .env file and the environment.
    """

    load_dotenv()

    env = read_env(
        {
            "IXN_PROXY": "optional",
            "IXN_ADDRESS": "required",
            "IXN_USER": "required",
            "IXN_PASS": "required",
            "IXN_PORTS": "required",
        }
    )

    if env["IXN_PROXY"]:
        os.environ["ALL_PROXY"] = env["IXN_PROXY"]

    config = Config(
        chassis=env["IXN_ADDRESS"],
        username=env["IXN_USER"],
        password=env["IXN_PASS"],
        ports=parse_ports(env["IXN_PORTS"]),
    )

    print_config = copy(config)
    print_config.password = "******"
    print(print_config)

    return config


@pytest.fixture(scope="module")
def session(config, request):
    remainder, filename = os.path.split(request.path)
    remainder, dirname = os.path.split(remainder)
    scenario = filename.replace("test_", "").replace(".py", "")
    session_name = f"{dirname}-{scenario}"

    session = SessionAssistant(
        IpAddress=config.chassis,
        UserName=config.username,
        Password=config.password,
        LogLevel=SessionAssistant.LOGLEVEL_INFO,
        ClearConfig=True,
        SessionName=session_name,
    )

    yield session

    # Prevent cleanup on failure so that we can inspect the state of the system
    if not pytest.any_test_failed:
        session.Session.remove()


@pytest.fixture(scope="module")
def ixn(session):
    return session.Ixnetwork
