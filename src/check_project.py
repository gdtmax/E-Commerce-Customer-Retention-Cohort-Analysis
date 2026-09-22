"""Run small synthetic regression checks without requiring the raw dataset."""
from pathlib import Path
import os
import subprocess
import sys


def main():
    if not __debug__ or os.environ.get('PYTHONOPTIMIZE', '0') not in ('', '0'):
        raise RuntimeError('Run without optimization so assertions remain active.')
    checks = Path(__file__).resolve().parent / 'checks'
    files = sorted(checks.glob('test_*.py'))
    if len(files) != 6:
        raise RuntimeError('Expected all six regression-check files.')
    for path in files:
        subprocess.run([sys.executable, str(path)], check=True)
    print(f'All {len(files)} regression suites passed.')


if __name__ == '__main__':
    main()
