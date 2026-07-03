import array
import contextlib
import functools
import os
import shutil
import sys
import termios
import threading
import tty
from collections.abc import Generator, Iterator, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

from .ffmpeg import cut_audio, load_wave
from .mpv import Mpv

np = None
try:
    import numpy as np
except ImportError:
    pass

LOOP_MODE_TIME = 1.0


class App:
    def __init__(self, file: Path, output: Path | None) -> None:
        self.file = file
        if not self.file.exists():
            raise ValueError(f'file does not exist: {self.file}')
        self.output = output
        self.wave_data = None

        self._ui_string = ''
        self._running = False
        self.loop_mode = False

        with TemporaryDirectory() as base:
            ipc = Path(base) / 'ipc.sock'
            self.mpv = Mpv(self.file, ipc)

        self.duration = self.mpv.get_duration()
        self.points = Points(self.duration)
        self.jump_size = 1

        s, e = self.points
        self.mpv.set_ab(s, e)

        self.top_chset = (' ', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█')
        self.bot_chset = (' ', '▔', '🮂', '🮃', '▀', '🮄', '🮅', '🮆', '█')
        self.height = 1

        self._load_wave()
        self.wave_thread.join(0.1)

        self.keybinds = {
            'left': ('<', 'h', '\x1b[D'),
            'right': ('>', 'l', '\x1b[C'),
            'up': ('+', 'k', '\x1b[A'),
            'down': ('-', 'j', '\x1b[B'),
            'swap': (' ',),
            'loop': ('m',),
            'seek': ('n',),
            'cut': ('\n',),
            'exit': ('\x1b', 'q'),
        }

    def _load_wave(self) -> None:
        def func() -> None:
            wave_data = load_wave(self.file).readframes(-1)

            width, _ = shutil.get_terminal_size()
            self.make_waveform_values(wave_data, width - 2)

            self.wave_data = wave_data
            if self._running:
                self.print_ui()

        self.wave_thread = threading.Thread(target=func, daemon=True)
        self.wave_thread.start()

    @functools.cache
    def make_waveform_values(
        self, wave_data: bytes, width: int
    ) -> Sequence[float]:
        return make_waveform_values(wave_data, width)

    @functools.cache
    def build_waveform_2(self, width: int, height: int) -> Sequence[str]:
        assert self.wave_data
        values = self.make_waveform_values(self.wave_data, width - 2)

        max_ = height * 8 - 1
        raw_lines = [
            *reversed(build_waveform(self.top_chset, values, max_, 1)),
            *build_waveform(self.bot_chset, values, max_),
        ]

        raw_lines[0] = f'┌{raw_lines[0]}┐'
        for i, line in enumerate(raw_lines[1:-1], 1):
            raw_lines[i] = f'│{line}│'
        raw_lines[-1] = f'└{raw_lines[-1]}┘'

        return raw_lines

    @functools.cache
    def build_placeholder_waveform(self, width, height: int) -> Sequence[str]:
        raw_lines = [' ' * (width - 2) for _ in range(height * 2)]
        raw_lines[height - 1] = '▁' * (width - 2)

        raw_lines[0] = f'┌{raw_lines[0]}┐'
        for i, line in enumerate(raw_lines[1:-1], 1):
            raw_lines[i] = f'│{line}│'
        raw_lines[-1] = f'└{raw_lines[-1]}┘'

        return raw_lines

    def build_ui(self) -> str:
        start, end = self.points
        width, _ = shutil.get_terminal_size()

        left_pos = int((start / self.duration) * (width - 2 - 1))
        right_pos = int((end / self.duration) * (width - 2 - 1))

        lines = []

        statuses = [f'jump size = {self.jump_size:.2f}s']
        if self.loop_mode:
            statuses.append('loop mode')
        if not self.wave_data:
            statuses.append('loading wave')
        status_bar = '; '.join(statuses).ljust(width, ' ')
        if len(status_bar) <= width:
            lines.append(status_bar)

        build_waveform = (
            self.build_waveform_2
            if self.wave_data
            else self.build_placeholder_waveform
        )
        lines.extend(
            colorize_line(line, left_pos + 1, right_pos + 1, '\x1b[38;5;8m')
            for line in build_waveform(width, self.height)
        )

        arrows = f'{" " * (left_pos + 1)}^'
        if left_pos != right_pos:
            arrows += f'{" " * (right_pos - left_pos - 1)}^'
        arrows = arrows.ljust(width, ' ')
        lines.append(arrows)

        return '\n'.join(lines)

    def handle_keypress(self, key: str) -> bool:
        if key in self.keybinds['left']:
            self.points.selected -= self.jump_size
            return True
        elif key in self.keybinds['right']:
            self.points.selected += self.jump_size
            return True
        elif key in self.keybinds['up']:
            self.jump_size *= 2
            return False
        elif key in self.keybinds['down']:
            self.jump_size /= 2
            return False
        elif key in self.keybinds['swap']:
            self.points.toggle_selected()
            return self.loop_mode
        elif key in self.keybinds['loop']:
            self.loop_mode = not self.loop_mode
            return True
        elif key in self.keybinds['seek']:
            self.points.selected = self.get_playback_time()
            self.points.toggle_selected()
            return self.points.selected_index == 0
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

    def print_ui(self) -> None:
        n = self._ui_string.count('\n')
        self._ui_string = self.build_ui()
        if n:
            print(f'\x1b[{n}F', end='')
        print(self._ui_string, end='', flush=True)

    def get_ab_points(self) -> tuple[float, float]:
        s, e = self.points
        if self.loop_mode:
            if self.points.selected_index == 0:
                e = min(s + LOOP_MODE_TIME, e)
            else:
                s = max(s, e - LOOP_MODE_TIME)
        return s, e

    def get_playback_time(self) -> float:
        s, e = self.get_ab_points()
        t = self.mpv.get_position()
        if t is None:
            t = s
        if t <= s:
            t = e - s + t
        return t

    def run(self) -> None:
        self._running = True
        try:
            self.print_ui()
            while True:
                if self.handle_keypress(get_input()):
                    s, e = self.get_ab_points()
                    self.mpv.set_ab(s, e, True)
                self.print_ui()
        except KeyboardInterrupt:
            sys.exit(1)
        except AppExitException:
            pass
        finally:
            self._running = False
            self.mpv.terminate()


class Points:
    def __init__(self, duration: float) -> None:
        assert duration > 0
        self._duration = duration
        self._points = [0, self._duration]
        self.selected_index = 0

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self._points!r})'

    def toggle_selected(self) -> None:
        self.selected_index ^= 1

    def __getitem__(self, key: int) -> float:
        return self._points[key]

    def __setitem__(self, key: int, value: float) -> None:
        self._points[key] = max(0, min(value, self._duration))
        if self._points[0] > self._points[1]:
            self._points[0], self._points[1] = self._points[1], self._points[0]
            self.toggle_selected()

    def __iter__(self) -> Iterator[float]:
        return self._points.__iter__()

    @property
    def left(self):
        return self[0]

    @left.setter
    def left(self, value):
        self[0] = value

    @property
    def right(self):
        return self[1]

    @right.setter
    def right(self, value):
        self[1] = value

    @property
    def selected(self):
        return self[self.selected_index]

    @selected.setter
    def selected(self, value):
        self[self.selected_index] = value


class AppExitException(Exception):
    pass


def make_waveform_values(wave_data: bytes, width: int) -> Sequence[float]:
    data = bytearray(wave_data)
    n = len(data) // 2 // width * 2
    total = n * width
    data = data[:total]

    if np:
        arr = np.frombuffer(data, np.int16).reshape((width, -1))
        maxes = np.amax(np.abs(arr), axis=1)
        return (maxes / np.max(maxes)).tolist()
    else:
        maxes = [
            abs(max(array.array('h', data[i : i + n]), key=abs))
            for i in range(0, total, n)
        ]
        max_max = max(maxes)
        return [v / max_max for v in maxes]


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
