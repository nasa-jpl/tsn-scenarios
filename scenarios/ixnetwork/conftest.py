from copy import copy
from dataclasses import dataclass
import os
from typing import Literal

from dotenv import load_dotenv
from ixnetwork_restpy import BatchAdd, SessionAssistant
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


def parse_ports(ports: str) -> list[int]:
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
) -> dict[str, str]:
    """
    Read and validate the environment.
    """

    load_dotenv()

    env = {}

    for variable, optionality in variables.items():
        env[variable] = os.getenv(variable, "")
        match optionality:
            case "optional":
                pass
            case "required":
                assert variable in os.environ

    return env


@dataclass
class DebugConfig:
    reuse_session: bool
    reuse_topology: bool


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
        debug=DebugConfig(
            reuse_session=False,
            reuse_topology=False,
        ),
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
        ClearConfig=not config.debug.reuse_session,
        SessionName=session_name,
    )

    session.Ixnetwork.Globals.PortTestOptions.EnableDpdkPerformanceAcceleration = True

    yield session

    # Prevent cleanup on failure so that we can inspect the state of the system
    if not pytest.any_test_failed and not config.debug.reuse_session:
        session.Session.remove()


@pytest.fixture(scope="module")
def ixn(session):
    return session.Ixnetwork

@pytest.fixture(scope="module")
def vports(config, ixn):
    with BatchAdd(ixn):
        for i, port in enumerate(config.ports):
            ixn.Vport.add(Name=i, Location=f"{config.chassis};1;{port}")

    yield ixn.Vport.find()

    # On the topic of virtual port to physical port connection:
    #
    # If physical ports are not already connected to vports in another
    # session, then vports will automatically connect to assigned
    # physical ports on traffic apply. However, if physical ports ARE
    # assigned to vports in another session, traffic apply will fail with
    # a terse error.
    #
    # There are two ways to address this:
    #
    # 1. During setup (before the yield statement above), explicitly
    #    connect ports with force ownership
    # 2. During teardown (after the yield statement above), explicitly
    #    release ports
    #
    # We use option 2 since it is the safest. Option 2 prevents
    # automatically stealing ports from others.
    ixn.Vport.find().ReleasePort()
