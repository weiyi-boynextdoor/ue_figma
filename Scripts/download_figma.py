#!/usr/bin/env python3
"""Download Figma REST JSON, like UFigmaImporter.Run(), using only stdlib.

PowerShell:
    $env:FIGMA_ACCESS_TOKEN = "your-token"
    python Scripts/download_figma.py FILE_KEY
    python Scripts/download_figma.py "https://www.figma.com/design/FILE_KEY/Name" --ids "1:2,3:4"
    python Scripts/download_figma.py FILE_KEY --library-file-key LIB_KEY -o Downloads/design.json

The .figma output contains REST JSON, not a native .fig archive. Referenced
images and rendered vector nodes are saved alongside it in Images/ by default.
Google Fonts and Unreal asset generation are not included.
"""

import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


def file_key(value):
    """Accept a file key or a Figma file/design URL (ignore URL node selection)."""
    if "://" in value:
        url = urlparse(value)
        parts = url.path.strip("/").split("/")
        if (url.hostname not in {"figma.com", "www.figma.com"}
                or len(parts) < 2 or parts[0] not in {"file", "design", "board", "slides"}):
            raise argparse.ArgumentTypeError("Expected a Figma file URL or file key.")
        value = parts[1]
    if not re.fullmatch(r"[A-Za-z0-9]+", value):
        raise argparse.ArgumentTypeError("File keys must contain only letters and digits.")
    return value


