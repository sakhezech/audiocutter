import contextlib
import os
import sys
import termios
import tty
from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory

from .ffmpeg import cut_audio
from .mpv import get_duration, mpv_open, set_ab, wait_for_load


class App:
    def __init__(self, file: Path, output: Path | None) -> None:
        self.file = file
        self.output = output

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
            'swap': ('s', ' '),
            'left': ('<', 'h'),
            'right': ('>', 'l'),
            'small': ('-', 'j'),
            'big': ('+', 'k'),
            'exit': ('\x1b'),
            'done': ('\n',),
        }

    def build_ui(self) -> str:
        start, end = sorted(self.points)
        width, _ = os.get_terminal_size()
        width -= 2

        left_pos = int((start / self.duration) * width)
        right_pos = int((end / self.duration) * width)

        from_left = left_pos
        from_right = width - right_pos
        delta = right_pos - left_pos

        if from_right > 0:
            delta += 1
            from_right -= 1

        control = f'jump size = {self.jump_size:.2f}s'
        bar = f'[{"-" * from_left}{"#" * delta}{"-" * from_right}]'
        arrows = f'{" " * (from_left + 1)}^'
        if delta > 1:
            arrows += f'{" " * (delta - 2)}^'

        parts = []
        if len(control) <= width:
            parts.append(control)
        parts.extend((bar, arrows))
        return '\n'.join(parts)

    def add_to_curr_point(self, jump: float) -> None:
        v = self.points[self.point_selected]
        self.points[self.point_selected] = min(max(0, v + jump), self.duration)

    def handle_keypress(self, key: str) -> bool:
        if key in self.keybinds['swap']:
            self.point_selected = (self.point_selected + 1) % 2
            return False
        elif key in self.keybinds['small']:
            self.jump_size /= 2
            return False
        elif key in self.keybinds['big']:
            self.jump_size *= 2
            return False
        elif key in self.keybinds['left']:
            self.add_to_curr_point(-self.jump_size)
            return True
        elif key in self.keybinds['right']:
            self.add_to_curr_point(self.jump_size)
            return True
        elif key in self.keybinds['done']:
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
            pass
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
