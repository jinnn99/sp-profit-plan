"""HTTPS 배포용 정적 PWA 폴더를 만든다.

생성 결과:
    mobile_app/
      index.html
      manifest.webmanifest
      sw.js
      app_icon.svg
      app_icon-192.png
      app_icon-512.png
      _headers
    S&P_수익&플랜_mobile_app.zip
"""
from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "S&P_수익&플랜.html"
OUT_DIR = ROOT / "mobile_app"
ZIP_PATH = ROOT / "S&P_수익&플랜_mobile_app.zip"
ICON_FILES = ("app_icon.svg", "app_icon-192.png", "app_icon-512.png")


def main() -> None:
    if not REPORT.exists():
        raise FileNotFoundError(f"리포트 파일이 없습니다: {REPORT}")

    OUT_DIR.mkdir(exist_ok=True)
    html = REPORT.read_text(encoding="utf-8")
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")

    manifest = json.loads((ROOT / "manifest.webmanifest").read_text(encoding="utf-8"))
    manifest["start_url"] = "./index.html"
    manifest["scope"] = "./"
    (OUT_DIR / "manifest.webmanifest").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for icon_file in ICON_FILES:
        icon_path = ROOT / icon_file
        if icon_path.exists():
            shutil.copy2(icon_path, OUT_DIR / icon_file)

    # 서비스워커는 루트 sw.js를 단일 소스로 삼고, 배포본(index.html)에 맞게
    # REPORT_URL/ASSETS만 치환한다. 캐시 전략(install/activate/fetch, /api/ 우회)은
    # 루트 sw.js 한 곳에서만 관리한다.
    sw_src = (ROOT / "sw.js").read_text(encoding="utf-8")
    sw_src = sw_src.replace(
        'const REPORT_URL = "./S%26P_%EC%88%98%EC%9D%B5%26%ED%94%8C%EB%9E%9C.html";',
        'const REPORT_URL = "./index.html";',
    )
    sw_src = sw_src.replace(
        'const ASSETS = [\n'
        '  "./",\n'
        '  REPORT_URL,\n'
        '  "./manifest.webmanifest",\n'
        '  "./app_icon.svg"\n'
        '];',
        'const ASSETS = ["./", REPORT_URL, "./manifest.webmanifest", '
        '"./app_icon.svg", "./app_icon-192.png", "./app_icon-512.png"];',
    )
    if 'REPORT_URL = "./index.html"' not in sw_src:
        raise RuntimeError("sw.js REPORT_URL 치환 실패 — 루트 sw.js 형식을 확인하세요.")
    (OUT_DIR / "sw.js").write_text(sw_src, encoding="utf-8")

    (OUT_DIR / "_headers").write_text(
        "/sw.js\n"
        "  Cache-Control: no-cache\n"
        "/index.html\n"
        "  Cache-Control: no-cache\n"
        "/manifest.webmanifest\n"
        "  Content-Type: application/manifest+json\n"
        "/api/*\n"
        "  Cache-Control: no-store\n",
        encoding="utf-8",
    )
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(OUT_DIR.rglob("*")):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(OUT_DIR))

    print(f"배포 폴더 생성 완료: {OUT_DIR}")
    print(f"배포 ZIP 생성 완료: {ZIP_PATH}")
    print("Netlify Drop, Cloudflare Pages, GitHub Pages 등에 이 폴더 내용을 올리면 됩니다.")


if __name__ == "__main__":
    main()
