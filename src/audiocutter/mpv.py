import json
import os
import random
import socket
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SOCKET_WAIT_SLEEP_TIME = 0.05


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
            time.sleep(SOCKET_WAIT_SLEEP_TIME)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(str(ipc))

        try:
            self.get_duration()
        except MpvError:
            self._wait_for('file-loaded')

    def terminate(self) -> None:
        self.proc.terminate()

    def _wait_for(self, wait: str | int) -> dict[str, Any]:
        buff = bytearray()
        while True:
            exit_code = self.proc.poll()
            if exit_code is not None:
                raise MpvError(f'mpv exited with code: {exit_code}')
            buff.extend(self.sock.recv(2**12))
            try:
                results = [json.loads(x) for x in buff.splitlines() if x]
            except json.JSONDecodeError:
                continue
            buff.clear()
            for res in results:
                if res.get('error', 'success') != 'success':
                    raise MpvError(res['error'])
                if isinstance(wait, int):
                    if res.get('request_id') == wait:
                        return res
                else:
                    if res.get('event') == wait:
                        return res

    def send_command(
        self,
        cmd: Sequence[Any],
        event: str | None = None,
    ) -> dict[str, Any]:
        req_id = random.randint(0, 2**12)
        self.sock.sendall(
            (
                json.dumps({'command': cmd, 'request_id': req_id}) + '\n'
            ).encode()
        )
        return self._wait_for(event if event else req_id)

    def get_duration(self) -> float:
        return self.send_command(['get_property', 'duration'])['data']

    def get_position(self) -> float:
        return self.send_command(['get_property', 'audio-pts/full'])['data']

    def set_ab(self, start: float, end: float) -> None:
        self.send_command(['set_property', 'ab-loop-a', start])
        self.send_command(['set_property', 'ab-loop-b', end])

    def seek(self, time: float) -> None:
        self.send_command(['seek', time, 'absolute'], event='seek')


class MpvError(Exception):
    pass
