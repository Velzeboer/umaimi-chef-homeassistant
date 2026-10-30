"""Runs the integration in Home Assistant's test harness against a real UmamiList server.

Build the server first (./gradlew :server:installDist in the server's repository), or point UMAIMI_SERVER at it.
"""

from collections.abc import Iterator
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.request

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

# The server to test against: UMAIMI_SERVER, or the one built next to this folder (./gradlew :server:installDist).
SERVER = Path(os.environ.get("UMAIMI_SERVER") or Path(__file__).parents[2] / "server/build/install/server/bin/server")
EMAIL, PASSWORD = "test@example.com", "correct horse"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _post(url: str, body: dict, token: str | None = None) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read() or b"{}")


@pytest.fixture
def server(socket_enabled) -> Iterator[str]:
    """A fresh server with one account (EMAIL / PASSWORD); yields its URL. Needs the network, on 127.0.0.1 only."""
    if not SERVER.exists():
        pytest.fail(f"Build the server first: ./gradlew :server:installDist ({SERVER} is missing)")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with tempfile.TemporaryDirectory() as data:
        proc = subprocess.Popen(
            [str(SERVER)], env={**os.environ, "DATA_DIR": data, "PORT": str(port)},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        url = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(url + "/health")
                    break
                except OSError:
                    time.sleep(0.1)
            _post(url + "/api/auth/register", {"email": EMAIL, "password": PASSWORD, "name": "Tester"})
            yield url
        finally:
            proc.terminate()
            proc.wait()


@pytest.fixture
def login(server: str):
    """Logs in to the test server directly (not through Home Assistant); returns a token."""
    return lambda: _post(server + "/api/auth/login", {"email": EMAIL, "password": PASSWORD})["token"]


@pytest.fixture
def api_post(server: str):
    return lambda path, body, token: _post(server + path, body, token)
