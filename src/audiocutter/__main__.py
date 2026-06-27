import argparse
from collections.abc import Sequence
from pathlib import Path

from .app import App


def cli(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser('audiocutter')
    parser.add_argument('file', type=Path, help='audio file')

    args = parser.parse_args(argv)
    App(args.file).run()


if __name__ == '__main__':
    cli(None)
