"""Package a PyInstaller onedir bundle with ZIP-compatible Unicode paths."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import zipfile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bundle",
        default="dist/奶蛙的荣光",
        help="PyInstaller onedir bundle directory",
    )
    parser.add_argument(
        "--zip",
        dest="zip_path",
        default="outputs/奶蛙的荣光_v1.0.0_onedir.zip",
        help="Output ZIP path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    bundle = (project_root / args.bundle).resolve()
    zip_path = (project_root / args.zip_path).resolve()
    if not bundle.is_dir():
        raise FileNotFoundError(f"Bundle directory not found: {bundle}")

    notice = project_root / "THIRD_PARTY_NOTICES.md"
    if notice.is_file():
        shutil.copy2(notice, bundle / notice.name)
        internal_notice = bundle / "_internal" / notice.name
        if internal_notice.parent.is_dir():
            shutil.copy2(notice, internal_notice)
    disclaimer = project_root / "DISCLAIMER.md"
    if disclaimer.is_file():
        shutil.copy2(disclaimer, bundle / disclaimer.name)
        internal_disclaimer = bundle / "_internal" / disclaimer.name
        if internal_disclaimer.parent.is_dir():
            shutil.copy2(disclaimer, internal_disclaimer)

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()

    file_count = 0
    total_bytes = 0
    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in sorted(bundle.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(bundle)
            archive_name = (Path(bundle.name) / relative).as_posix()
            archive.write(path, archive_name)
            file_count += 1
            total_bytes += path.stat().st_size

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    hash_path = zip_path.with_name(zip_path.name + ".sha256")
    with hash_path.open("w", encoding="utf-8", newline="\n") as hash_file:
        hash_file.write(f"{digest}  {zip_path.name}\n")

    print(f"ZipPath={zip_path}")
    print(f"ZipFileCount={file_count}")
    print(f"ZipSourceBytes={total_bytes}")
    print(f"ZipBytes={zip_path.stat().st_size}")
    print(f"ZipSha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
