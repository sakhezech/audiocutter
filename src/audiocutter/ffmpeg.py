import array
import io
import struct
import subprocess
import wave
from collections.abc import Sequence
from pathlib import Path

np = None
try:
    import numpy as np
except ImportError:
    pass


def cut_audio(
    file: Path, output: Path | None, start: float, end: float
) -> None:
    base_name = file.name.removesuffix(file.suffix)
    name = Path(f'{base_name}_{start:.2f}_to_{end:.2f}{file.suffix}')
    if output is None:
        output = name
    elif output.exists() and output.is_dir():
        output /= name

    codec = output.suffix if output.suffix != file.suffix else 'copy'
    subprocess.run(
        [
            'ffmpeg',
            '-hide_banner',
            '-loglevel',
            'quiet',
            '-stats',
            '-i',
            str(file),
            '-c',
            codec,
            '-ss',
            str(start),
            '-to',
            str(end),
            '-f',
            file.suffix.removeprefix('.'),
            str(output),
        ]
    ).check_returncode()


def _patch_ffmpeg_stdin_wave(data: bytes) -> bytes:
    arr = bytearray(data)
    size = len(data)

    struct.pack_into('<I', arr, 4, size - 8)

    pos = 12
    while pos + 8 <= size:
        chunk_name = arr[pos : pos + 4]
        chunk_size = struct.unpack_from('<I', arr, pos + 4)[0]
        if chunk_name == b'data':
            data_size = size - (pos + 8)
            struct.pack_into('<I', arr, pos + 4, data_size)
            return bytes(arr)
        pos += 8 + chunk_size
    raise ValueError('no data chunk')


def load_wave(file: Path) -> wave.Wave_read:
    proc = subprocess.run(
        ['ffmpeg', '-i', str(file), '-c:a', 'pcm_s16le', '-f', 'wav', '-'],
        capture_output=True,
    )
    proc.check_returncode()
    return wave.Wave_read(io.BytesIO(_patch_ffmpeg_stdin_wave(proc.stdout)))


def make_waveform_values(wav: wave.Wave_read, width: int) -> Sequence[float]:
    wav.setpos(0)
    n = wav.getnframes() // width

    if np:
        data = wav.readframes(n * width)
        arr = np.frombuffer(data, np.int16).reshape((width, -1))
        maxes = np.amax(np.abs(arr), axis=1)
        return (maxes / np.max(maxes)).tolist()
    else:
        maxes = []
        for _ in range(width):
            data = wav.readframes(n)
            maxes.append(abs(max(array.array('h', data), key=abs)))
        max_max = max(maxes)
        return [v / max_max for v in maxes]
