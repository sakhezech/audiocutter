import argparse
from collections.abc import Sequence
from pathlib import Path

from .app import App, terminal_context


def cli(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser('audiocutter')
    parser.add_argument('file', type=Path, help='audio file')
    parser.add_argument('-o', '--output', type=Path, help='output file')

    args = parser.parse_args(argv)
    with terminal_context():
        App(args.file, args.output).run()


if __name__ == '__main__':
    cli(None)
