# -*- coding: utf-8 -*-
"""이 PC에서 쓰는 DB 찾기 — 서비스 이름, 열린 포트, DB 파일 위치 (읽기만)"""
import os
import socket
import string
import subprocess
from pathlib import Path

SERVICE_HINTS = {
    "firebird": ("firebird", "interbase"),
    "mssql": ("mssql", "sql server"),
    "mysql": ("mysql", "mariadb"),
    "postgresql": ("postgresql",),
}
PORTS = {"firebird": 3050, "mssql": 1433, "mysql": 3306, "postgresql": 5432}
DB_EXT = {".fdb": "firebird", ".gdb": "firebird", ".mdf": "mssql", ".ibd": "mysql", ".myd": "mysql", ".frm": "mysql"}
SKIP_DIRS = {"windows", "$recycle.bin", "system volume information", "programdata\\microsoft", "appdata", "node_modules",
             "winsxs", "temp", "msocache", "recovery"}


def services() -> list[dict]:
    """실행 중·설치된 DB 서비스 (Windows)"""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-CimInstance Win32_Service | Select-Object Name,DisplayName,State,PathName | ConvertTo-Json"],
                           capture_output=True, timeout=60, encoding="utf-8", errors="replace")
        import json
        items = json.loads(r.stdout or "[]")
        if isinstance(items, dict):
            items = [items]
    except Exception:
        return []
    out = []
    for s in items:
        text = f"{s.get('Name', '')} {s.get('DisplayName', '')}".lower()
        for kind, hints in SERVICE_HINTS.items():
            if any(h in text for h in hints):
                out.append({"kind": kind, "name": s.get("Name"), "display": s.get("DisplayName"), "state": s.get("State"),
                            "instance": _mssql_instance(s.get("Name", "")) if kind == "mssql" else None})
                break
    return out


def _mssql_instance(name: str):
    if name.upper() == "MSSQLSERVER":
        return "."
    if name.upper().startswith("MSSQL$"):
        return ".\\" + name.split("$", 1)[1]
    return None


def open_ports(host="127.0.0.1") -> dict:
    out = {}
    for kind, port in PORTS.items():
        s = socket.socket()
        s.settimeout(0.5)
        try:
            out[kind] = s.connect_ex((host, port)) == 0
        finally:
            s.close()
    return out


def db_files(max_depth: int = 5, limit: int = 60) -> list[dict]:
    """고정 드라이브에서 DB 파일 찾기 (크기 큰 순). 내용은 열지 않는다"""
    found = []
    drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    for root in drives:
        base_depth = root.count("\\")
        for dirpath, dirnames, filenames in os.walk(root):
            low = dirpath.lower()
            if any(k in low for k in SKIP_DIRS) or dirpath.count("\\") - base_depth >= max_depth:
                dirnames[:] = []
                continue
            for f in filenames:
                ext = os.path.splitext(f)[1].lower()
                if ext in DB_EXT:
                    p = Path(dirpath) / f
                    try:
                        size = p.stat().st_size
                    except OSError:
                        continue
                    if ext in (".ibd", ".frm", ".myd") and size < 1_000_000:
                        continue          # MySQL은 표마다 파일이 있어 작은 것은 뺀다
                    if f.lower() in ("security2.fdb", "security3.fdb", "security.fdb", "help.fdb", "employee.fdb", "employee.gdb"):
                        continue          # Firebird 자체 파일 (차트 DB 아님)
                    found.append({"kind": DB_EXT[ext], "path": str(p), "size_mb": round(size / 1048576, 1)})
    found.sort(key=lambda x: -x["size_mb"])
    return found[:limit]
