import contextlib
import functools
import os
import shutil
import sys
import termios
import tty
from collections.abc import Generator, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

from .ffmpeg import cut_audio, load_wave, make_waveform_values
from .mpv import get_duration, mpv_open, set_ab, wait_for_load


class App:
    def __init__(self, file: Path, output: Path | None) -> None:
        self.file = file
        self.output = output
        self.wave = load_wave(file)

        with TemporaryDirectory() as base:
            ipc = Path(base) / 'ipc.sock'
            self.proc, self.sock = mpv_open(file, ipc)
        wait_for_load(self.sock)

        self.duration = get_duration(self.sock)
        self.points = [0, self.duration]
        self.point_selected = 0
        self.jump_size = 1

        set_ab(self.sock, *self.points)

        self.keybinds = {
            'left': ('<', 'h', '\x1b[D'),
            'right': ('>', 'l', '\x1b[C'),
            'up': ('+', 'k', '\x1b[A'),
            'down': ('-', 'j', '\x1b[B'),
            'swap': (' ',),
            'cut': ('\n',),
            'exit': ('\x1b', 'q'),
        }

    @functools.cache
    def get_waveform_values(self, width: int) -> Sequence[float]:
        return make_waveform_values(self.wave, width)

    def build_ui(self) -> str:
        start, end = sorted(self.points)
        width, _ = shutil.get_terminal_size()
        width -= 2

        left_pos = int((start / self.duration) * (width - 1))
        right_pos = int((end / self.duration) * (width - 1))

        control = f'jump size = {self.jump_size:.2f}s'
        values = self.get_waveform_values(width)

        gray = '\x1b[38;5;8m'  # ]
        reset = '\x1b[39m'  # ]

        lines = []
        for chset, surr in [
            (['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'], '┌┐'),
            (['▔', '🮂', '🮃', '▀', '🮄', '🮅', '🮆', '█'], '└┘'),
        ]:
            l_surr, r_surr = surr
            line = ''.join(chset[int(v * (len(chset) - 1))] for v in values)
            line = (
                f'{gray}{l_surr}{line[:left_pos]}{reset}'
                f'{line[left_pos : right_pos + 1]}'
                f'{gray}{line[right_pos + 1 :]}{r_surr}{reset}'
            )
            lines.append(line)

        arrows = f'{" " * (left_pos + 1)}^'
        if left_pos != right_pos:
            arrows += f'{" " * (right_pos - left_pos - 1)}^'

        parts = []
        if len(control) <= width:
            parts.append(control)
        parts.extend((*lines, arrows))
        return '\n'.join(parts)

    def add_to_curr_point(self, jump: float) -> None:
        v = self.points[self.point_selected]
        self.points[self.point_selected] = min(max(0, v + jump), self.duration)

    def handle_keypress(self, key: str) -> bool:
        if key in self.keybinds['left']:
            self.add_to_curr_point(-self.jump_size)
            return True
        elif key in self.keybinds['right']:
            self.add_to_curr_point(self.jump_size)
            return True
        elif key in self.keybinds['up']:
            self.jump_size *= 2
            return False
        elif key in self.keybinds['down']:
            self.jump_size /= 2
            return False
        elif key in self.keybinds['swap']:
            self.point_selected = (self.point_selected + 1) % 2
            return False
        elif key in self.keybinds['cut']:
            self.cut_audio()
            return False
        elif key in self.keybinds['exit']:
            self.proc.terminate()
            sys.exit(0)
        else:
            return False

    def cut_audio(self) -> None:
        self.proc.terminate()
        s, e = sorted(self.points)
        print()
        cut_audio(self.file, self.output, s, e)
        sys.exit(0)

    def loop(self) -> None:
        try:
            ui_string = self.build_ui()
            print(ui_string, end='', flush=True)

            while True:
                if self.handle_keypress(get_input()):
                    s, e = sorted(self.points)
                    set_ab(self.sock, s, e, reset=True)
                n = ui_string.count('\n')
                ui_string = self.build_ui()
                print(f'\x1b[{n}F\x1b[J{ui_string}', end='', flush=True)
        except KeyboardInterrupt:
            sys.exit(1)
        finally:
            self.proc.terminate()

    def run(self) -> None:
        with terminal_context():
            self.loop()


@contextlib.contextmanager
def terminal_context() -> Generator[None, None, None]:
    fd = sys.stdin.fileno()
    old = tty.setcbreak(fd)
    print('\x1b[?25l', end='', flush=True)
    try:
        yield
    finally:
        print('\x1b[?25h', end='', flush=True)
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def get_input() -> str:
    fd = sys.stdin.fileno()
    char = sys.stdin.read(1)
    if char == '\x1b':
        os.set_blocking(fd, False)
        char += sys.stdin.read(2**8)
        os.set_blocking(fd, True)
    return char
