from copy import copy
from dataclasses import dataclass
import datetime
import logging
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from ixnetwork_restpy import BatchAdd, SessionAssistant
import pytest

from istax import Istax

# Enable pytest assertion rewriting for helpers
# See https://docs.pytest.org/en/stable/how-to/writing_plugins.html#assertion-rewriting
pytest.register_assert_rewrite("ixnetwork_restpy_helpers")

logging.Formatter.formatTime = (
    lambda self, record, datefmt=None: datetime.datetime.fromtimestamp(
        record.created, datetime.timezone.utc
    )
    .astimezone()
    .isoformat(timespec="seconds")
)
logger = logging.getLogger(__name__)


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
class SwitchConfig:
    platform: str
    host: str
    username: str
    password: str


@dataclass
class Config:
    chassis: str
    username: str
    password: str
    ports: list[int]
    switch: SwitchConfig
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
            "ISTAX_HOST": "optional",
            "ISTAX_USER": "optional",
            "ISTAX_PASS": "optional",
        }
    )

    if env["IXN_PROXY"]:
        os.environ["ALL_PROXY"] = env["IXN_PROXY"]

    config = Config(
        chassis=env["IXN_ADDRESS"],
        username=env["IXN_USER"],
        password=env["IXN_PASS"],
        ports=parse_ports(env["IXN_PORTS"]),
        switch=SwitchConfig(
            platform="istax",
            host=env["ISTAX_HOST"],
            username=env["ISTAX_USER"],
            password=env["ISTAX_PASS"],
        ),
        debug=DebugConfig(
            reuse_session=False,
            reuse_topology=False,
        ),
    )

    print_config = copy(config)
    print_config.password = "******"
    print_config.switch.password = "******"
    logger.info(print_config)

    return config


def scenario_from_mod_path(path: str):
    remainder, filename = os.path.split(path)
    _remainder, dirname = os.path.split(remainder)
    feature = dirname
    subfeature = filename.replace("test_", "").replace(".py", "")
    return feature, subfeature


@pytest.fixture(scope="module")
def session(config, request):
    session_name = "-".join(scenario_from_mod_path(request.path))

    logger.info(f"Creating IxNetwork session '{session_name}'")
    session = SessionAssistant(
        IpAddress=config.chassis,
        UserName=config.username,
        Password=config.password,
        LogLevel=SessionAssistant.LOGLEVEL_NONE,
        ClearConfig=not config.debug.reuse_session,
        SessionName=session_name,
    )

    session.Ixnetwork.Globals.PortTestOptions.EnableDpdkPerformanceAcceleration = True

    yield session

    # Prevent cleanup on failure so that we can inspect the state of the system
    if not pytest.any_test_failed and not config.debug.reuse_session:
        logger.info(f"Removing session '{session_name}'")
        session.Session.remove()


@pytest.fixture(scope="module")
def ixn(session):
    return session.Ixnetwork


@pytest.fixture(scope="module")
def vports(config, ixn):
    logger.info(f"Creating virtual ports for physical ports {config.ports}")
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
    logger.info(f"Releasing physical ports {config.ports}")
    ixn.Vport.find().ReleasePort()


@pytest.fixture(scope="module")
def switch(config, request):
    feature, subfeature = scenario_from_mod_path(request.path)
    match config.switch.platform:
        case "istax":
            project_root = get_project_root()
            scenarios_root = os.path.join(project_root, "scenarios")
            short_cfg = os.path.join("istax", feature, f"{subfeature}.cfg")
            switch_cfg_file = os.path.join(scenarios_root, short_cfg)
            logger.info(
                f"Uploading switch configuration '{short_cfg}' to '{config.switch.host}'"
            )
            switch = Istax(
                host=config.switch.host,
                username=config.switch.username,
                password=config.switch.password,
                proxy=None,  # We use the ALL_PROXY environment variable instead
            )
            switch.upload(
                files=[switch_cfg_file],
            )
        case _:
            raise NotImplementedError

    return switch


def get_project_root():
    for p in Path(__file__).parents:
        if (p / ".git").is_dir():
            return p

    raise RuntimeError("Could not find project root")
