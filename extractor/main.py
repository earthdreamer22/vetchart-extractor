# -*- coding: utf-8 -*-
"""VetChart 구조 정보 추출 프로그램 — 베타테스터용

차트 서버 PC에서 실행 → DB를 읽기만 해서 구조와 '값의 모양'만 모은 파일을 바탕화면에 만든다
→ 미리보기로 확인 → 제출 양식(구글폼)과 파일 위치를 열어 병원이 직접 올린다 (프로그램이 혼자 보내지 않음)
엑셀·CSV로 자료를 내보낼 수 있는 차트는 이 프로그램이 필요 없다 — VetChart 앱에서 그 파일로 바로 옮긴다.
DB 비밀번호는 이 PC에서 접속에만 쓰고 저장하거나 보내지 않는다.
"""
import getpass
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from . import BETA_PAGE_URL, SUBMIT_FORM_URL, TOOL_VERSION, engines
from .collect import collect
from .detect import db_files, open_ports, services
from .report import write


def say(t=""):
    print(t, flush=True)


def ask(prompt, default=""):
    v = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    return v or default


def choose(items, label):
    for i, it in enumerate(items, 1):
        say(f"  {i}) {label(it)}")
    while True:
        v = ask("번호를 고르세요")
        if v.isdigit() and 1 <= int(v) <= len(items):
            return items[int(v) - 1]
        say("  목록에 있는 번호를 입력하세요")


def connect_interactive() -> engines.Engine:
    say("\n이 PC에서 쓰는 DB를 찾는 중입니다… (파일 찾기에 1~2분 걸릴 수 있습니다)")
    svcs = services()
    ports = open_ports()
    files = db_files()
    cands = []
    for f in files:
        if f["kind"] == "firebird":
            cands.append(("firebird_file", f, f"Firebird 파일 {f['path']} ({f['size_mb']} MB)"))
    for s in svcs:
        if s["kind"] == "mssql" and s.get("instance"):
            cands.append(("mssql", s, f"MS SQL Server '{s['display']}' ({s['state']})"))
    if ports.get("mysql") or any(s["kind"] == "mysql" for s in svcs):
        cands.append(("mysql", {}, "MySQL / MariaDB (이 PC)"))
    if ports.get("postgresql") or any(s["kind"] == "postgresql" for s in svcs):
        cands.append(("postgresql", {}, "PostgreSQL (이 PC)"))
    for f in files:
        if f["kind"] == "mssql":
            cands.append(("info", f, f"(참고) MS SQL 데이터 파일 {f['path']} ({f['size_mb']} MB)"))
    cands.append(("manual", {}, "목록에 없음 — 직접 입력"))
    say("\n찾은 DB:")
    kind, item, _ = choose(cands, lambda c: c[2])
    if kind == "info":
        say("  MS SQL 데이터 파일은 SQL Server 서비스를 통해 읽습니다. 목록에서 MS SQL Server를 고르세요.")
        return connect_interactive()
    if kind == "manual":
        kind = choose(["firebird_file", "mssql", "mysql", "postgresql"], lambda k: k)
        item = {}

    if kind == "firebird_file":
        path = item.get("path") or ask("FDB 파일 경로")
        host = ask("Firebird 서버 주소 (이 PC면 그대로)", "localhost")
        # 병원이 아는 계정 또는 Firebird 설치 기본 계정으로만 접속한다 (비밀번호를 풀거나 보호 장치를 우회하지 않음)
        if ask("Firebird 설치 기본 계정(SYSDBA)으로 접속해 볼까요? (예 Y · 아니요 N)", "Y").strip().lower() in ("", "y", "yes", "예"):
            try:
                e = engines.Firebird(host, path, "SYSDBA", "masterkey")
                say("  기본 계정으로 접속했습니다")
                return e
            except Exception:
                say("  기본 계정으로 접속하지 못했습니다.")
        say("  병원이 알고 있는 계정을 입력하세요 (저장하지 않습니다). 모르면 차트 회사에 계정이나 내보내기 파일을 요청해 주세요")
        return engines.Firebird(host, path, ask("사용자", "SYSDBA"), getpass.getpass("비밀번호: "))

    if kind == "mssql":
        server = item.get("instance") or ask("SQL Server 이름 (예: .\\SQLEXPRESS)", ".\\SQLEXPRESS")
        user = pw = None
        try:
            dbs = engines.MsSql.databases(server)
            say("  Windows 로그인으로 접속했습니다")
        except Exception:
            say("  Windows 로그인으로는 접속하지 못했습니다. SQL 로그인이 있으면 입력하세요 (저장하지 않습니다)")
            user = ask("SQL 로그인", "sa")
            pw = getpass.getpass("비밀번호: ")
            dbs = engines.MsSql.databases(server, user, pw)
        db = choose(dbs, lambda d: d)
        return engines.MsSql(server, db, user, pw)

    if kind == "mysql":
        user = ask("MySQL 사용자", "root")
        pw = getpass.getpass("비밀번호 (저장하지 않습니다): ")
        db = choose(engines.MySql.databases("127.0.0.1", user, pw), lambda d: d)
        return engines.MySql("127.0.0.1", db, user, pw)

    user = ask("PostgreSQL 사용자", "postgres")
    pw = getpass.getpass("비밀번호 (저장하지 않습니다): ")
    port = ask("포트", "5432")
    db = choose(engines.Postgres.databases("127.0.0.1", user, pw, port), lambda d: d)
    return engines.Postgres("127.0.0.1", db, user, pw, port)


