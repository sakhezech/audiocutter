import json
import os
import random
import socket
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any


class Mpv:
    def __init__(self, file: Path, ipc: Path) -> None:
        devnull_write = open(os.devnull, 'w')
        devnull_read = open(os.devnull, 'r')
        self.proc = subprocess.Popen(
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

        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(str(ipc))

    def terminate(self) -> None:
        self.proc.terminate()

    def _wait_for(self, wait: str | int) -> dict[str, Any]:
        buff = bytearray()
        while True:
            read = self.sock.recv(2**12)
            try:
                results = [
                    json.loads(x) for x in (buff + read).splitlines() if x
                ]
            except json.JSONDecodeError:
                buff.extend(read)
                continue
            buff.clear()
            for res in results:
                if isinstance(wait, int):
                    if res.get('request_id') == wait:
                        return res
                else:
                    if res.get('event') == wait:
                        return res

    def send_command(
        self,
        cmd: Sequence[str],
        event: str | None = None,
    ) -> dict[str, Any]:
        req_id = random.randint(0, 2**12)
        self.sock.sendall(
            (
                json.dumps({'command': cmd, 'request_id': req_id}) + '\n'
            ).encode()
        )
        return self._wait_for(event if event else req_id)

    def wait_for_load(self) -> None:
        self._wait_for('playback-restart')

    def get_duration(self) -> float:
        return self.send_command(['get_property', 'duration'])['data']

    def set_ab(
        self,
        start: float,
        end: float,
        reset: bool = False,
    ) -> None:
        if reset:
            self.send_command(['ab-loop'])
        self.send_command(['keypress', 'space'])
        self.send_command(['seek', str(end), 'absolute'], event='seek')
        self.send_command(['ab-loop'])
        self.send_command(['seek', str(start), 'absolute'], event='seek')
        self.send_command(['ab-loop'])
        self.send_command(['keypress', 'space'])
