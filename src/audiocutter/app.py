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
from .mpv import Mpv


class App:
    def __init__(self, file: Path, output: Path | None) -> None:
        self.file = file
        self.output = output
        self.wave = load_wave(file)

        with TemporaryDirectory() as base:
            ipc = Path(base) / 'ipc.sock'
            self.mpv = Mpv(self.file, ipc)

        self.duration = self.mpv.get_duration()
        self.points = [0, self.duration]
        self.point_selected = 0
        self.jump_size = 1

        self.mpv.set_ab(*self.points)

        self.top_chset = (' ', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█')
        self.bot_chset = (' ', '▔', '🮂', '🮃', '▀', '🮄', '🮅', '🮆', '█')
        self.height = 1 * 8 - 1

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
    def build_waveform_2(self, width: int, height: int) -> Sequence[str]:
        values = make_waveform_values(self.wave, width - 2)

        raw_lines = [
            *reversed(build_waveform(self.top_chset, values, height, 1)),
            *build_waveform(self.bot_chset, values, height),
        ]

        raw_lines[0] = f'┌{raw_lines[0]}┐'
        for i, line in enumerate(raw_lines[1:-1], 1):
            raw_lines[i] = f'│{line}│'
        raw_lines[-1] = f'└{raw_lines[-1]}┘'

        return raw_lines

    def build_ui(self) -> str:
        start, end = sorted(self.points)
        width, _ = shutil.get_terminal_size()

        left_pos = int((start / self.duration) * (width - 2 - 1))
        right_pos = int((end / self.duration) * (width - 2 - 1))

        lines = []

        status_bar = f'jump size = {self.jump_size:.2f}s'.ljust(width, ' ')
        if len(status_bar) <= width:
            lines.append(status_bar)

        lines.extend(
            colorize_line(line, left_pos + 1, right_pos + 1, '\x1b[38;5;8m')
            for line in self.build_waveform_2(width, self.height)
        )

        arrows = f'{" " * (left_pos + 1)}^'
        if left_pos != right_pos:
            arrows += f'{" " * (right_pos - left_pos - 1)}^'
        arrows = arrows.ljust(width, ' ')
        lines.append(arrows)

        return '\n'.join(lines)

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
            raise AppExitException
        else:
            return False

    def cut_audio(self) -> None:
        self.mpv.terminate()
        s, e = sorted(self.points)
        print()
        cut_audio(self.file, self.output, s, e)
        raise AppExitException

    def loop(self) -> None:
        try:
            ui_string = self.build_ui()
            print(ui_string, end='', flush=True)

            while True:
                if self.handle_keypress(get_input()):
                    s, e = sorted(self.points)
                    self.mpv.set_ab(s, e, reset=True)
                n = ui_string.count('\n')
                ui_string = self.build_ui()
                print(f'\x1b[{n}F{ui_string}', end='', flush=True)
        except KeyboardInterrupt:
            sys.exit(1)
        except AppExitException:
            pass
        finally:
            self.mpv.terminate()

    def run(self) -> None:
        with terminal_context():
            self.loop()


class AppExitException(Exception):
    pass


def build_waveform(
    chset: Sequence[str], values: Sequence[float], max_: int, offset: int = 0
) -> Sequence[str]:
    res = [[] for _ in range(0, max_ + offset, 8)]
    for v in values:
        bv = int(v * max_) + offset
        for i in range(len(res)):
            res[i].append(chset[max(0, min(bv - i * 8, 8))])
    return [''.join(v) for v in res]


def colorize_line(line: str, left_pos: int, right_pos: int, color: str) -> str:
    reset = '\x1b[39m'
    return (
        f'{color}{line[:left_pos]}{reset}'
        f'{line[left_pos : right_pos + 1]}'
        f'{color}{line[right_pos + 1 :]}{reset}'
    )


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
