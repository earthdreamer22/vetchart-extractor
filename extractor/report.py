# -*- coding: utf-8 -*-
"""결과 파일 — report.json(보낼 내용 전부) + 미리보기.html(사람이 읽는 판) → zip"""
import html
import json
import zipfile
from pathlib import Path


def write(result: dict, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (folder / "미리보기.html").write_text(preview_html(result), encoding="utf-8")
    z = folder.with_suffix(".zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
        f.write(folder / "report.json", "report.json")
        f.write(folder / "미리보기.html", "미리보기.html")
    return z


def preview_html(r: dict) -> str:
    e = html.escape
    meta = r.get("meta", {})
    parts = [
        "<!doctype html><meta charset='utf-8'><title>VetChart 구조 정보 미리보기</title>",
        "<style>body{font-family:'Malgun Gothic',sans-serif;margin:24px;color:#333}table{border-collapse:collapse;margin:6px 0 18px}"
        "td,th{border:1px solid #ddd;padding:3px 7px;font-size:13px;vertical-align:top}th{background:#f4f1ea}"
        ".box{background:#f6ffed;border:1px solid #b7eb8f;padding:12px 16px;border-radius:8px;margin-bottom:16px}"
        "code{background:#f5f5f5;padding:0 3px}</style>",
        "<h1>보낼 내용 미리보기</h1>",
        "<div class='box'><b>이 파일에는 실제 값이 없습니다.</b> 표·칸 이름과 형식, 건수, 그리고 값의 '모양'"
        "(날짜·전화번호처럼 보이는 비율, 글 길이, <code>###-####</code> 같은 형식 틀)만 들어 있습니다. "
        "보호자 이름·전화번호·주소·진료 내용은 들어 있지 않습니다. "
        "아래 '코드 값'만 실제 값인데, 성별·종·상태처럼 여러 번 반복되는 짧은 코드만 남깁니다.</div>",
        f"<p>DB 종류: <b>{e(str(r.get('engine')))}</b> · 정보: {e(json.dumps(r.get('info', {}), ensure_ascii=False))} · "
        f"표 {len(r.get('tables', []))}개 · 만든 시각 {e(str(meta.get('created_at', '')))} · 프로그램 {e(str(meta.get('tool_version', '')))}</p>",
    ]
    if r.get("errors"):
        parts.append("<p>읽지 못한 부분: " + e(", ".join(r["errors"][:30])) + "</p>")
    for t in r.get("tables", []):
        parts.append(f"<h3>{e(t['name'])} <small>({t.get('rows')}행)</small></h3><table>"
                     "<tr><th>칸</th><th>형식</th><th>비어 있음</th><th>모양</th><th>코드 값</th></tr>")
        for c in t.get("columns", []):
            txt = c.get("text") or {}
            look = ", ".join(f"{k} {v:.0%}" for k, v in (txt.get("looks_like") or {}).items())
            shp = " / ".join(txt.get("shapes") or [])
            extra = []
            if c.get("number"):
                extra.append(f"숫자 {c['number']['min']}~{c['number']['max']}")
            if c.get("date"):
                extra.append(f"날짜 {c['date']['year_min']}~{c['date']['year_max']}년")
            if txt.get("len_max"):
                extra.append(f"글 {txt['len_min']}~{txt['len_max']}자")
            if c.get("binary"):
                extra.append(f"파일 {c['binary']['starts']}")
            codes = ", ".join(f"{v}({n})" for v, n in (txt.get("code_values") or []))
            parts.append(f"<tr><td>{e(c['name'])}</td><td>{e(str(c.get('type')))}</td><td>{c.get('null_ratio', '')}</td>"
                         f"<td>{e('; '.join(x for x in [look, shp, ', '.join(extra)] if x))}</td><td>{e(codes)}</td></tr>")
        parts.append("</table>")
    return "\n".join(parts)
