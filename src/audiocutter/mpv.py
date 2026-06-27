import json
import os
import random
import socket
import subprocess
import time
from collections.abc import Generator, Sequence
from pathlib import Path
from typing import Any


def mpv_open(
    file: Path,
    ipc: Path,
) -> tuple[subprocess.Popen, socket.socket]:
    devnull_write = open(os.devnull, 'w')
    devnull_read = open(os.devnull, 'r')
    proc = subprocess.Popen(
        [
            'mpv',
            '--no-video',
            '--keep-open',
            '--quiet',
            f'--input-ipc-server={ipc}',
            str(file),
        ],
        stdin=devnull_read,
        stdout=devnull_write,
        stderr=devnull_write,
    )

    while not ipc.exists():
        time.sleep(0.05)

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(str(ipc))

    return proc, sock


def _read_results(
    string: str | bytes,
) -> Generator[dict[str, Any], None, None]:
    for x in string.splitlines():
        yield json.loads(x)


def _wait_for(sock: socket.socket, wait: str | int) -> dict[str, Any]:
    while True:
        for res in _read_results(sock.recv(2**12)):
            if isinstance(wait, int):
                if res.get('request_id') == wait:
                    return res
            else:
                if res.get('event') == wait:
                    return res


def send_command(
    sock: socket.socket,
    cmd: Sequence[str],
    event: str | None = None,
) -> dict[str, Any]:
    req_id = random.randint(0, 2**12)
    sock.sendall(
        (json.dumps({'command': cmd, 'request_id': req_id}) + '\n').encode()
    )
    return _wait_for(sock, event if event else req_id)


def wait_for_load(sock: socket.socket) -> None:
    _wait_for(sock, 'playback-restart')


def get_duration(sock: socket.socket) -> float:
    return send_command(sock, ['get_property', 'duration'])['data']


def set_ab(
    sock: socket.socket,
    start: float,
    end: float,
    reset: bool = False,
) -> None:
    if reset:
        send_command(sock, ['ab-loop'])
    send_command(sock, ['keypress', 'space'])
    send_command(sock, ['seek', str(end), 'absolute'], event='seek')
    send_command(sock, ['ab-loop'])
    send_command(sock, ['seek', str(start), 'absolute'], event='seek')
    send_command(sock, ['ab-loop'])
    send_command(sock, ['keypress', 'space'])
