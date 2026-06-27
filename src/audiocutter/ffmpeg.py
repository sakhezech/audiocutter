import subprocess
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
