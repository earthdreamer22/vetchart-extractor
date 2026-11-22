# -*- coding: utf-8 -*-
"""연결된 DB에서 구조와 값의 모양을 모은다 — 결과에는 실제 값이 없다

표 하나에서 오류가 나도(문자 깨짐·권한 등) 연결을 되살리고 다음 표로 넘어간다. 오류는 종류만 기록한다.
"""
import time

from .profile import SAMPLE_ROWS, is_master_table, profile_column


def _err(out, engine, where, e):
    out["errors"].append(f"{where}: {type(e).__name__}")
    try:
        engine.recover()
    except Exception as e2:
        out["errors"].append(f"다시 연결 실패: {type(e2).__name__}")


def collect(engine, progress=print, sample_rows: int = SAMPLE_ROWS) -> dict:
    started = time.time()
    tables = engine.tables()
    out = {"engine": engine.kind, "info": {}, "tables": [], "keys": {}, "errors": []}
    try:
        out["info"] = engine.info()
    except Exception as e:
        _err(out, engine, "정보 읽기", e)
    try:
        out["keys"] = engine.keys()
    except Exception as e:
        _err(out, engine, "키 읽기", e)
    for i, t in enumerate(tables, 1):
        progress(f"  [{i}/{len(tables)}] {t}")
        master = is_master_table(t, out["keys"])
        item = {"name": t, "rows": None, "columns": [], "code_table": master}
        try:
            cols = engine.columns(t)
        except Exception as e:
            _err(out, engine, f"{t} 칸 목록", e)
            out["tables"].append(item)
            continue
        try:
            item["rows"] = engine.row_count(t)
        except Exception as e:
            _err(out, engine, f"{t} 행 수", e)
        values_by_col = {c["name"]: [] for c in cols}
        if item["rows"] != 0:
            try:
                names, rows = engine.sample(t, sample_rows)
                for idx, n in enumerate(names):
                    key = n.strip() if isinstance(n, str) else n
                    if key in values_by_col:
                        values_by_col[key] = [r[idx] for r in rows]
            except Exception as e:
                _err(out, engine, f"{t} 표본", e)
        for c in cols:
            p = profile_column(c["name"], c["type"], values_by_col.get(c["name"], []), allow_codes=not master)
            p.update({"nullable": c.get("nullable"), "length": c.get("length")})
            item["columns"].append(p)
        out["tables"].append(item)
    out["seconds"] = round(time.time() - started, 1)
    return out
