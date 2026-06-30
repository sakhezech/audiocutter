import io
import struct
import subprocess
import wave
from pathlib import Path


def cut_audio(
    file: Path, output: Path | None, start: float, end: float
) -> None:
    base_name = file.name.removesuffix(file.suffix)
    name = Path(f'{base_name}_{start:.2f}_to_{end:.2f}{file.suffix}')
    if output is None:
        output = name
    elif output.exists() and output.is_dir():
        output /= name

    subprocess.run(
        [
            'ffmpeg',
            '-hide_banner',
            '-loglevel',
            'fatal',
            '-stats',
            '-ss',
            str(start),
            '-to',
            str(end),
            '-i',
            str(file),
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
