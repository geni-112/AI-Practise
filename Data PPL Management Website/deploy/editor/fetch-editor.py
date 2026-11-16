"""Install the immutable open-source draw.io static release into the web image."""
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import urllib.request
import zipfile

TAG = "v32.6.10"
SHA256 = "a57b06b3b6a876a351dacfe65d027d9509319cd030e9bacf6ae04a034d66a38f"
URL = "https://github.com/jgraph/drawio/releases/download/" + TAG + "/draw.war"
root = Path("/srv/drawio")
root.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryFile() as asset:
    req = urllib.request.Request(URL, headers={"User-Agent": "Data-PPL-Management"})
    with urllib.request.urlopen(req, timeout=120) as response:
        shutil.copyfileobj(response, asset)
    asset.seek(0)
    if hashlib.file_digest(asset, "sha256").hexdigest() != SHA256:
        raise ValueError("draw.io release checksum mismatch")
    asset.seek(0)
    with zipfile.ZipFile(asset) as release:
        for member in release.infolist():
            path = PurePosixPath(member.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Invalid release path")
            if not path.parts or path.parts[0] in ("WEB-INF", "META-INF") or member.is_dir():
                continue
            if path.suffix in (".jsp", ".class", ".jar"):
                continue
            output = root.joinpath(*path.parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            with release.open(member) as source, output.open("wb") as target:
                shutil.copyfileobj(source, target)
if not (root / "index.html").is_file() or not (root / "js/app.min.js").is_file():
    raise ValueError("Incomplete draw.io web release")
with urllib.request.urlopen("https://raw.githubusercontent.com/jgraph/drawio/" + TAG + "/LICENSE", timeout=45) as response:
    license_text = response.read()
if hashlib.sha256(license_text).hexdigest() != "43070e2d4e532684de521b885f385d0841030efa2b1a20bafb76133a5e1379c1":
    raise ValueError("draw.io license checksum mismatch")
(root / "LICENSE.txt").write_bytes(license_text)
