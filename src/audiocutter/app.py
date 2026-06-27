import contextlib
import os
import sys
import termios
import tty
from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory

from .mpv import get_duration, mpv_open, set_ab, wait_for_load


class App:
    def __init__(self, file: Path) -> None:
        self.file = file

        with TemporaryDirectory() as base:
            ipc = Path(base) / 'ipc.sock'
            self.proc, self.sock = mpv_open(file, ipc)
        wait_for_load(self.sock)

        self.p1 = 0
        self.p2 = self.duration = get_duration(self.sock)

        set_ab(self.sock, self.p1, self.p2)

        self.p1_selected = True

        self.jump_size = 1

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
        start, end = sorted((self.p1, self.p2))
        width, _ = os.get_terminal_size()
        width -= 2

        left_pos = int((start / self.duration) * width)
        right_pos = int((end / self.duration) * width)

        from_left = left_pos
        from_right = width - right_pos
        delta = right_pos - left_pos

        if delta == 0:
            delta = 1
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

    def handle_keypress(self, key: str) -> bool:
        if key in self.keybinds['swap']:
            self.p1_selected = not self.p1_selected
            return False
        elif key in self.keybinds['small']:
            self.jump_size /= 2
            return False
        elif key in self.keybinds['big']:
            self.jump_size *= 2
            return False
        elif key in self.keybinds['left']:
            if self.p1_selected:
                self.p1 -= self.jump_size
            else:
                self.p2 -= self.jump_size
            return True
        elif key in self.keybinds['right']:
            if self.p1_selected:
                self.p1 += self.jump_size
            else:
                self.p2 += self.jump_size
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
        # TODO: implement
        pass

    def loop(self) -> None:
        ui_string = self.build_ui()
        print(ui_string, end='', flush=True)

        try:
            while True:
                if self.handle_keypress(get_input()):
                    s, e = sorted((self.p1, self.p2))
                    set_ab(self.sock, s, e, reset=True)
                n = ui_string.count('\n')
                ui_string = self.build_ui()
                print(f'\x1b[{n}F\x1b[J{ui_string}', end='', flush=True)
        except KeyboardInterrupt:
            pass

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
