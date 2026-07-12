# audiocutter

TUI audio trimming program.

## Keybinds

- <kbd>h</kbd> / <kbd>&#8592;</kbd> / <kbd><</kbd> - move left
- <kbd>l</kbd> / <kbd>&#8594;</kbd> / <kbd>></kbd> - move right
- <kbd>k</kbd> / <kbd>&#8593;</kbd> / <kbd>+</kbd> - increase jump size
- <kbd>j</kbd> / <kbd>&#8595;</kbd> / <kbd>-</kbd> - decrease jump size
- <kbd>space</kbd> - select the other handle
- <kbd>m</kbd> - loop mode (loop audio around the selected handle)
- <kbd>n</kbd> - seek to current playback position
- <kbd>t</kbd> - trim silence
- <kbd>enter</kbd> - cut audio
- <kbd>esc</kbd> / <kbd>q</kbd> - exit

## Options

```console
$ audiocutter -h
usage: audiocutter [-h] [-o OUTPUT] file

positional arguments:
  file                 audio file

options:
  -h, --help           show this help message and exit
  -o, --output OUTPUT  output file
```

## Installation

`numpy` is optional, but it will speed up waveform generation.

Via `pipx`.

```console
pipx install 'git+https://github.com/sakhezech/audiocutter[numpy]'
```

Via `uv`.

```console
uv tool install 'git+https://github.com/sakhezech/audiocutter[numpy]'
```
