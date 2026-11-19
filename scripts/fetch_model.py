"""Fetch the quantized MiniLM model once, verifying its pinned files before use."""

import argparse
import hashlib
import shutil
import tempfile
import time
from http.client import HTTPException
from pathlib import Path
from urllib.request import urlopen


BASE = (
    "https://huggingface.co/Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
    "/resolve/faf4aa4225822f3bc6376869cb1164e8e3feedd0"
)
SHA256 = {
    "config.json": "c8ec081fdad2df991bf5abbf18418fec7a5cdaa421f60ffb060a30040b8c376f",
    "special_tokens_map.json": "8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835",
    "tokenizer_config.json": "0666eebf692422757e1dddf3c9fb1ded73ba3dc726c5828671fc89e45bf3609f",
    "tokenizer.json": "fa685fc160bbdbab64058d4fc91b60e62d207e8dc60b9af5c002c5ab946ded00",
    "model_optimized.onnx": "634d0f66c29dc934c8fa72b8a4fe91dd4d420a22f1d82a241058d4316e659a99",
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name, expected in SHA256.items():
        target = directory / name
        if target.is_file() and digest(target) == expected:
            continue
        for attempt in range(3):
            with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
                temporary = Path(stream.name)
            try:
                with urlopen(f"{BASE}/{name}?download=true", timeout=120) as source:
                    with temporary.open("wb") as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                if digest(temporary) != expected:
                    raise OSError(f"Invalid SHA-256 for {name}")
                # Docker builds as root; the app reads these public weights as its own user.
                temporary.chmod(0o644)
                temporary.replace(target)
                print(f"Verified {name}", flush=True)
                break
            except (OSError, HTTPException):
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
            finally:
                temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    fetch(parser.parse_args().directory)
