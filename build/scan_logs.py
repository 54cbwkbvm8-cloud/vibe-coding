"""Scan logs for forbidden secret/content patterns without printing log data."""

from __future__ import annotations

import argparse
from pathlib import Path
import re


PATTERNS = {
    "api_key_like": re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "bearer_token": re.compile(
        rb"authorization\s*:\s*bearer\s+[A-Za-z0-9._-]{10,}",
        re.IGNORECASE,
    ),
    "private_key": re.compile(
        rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"
    ),
    "base64_image": re.compile(
        rb"data:image/[A-Za-z0-9.+-]+;base64,",
        re.IGNORECASE,
    ),
    "full_url": re.compile(
        rb"https?://[^\s\"'<>]+",
        re.IGNORECASE,
    ),
    "question_or_answer_body": re.compile(
        rb"(?i)\b(question|answer|prompt|transcript)\s*[:=]\s*\S+"
    ),
    "local_user_path": re.compile(
        rb"(?i)(?:[A-Z]:\\(?:[^\\\s]+\\){1,}|/(?:Users|home)/[^/\s]+/)"
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log_directory", type=Path)
    args = parser.parse_args()
    directory = args.log_directory
    if not directory.exists():
        print("LOG_DIRECTORY=MISSING")
        return 2

    counts = {name: 0 for name in PATTERNS}
    files_scanned = 0
    for path in sorted(directory.glob("*.log*")):
        if not path.is_file():
            continue
        files_scanned += 1
        data = path.read_bytes()
        for name, pattern in PATTERNS.items():
            counts[name] += len(pattern.findall(data))

    print(f"LOG_FILES_SCANNED={files_scanned}")
    for name, count in counts.items():
        print(f"{name.upper()}_MATCHES={count}")
    return 0 if not any(counts.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
