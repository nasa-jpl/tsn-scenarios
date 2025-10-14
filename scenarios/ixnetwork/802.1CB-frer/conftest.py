import os

from dotenv import load_dotenv
from ixnetwork_restpy import SessionAssistant
import pytest


@pytest.fixture(scope="session")
def config():
    load_dotenv()

    return {
        "chassis": os.getenv("IXN_ADDRESS"),
        "user": os.getenv("IXN_USER"),
        "pass": os.getenv("IXN_PASS"),
        "ports": [5, 6, 7],
    }


@pytest.fixture(scope="module")
def session(config, request):
    remainder, filename = os.path.split(request.path)
    remainder, dirname = os.path.split(remainder)
    scenario = filename.replace("test_", "").replace(".py", "")
    session_name = f"{dirname}-{scenario}"

    session = SessionAssistant(
        IpAddress=config["chassis"],
        UserName=config["user"],
        Password=config["pass"],
        LogLevel=SessionAssistant.LOGLEVEL_INFO,
        ClearConfig=True,
        SessionName=session_name,
    )
    yield session
    session.Session.remove()


@pytest.fixture(scope="module")
def ixn(session):
    return session.Ixnetwork
