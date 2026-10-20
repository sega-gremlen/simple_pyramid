"""Собирает ``installer/favicon.ico`` из ``installer/logo.svg``: ``uv run python -m dev.make_icon``.

Без лишних зависимостей: SVG рисует headless Microsoft Edge (он есть на любой Windows) —
страница рисует картинку на canvas нужных размеров и кладёт PNG в DOM, ``--dump-dom`` их отдаёт.
PNG упаковываются в ICO (формат с PNG-кадрами понимают Windows, PyInstaller и Inno Setup).

Готовый ``favicon.ico`` коммитится в репозиторий — CI использует его как есть.
"""

import argparse
import base64
import logging
import re
import struct
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "installer" / "logo.svg"
ICO = ROOT / "installer" / "favicon.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)
EDGE_PATHS = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)

PAGE = """<!DOCTYPE html><html><body><pre id="out"></pre><script>
const img = new Image();
img.onload = () => {
  const out = [];
  for (const s of %(sizes)s){
    const c = document.createElement("canvas"); c.width = c.height = s;
    const ctx = c.getContext("2d"); ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img, 0, 0, s, s);
    out.push(s + ":" + c.toDataURL("image/png").split(",")[1]);
  }
  document.getElementById("out").textContent = out.join("\\n");
};
img.src = "data:image/svg+xml;base64,%(svg)s";
</script></body></html>"""


def find_edge() -> Path:
    """Путь к msedge.exe."""
    for path in EDGE_PATHS:
        if path.exists():
            return path
    raise FileNotFoundError("Не найден Microsoft Edge (msedge.exe)")


def render_pngs(svg: bytes, sizes: tuple[int, ...]) -> dict[int, bytes]:
    """Рисует SVG в PNG каждого размера через headless Edge."""
    page = PAGE % {"sizes": list(sizes), "svg": base64.b64encode(svg).decode()}
    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / "render.html"
        html.write_text(page, encoding="utf-8")
        result = subprocess.run(  # noqa: S603 — запускаем системный Edge с нашим файлом
            [
                str(find_edge()),
                "--headless=new",
                "--disable-gpu",
                f"--user-data-dir={tmp}",
                "--virtual-time-budget=3000",
                "--dump-dom",
                html.as_uri(),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
    found = re.findall(r"(?<![\w+/=])(\d+):([A-Za-z0-9+/=]{20,})", result.stdout)
    pngs = {int(s): base64.b64decode(b) for s, b in found}
    missing = set(sizes) - set(pngs)
    if missing:
        raise RuntimeError(f"Edge не отрисовал размеры: {sorted(missing)}")
    return pngs


def pack_ico(pngs: dict[int, bytes]) -> bytes:
    """Упаковывает PNG-кадры в ICO."""
    sizes = sorted(pngs)
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries, blobs = b"", b""
    for s in sizes:
        data = pngs[s]
        dim = 0 if s >= 256 else s  # 0 в ICO означает 256
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    return header + entries + blobs


def main() -> None:
    """Точка входа."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--svg", type=Path, default=SVG)
    parser.add_argument("--out", type=Path, default=ICO)
    parser.add_argument(
        "--png-dir", type=Path, help="заодно сохранить PNG каждого размера (для просмотра)"
    )
    args = parser.parse_args()

    pngs = render_pngs(args.svg.read_bytes(), SIZES)
    args.out.write_bytes(pack_ico(pngs))
    log.info("%s: %s", args.out, ", ".join(f"{s}px" for s in sorted(pngs)))
    if args.png_dir:
        args.png_dir.mkdir(parents=True, exist_ok=True)
        for s, data in pngs.items():
            (args.png_dir / f"icon_{s}.png").write_bytes(data)


if __name__ == "__main__":
    main()
