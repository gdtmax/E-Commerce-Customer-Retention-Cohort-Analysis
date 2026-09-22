"""Download and verify the pinned original UCI workbook using the standard library.

Run from the repository root with Python 3.10+: python src/download_dataset.py
Existing matching data is kept. An existing nonmatching workbook is never overwritten.
"""

import hashlib
from pathlib import Path
import shutil
import tempfile
from urllib.request import Request, urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
URL = "https://archive.ics.uci.edu/static/public/502/online%2Bretail%2Bii.zip"
FILENAME = "online_retail_II.xlsx"
EXPECTED_SHA256 = "bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    raw = ROOT / "data/raw"
    raw.mkdir(parents=True, exist_ok=True)
    destination = raw / FILENAME
    if destination.exists():
        if sha256(destination) != EXPECTED_SHA256:
            raise SystemExit("Existing workbook has a different checksum. Inspect it before replacing it.")
        print("Original workbook already exists and its SHA-256 matches.")
        return
    with tempfile.TemporaryDirectory(prefix="uci-download-", dir=raw) as temporary:
        archive_path = Path(temporary) / "source.zip"
        request = Request(URL, headers={"User-Agent": "ecommerce-retention-portfolio/step-2"})
        with urlopen(request, timeout=120) as response, archive_path.open("wb") as output:
            shutil.copyfileobj(response, output)
        extracted = Path(temporary) / FILENAME
        with ZipFile(archive_path) as archive:
            # Read one named member; do not extract arbitrary archive paths.
            with archive.open(FILENAME) as source, extracted.open("wb") as output:
                shutil.copyfileobj(source, output)
        if sha256(extracted) != EXPECTED_SHA256:
            raise SystemExit("Source checksum changed. Review the new source version before use.")
        # Exclusive creation also protects against a concurrent local replacement.
        with extracted.open("rb") as source, destination.open("xb") as output:
            shutil.copyfileobj(source, output)
    print(f"Downloaded and verified {destination}")


if __name__ == "__main__":
    main()
