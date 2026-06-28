import io
import struct
import subprocess
import wave
from collections.abc import Sequence
from pathlib import Path


def cut_audio(
    file: Path, output: Path | None, start: float, end: float
) -> None:
    if output is None:
        base_name = file.name.removesuffix(file.suffix)
        output = Path(f'{base_name}_{start:.2f}_to_{end:.2f}{file.suffix}')
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


def load_wave(file: Path) -> wave.Wave_read:
    proc = subprocess.run(
        ['ffmpeg', '-i', str(file), '-c:a', 'pcm_s16le', '-f', 'wav', '-'],
        capture_output=True,
    )
    proc.check_returncode()

    w = wave.Wave_read(io.BytesIO(proc.stdout))
    p = w.getparams()
    w._nframes = (len(proc.stdout) - 44) // (p.nchannels * p.sampwidth)  # type: ignore[reportAttributeAccessIssue]
    return w


def make_waveform_values(wav: wave.Wave_read, width: int) -> Sequence[float]:
    wav.setpos(0)
    n = wav.getnframes() // width

    res = []
    for _ in range(width):
        data = wav.readframes(n)
        res.append(max(abs(v) for v in struct.unpack(f'<{n}l', data)))
    m = max(res)
    return [v / m for v in res]
