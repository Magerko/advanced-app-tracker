#!/usr/bin/env python3
"""Sign the Firefox extension and put it into signed-extension/.

Run this once after every change to the extension. You need:

1. Node.js and web-ext:      npm install --global web-ext
2. API keys from https://addons.mozilla.org/developers/addon/api/key/
   ("JWT issuer" and "JWT secret").

Usage (Windows PowerShell):

    $env:WEB_EXT_API_KEY = "user:12345:678"
    $env:WEB_EXT_API_SECRET = "your-secret"
    python tools/sign_extension.py

The keys are read from the environment, so they never end up in git.
Every signing needs a NEW "version" in extension/manifest.json.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTENSION_DIR = ROOT / "extension"
OUTPUT = ROOT / "signed-extension" / "advanced-app-tracker.xpi"


def main() -> int:
    web_ext = shutil.which("web-ext")
    if web_ext is None:
        print("web-ext не найден. Установите: npm install --global web-ext")
        return 1

    missing = [v for v in ("WEB_EXT_API_KEY", "WEB_EXT_API_SECRET") if not os.environ.get(v)]
    if missing:
        print("Не заданы переменные:", ", ".join(missing))
        print("Ключи: https://addons.mozilla.org/developers/addon/api/key/")
        return 1

    version = json.loads((EXTENSION_DIR / "manifest.json").read_text("utf-8"))["version"]
    print(f"Подписываю версию {version}...")

    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [web_ext, "sign", "--channel=unlisted",
             "--source-dir", str(EXTENSION_DIR), "--artifacts-dir", tmp],
        )
        if result.returncode != 0:
            print("Подпись не удалась. Если версия уже подписывалась, "
                  "увеличьте \"version\" в extension/manifest.json.")
            return result.returncode

        signed = sorted(Path(tmp).glob("*.xpi"))
        if not signed:
            print("web-ext не вернул .xpi файл.")
            return 1
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(signed[-1], OUTPUT)

    print(f"Готово: {OUTPUT}")
    print("Добавьте этот файл в git, чтобы другие могли установить расширение.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
