"""安全教育資料アプリの資料を取得・更新チェックする。

catalog.json に登録した資料を元URLから取り直し、
- 新規/中身が変わったもの → docs/ のPDFと文字化け対策版を差し替え、取得日を更新
- 変わっていないもの → そのまま(確認日だけ更新)
- 取れなかったもの(リンク切れ等) → 前回のPDFを残したまま「要確認」にする
結果を data.json(アプリが読む)と update_report.md(更新レポート)に書き出す。

月1回の自動チェック(GitHub Actions)でも、手動でも同じこれを実行する:
    python build.py
"""
import hashlib
import io
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import pymupdf
import requests
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
UA = "Mozilla/5.0 (compatible; CivilWebSafetyDocs/1.0)"
TIMEOUT = 20
JST = timezone(timedelta(hours=9))


def fetch(url):
    """URLからPDFを取る。HTMLページだった場合は中の.pdfリンクを3件までたどる。"""
    last = None
    for _ in range(2):
        try:
            r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
            r.raise_for_status()
            if r.content[:5].startswith(b"%PDF"):
                return r.content, None
            html = r.content.decode("utf-8", "ignore")
            for h in re.findall(r'href=["\']([^"\']+?\.pdf[^"\']*)["\']', html, re.I)[:3]:
                cr = requests.get(urljoin(r.url, h), timeout=TIMEOUT, headers={"User-Agent": UA})
                if cr.ok and cr.content[:5].startswith(b"%PDF"):
                    return cr.content, None
            return None, "PDFではないページ(.pdfリンクも見つからず)"
        except Exception as e:
            last = str(e)
    return None, last


def slice_pages(content, page_range):
    """page_range=[開始, 終了](1始まり・両端含む)のページだけを抜き出す。指定なしならそのまま。"""
    if not page_range:
        return content
    from pypdf import PdfWriter
    rd = PdfReader(io.BytesIO(content))
    w = PdfWriter()
    for i in range(page_range[0] - 1, page_range[1]):
        w.add_page(rd.pages[i])
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def make_image_pdf(src_bytes, out_path):
    """文字化け対策版:各ページを画像にしてPDF化(どの端末でも同じ表示になる)。"""
    src = pymupdf.open(stream=src_bytes, filetype="pdf")
    out = pymupdf.open()
    for pg in src:
        pix = pg.get_pixmap(dpi=144)
        page = out.new_page(width=pg.rect.width, height=pg.rect.height)
        page.insert_image(page.rect, stream=pix.tobytes("jpeg", jpg_quality=78))
    out.save(out_path, deflate=True)


def main():
    catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    data_path = ROOT / "data.json"
    old = {}
    if data_path.exists():
        old = {d["id"]: d for d in json.loads(data_path.read_text(encoding="utf-8"))["docs"]}
    DOCS.mkdir(exist_ok=True)
    today = datetime.now(JST).strftime("%Y-%m-%d")

    docs, added, changed, broken = [], [], [], []
    cache = {}  # 同じURLから複数ページ範囲を切り出す資料があるため、1回だけ取得する
    for doc in catalog["docs"]:
        prev = old.get(doc["id"], {})
        rec = {**doc, "pages": prev.get("pages"), "sha256": prev.get("sha256"),
               "fetched_at": prev.get("fetched_at"), "checked_at": today,
               "status": "ok", "error": None}
        if doc["url"] not in cache:
            cache[doc["url"]] = fetch(doc["url"])
        content, err = cache[doc["url"]]
        if content is not None:
            content = slice_pages(content, doc.get("page_range"))
        if content is None:
            rec["status"] = "要確認"
            rec["error"] = err
            broken.append(rec)
            if not prev:  # 一度も取れていない資料はアプリに出さない
                print(f"NG(初回取得失敗) {doc['id']}: {err}")
                continue
            print(f"NG {doc['id']}: {err}(前回のPDFを継続使用)")
        else:
            sha = hashlib.sha256(content).hexdigest()
            if sha != prev.get("sha256") or not (DOCS / f"{doc['id']}.pdf").exists():
                (DOCS / f"{doc['id']}.pdf").write_bytes(content)
                make_image_pdf(content, DOCS / f"{doc['id']}_img.pdf")
                rec["pages"] = len(PdfReader(io.BytesIO(content)).pages)
                rec["sha256"] = sha
                rec["fetched_at"] = today
                (changed if prev else added).append(rec)
                print(f"{'更新' if prev else '新規'} {doc['id']} ({rec['pages']}ページ)")
            else:
                print(f"変更なし {doc['id']}")
        docs.append(rec)

    data = {"generated_at": today, "categories": catalog["categories"], "docs": docs}
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# 更新レポート({today})", "",
             f"- 新規取得:{len(added)}件", f"- 中身が変わり差し替え:{len(changed)}件",
             f"- 要確認(取得失敗・リンク切れ):{len(broken)}件", ""]
    for title, items in (("差し替えた資料", changed), ("要確認の資料", broken)):
        if items:
            lines.append(f"## {title}")
            lines += [f"- {d['title']}({d['org']})\n  - {d['url']}"
                      + (f"\n  - 理由:{d['error']}" if d.get("error") else "") for d in items]
            lines.append("")
    (ROOT / "update_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"完了:新規{len(added)} 差し替え{len(changed)} 要確認{len(broken)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