def safe_name(value):
    """Keep remote file names within one portable path component."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")[:120]
    if not name:
        name = "FigmaFile"
    if name.split(".")[0].upper() in {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        name = "_" + name
    return name


def api_json(path, token, timeout, params=None):
    url = "https://api.figma.com/v1/" + path
    if params:
        url += "?" + urlencode(params)
    # No request body: urllib sets Host and does not add Content-Length for GET.
    request = Request(url, headers={"X-Figma-Token": token, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        hints = {
            401: "Check the access token.",
            403: "Check token permissions and access to this file.",
            404: "Check the file key and access to this file.",
            429: "Rate limit reached; retry later.",
        }
        hint = hints.get(exc.code, "Figma API request failed.")
        if exc.code == 429 and exc.headers.get("Retry-After"):
            hint += f" Retry-After: {exc.headers['Retry-After']}."
        raise RuntimeError(f"HTTP {exc.code}: {hint}") from exc
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError("Figma returned invalid JSON; no output was saved.") from exc
    if not isinstance(data, dict) or data.get("err") or data.get("error"):
        raise RuntimeError("Figma returned an API error or invalid response.")
    return data, raw


def save_bytes(target, raw):
    target.parent.mkdir(parents=True, exist_ok=True)
    # Replace only after a complete, validated response has been written.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(f"Saved {target.resolve()} ({len(raw):,} bytes)")


def download_file(key, token, ids, output, download_dir, timeout):
    print(f"Downloading {key} ...")
    data, raw = api_json(f"files/{key}", token, timeout, {"ids": ids} if ids else None)
    if "document" not in data:
        raise RuntimeError("Response is not a Figma file document; no output was saved.")
    name = safe_name(str(data.get("name") or data.get("Name") or key))
    target = output if output is not None else download_dir / name / f"{name}.figma"
    save_bytes(target, raw)
    return target


def walk_nodes(node):
    yield node
    for child in node.get("children", []):
        yield from walk_nodes(child)


def image_requests(document, components):
    """Mirror texture selection in Vector/Rectangle/Ellipse/Paint builders.

    Instances use their component assets; missing components get a placeholder.
    Boolean children are already included in their parent's rasterization.
    """
    requests = {}

    def visit(node):
        kind = node.get("type")
        fills = node.get("fills", [])
        has_image = any(p.get("type") == "IMAGE" for p in fills)
        bounds = node.get("absoluteBoundingBox", {})
        circle = bounds.get("width", 0) == bounds.get("height", 0)
        vector = kind in {"VECTOR", "STAR", "LINE", "REGULAR_POLYGON", "BOOLEAN_OPERATION", "WASHI_TAPE"}
        ellipse = kind == "ELLIPSE" and (
            not circle or any(p.get("type") != "SOLID" for p in fills + node.get("strokes", [])))
        missing = kind == "INSTANCE" and node.get("componentId") not in components
        needs_texture = vector or ellipse or has_image or missing
        if kind == "INSTANCE":
            needs_texture = missing
        if needs_texture and node.get("id"):
            supports_ref = not vector and (kind != "ELLIPSE" or circle)
            ref = next((p.get("imageRef") for p in fills
                        if p.get("type") == "IMAGE" and p.get("imageRef")), None) if supports_ref else None
            requests[node["id"]] = {"node": node, "ref": ref}
        if kind not in {"INSTANCE", "BOOLEAN_OPERATION"}:
            for child in node.get("children", []):
                visit(child)

    visit(document)
    return requests


def image_extension(raw):
    for signature, extension in ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"),
                                 (b"GIF8", "gif"), (b"BM", "bmp"),
                                 (b"II*\x00", "tiff"), (b"MM\x00*", "tiff"),
                                 (b"\x00\x00\x01\x00", "ico"), (b"v/1\x01", "exr")):
        if raw.startswith(signature):
            return extension
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "webp"
    raise RuntimeError("Image response has an unsupported format; no image was saved.")


def download_images(key, data, target, token, timeout, scale, batch_size, components):
    requests = image_requests(data["document"], components)
    if not requests:
        return
    print(f"Resolving {len(requests)} images for {key} ...")
    refs, _ = api_json(f"files/{key}/images", token, timeout)
    ref_urls = refs.get("meta", {}).get("images", {})
    pending = []
    for node_id, item in requests.items():
        item["url"] = ref_urls.get(item["ref"])
        if not item["url"]:
            pending.append(node_id)
    for start in range(0, len(pending), batch_size):
        batch = pending[start:start + batch_size]
        rendered, _ = api_json(f"images/{key}", token, timeout,
                               {"ids": ",".join(batch), "scale": scale, "format": "png"})
        for node_id in batch:
            requests[node_id]["url"] = rendered.get("images", {}).get(node_id)
    failures = []
    for node_id, item in requests.items():
        try:
            url = item["url"]
            if not url:
                raise RuntimeError("Figma returned no image URL")
            if urlparse(url).scheme != "https":
                raise RuntimeError("Expected an HTTPS image URL")
            # CDN requests deliberately carry no Figma access token.
            with urlopen(Request(url), timeout=timeout) as response:
                raw = response.read()
            extension = image_extension(raw)
            name = safe_name(str(item["node"].get("name") or "Node"))
            suffix = safe_name(node_id.replace(":", "-"))
            save_bytes(target.parent / "Images" / f"{name}--{suffix}.{extension}", raw)
        except (RuntimeError, URLError, OSError, ValueError) as exc:
            failures.append(node_id)
            # Avoid logging signed CDN URLs or credentials from exceptions.
            print(f"Image {node_id} failed ({type(exc).__name__}).", file=sys.stderr)
    if failures:
        raise RuntimeError(f"{len(failures)} images failed: {', '.join(failures)}. Completed files were retained.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=file_key, help="Figma file key or file URL")
    parser.add_argument("--token", default=os.environ.get("FIGMA_ACCESS_TOKEN"),
                        help="Personal access token (default: FIGMA_ACCESS_TOKEN)")
    parser.add_argument("--ids", default="", help="Comma-separated node IDs, e.g. 1:2,3:4")
    parser.add_argument("--library-file-key", type=file_key, action="append", default=[],
                        help="Download a dependency first; repeat for multiple libraries")
    parser.add_argument("-o", "--output", type=Path, help="Main file output path (existing file is replaced)")
    parser.add_argument("--download-dir", type=Path,
                        default=Path.cwd() / "downloads",
                        help="Default: ./downloads/<name>/<name>.figma under the current working directory (existing files replaced)")
    parser.add_argument("--timeout", type=float, default=120, help="Network timeout in seconds (default: 120)")
    parser.add_argument("--skip-images", action="store_true", help="Download only the file JSON")
    parser.add_argument("--scale", type=float, default=4.0, help="Node image scale (default: 4, as in the plugin)")
    parser.add_argument("--image-batch-size", type=int, default=20, help="Node IDs per render request (default: 20)")
    args = parser.parse_args(argv)
    if not args.token or not args.token.strip():
        parser.error("Provide --token or set FIGMA_ACCESS_TOKEN.")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a positive finite number.")
    if not math.isfinite(args.scale) or not 0.01 <= args.scale <= 4:
        parser.error("--scale must be between 0.01 and 4.")
    if args.image_batch_size <= 0:
        parser.error("--image-batch-size must be positive.")
    ids = ",".join(part.strip() for part in args.ids.split(",") if part.strip())
    try:
        files = []
        for key in dict.fromkeys(args.library_file_key):
            target = download_file(key, args.token.strip(), "", None, args.download_dir, args.timeout)
            files.append((key, json.loads(target.read_bytes()), target))
        target = download_file(args.file, args.token.strip(), ids, args.output, args.download_dir, args.timeout)
        files.append((args.file, json.loads(target.read_bytes()), target))
        if not args.skip_images:
            # Resolve remote components by stable component key across downloaded libraries.
            component_keys = {data.get("components", {}).get(n["id"], {}).get("key")
                              for _, data, _ in files for n in walk_nodes(data["document"])
                              if n.get("type") == "COMPONENT"}
            component_keys.discard(None)
            for key, data, target in files:
                components = {n["id"] for n in walk_nodes(data["document"]) if n.get("type") == "COMPONENT"}
                components.update(cid for cid, info in data.get("components", {}).items()
                                  if info.get("key") in component_keys)
                download_images(key, data, target, args.token.strip(), args.timeout,
                                args.scale, args.image_batch_size, components)
    except (RuntimeError, URLError, OSError, ValueError) as exc:
        print(f"Error: {str(exc).replace(args.token.strip(), '[REDACTED]')}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