def main():
    if os.name == "nt":
        os.system("chcp 65001 >nul")
    say("=" * 64)
    say(f" VetChart 차트 구조 정보 추출 (베타) {TOOL_VERSION}")
    say("=" * 64)
    say(" 이 프로그램은 차트 DB를 '읽기만' 합니다. 아무것도 바꾸거나 지우지 않습니다.")
    say(" 보내는 파일에는 표·칸 이름, 형식, 건수, 값의 '모양'만 들어갑니다.")
    say(" 보호자 이름·전화번호·주소·진료 내용 같은 실제 값은 들어가지 않습니다.")
    say(" 진료가 끝난 뒤 실행하세요 (읽는 동안 차트가 잠깐 느려질 수 있습니다).")
    say("")
    say(" ※ 지금 차트에서 엑셀·CSV로 자료를 내보낼 수 있으면 이 프로그램은 필요 없습니다.")
    say("   그 파일로 VetChart 앱(설정 > 가져오기·내보내기)에서 바로 옮기시면 됩니다.")
    say("   이 프로그램은 엑셀로 내보낼 수 없는 병원이 'DB 구조'만 제출할 때 씁니다.")
    if ask("\n계속하려면 y를 입력하세요", "n").lower() != "y":
        return
    chart = ask("쓰시는 차트 프로그램 이름 (예: 인투벳, 이프렌즈)")

    try:
        eng = connect_interactive()
    except Exception as e:
        say(f"\nDB에 접속하지 못했습니다: {type(e).__name__}")
        say("차트 업체가 접속 정보를 막아 둔 경우일 수 있습니다. 이 화면을 사진으로 보내 주시면 도와드리겠습니다.")
        input("\nEnter를 누르면 닫힙니다")
        return

    say("\n구조를 읽는 중입니다…")
    try:
        result = collect(eng, progress=say)
    finally:
        eng.close()
    result["meta"] = {"tool_version": TOOL_VERSION, "created_at": datetime.now().isoformat(timespec="seconds"),
                      "chart_program": chart}

    desktop = Path(os.path.expanduser("~")) / "Desktop"
    folder = desktop / f"VetChart_구조정보_{datetime.now():%Y%m%d_%H%M}"
    z = write(result, folder)
    say(f"\n완료 — 표 {len(result['tables'])}개, {result['seconds']}초")
    say(f"결과 파일: {z}")
    say("미리보기를 엽니다. 보낼 내용을 확인해 주세요.")
    webbrowser.open((folder / "미리보기.html").as_uri())

    if ask("\n확인했으면 y를 입력하세요 — 제출 양식과 파일 위치를 엽니다 (제출하지 않으려면 n)", "y").lower() == "y":
        webbrowser.open(SUBMIT_FORM_URL)
        if os.name == "nt":
            os.system(f'explorer /select,"{z}"')
        say("\n열린 제출 양식(구글폼)에 병원 이름·사업자등록번호·차트 이름을 적고,")
        say(f"'구조 정보 파일' 칸에 바탕화면의 {z.name} 하나만 올려 주세요. (구글 로그인이 필요합니다)")
        say("※ 차트 내용(보호자·동물·진료 기록, 엑셀로 내보낸 자료, DB 파일 자체)은 절대 올리지 마세요.")
        say(f"양식이 열리지 않으면 {BETA_PAGE_URL} 의 '구조 파일 제출'을 이용해 주세요. 고맙습니다.")
    input("\nEnter를 누르면 닫힙니다")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
