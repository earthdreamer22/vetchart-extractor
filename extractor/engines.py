# -*- coding: utf-8 -*-
"""DB 엔진별 읽기 — 모두 읽기만 한다 (SELECT와 목록 조회만, 쓰기·변경 없음)

엔진마다 같은 질문에 답한다: 표 목록, 칸 목록(이름·형식·빈칸 허용·길이), 기본 키·외래 키, 행 수, 표본(최대 500행)
표본은 이 PC 안에서 '모양'으로만 요약되고 결과 파일에는 남지 않는다 (profile.py)
"""
from __future__ import annotations


class Engine:
    kind = ""

    def tables(self) -> list[str]: ...
    def columns(self, table: str) -> list[dict]: ...
    def keys(self) -> dict: return {"primary": {}, "foreign": []}
    def row_count(self, table: str) -> int | None: ...
    def sample(self, table: str, n: int) -> tuple[list[str], list[tuple]]: ...
    def info(self) -> dict: return {}

    def recover(self):
        """오류 뒤 다음 표를 읽을 수 있게 (엔진마다 필요하면 다시 연결)"""
        try:
            self.conn.rollback()
        except Exception:
            pass

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    def _q(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        cur.close()
        return cols, rows


# ── Firebird / InterBase (.fdb .gdb) ─────────────────────────────
def _register_lenient_cp949():
    import codecs
    base = codecs.lookup("cp949")

    def search(name):
        if name != "vc_cp949":
            return None
        return codecs.CodecInfo(name="vc_cp949", encode=base.encode,
                                decode=lambda b, errors="strict": base.decode(b, "replace"))
    try:
        codecs.lookup("vc_cp949")
    except LookupError:
        codecs.register(search)


class Firebird(Engine):
    kind = "firebird"

    def __init__(self, host, path, user, password, port=3050, charset=None):
        import firebirdsql
        import firebirdsql.wireprotocol as wp
        # 국내 프로그램의 KSC_5601 자료에는 확장 한글(CP949)과 깨진 바이트가 섞여 있다 — EUC-KR로 엄격히 읽으면
        # 오류가 나고 연결까지 깨진다 → CP949로 읽고 깨진 바이트는 대체 문자로 (모양 요약에는 영향 없음)
        _register_lenient_cp949()
        wp.charset_map["KSC_5601"] = "vc_cp949"
        self._args = (host, path, user, password, port)
        last = None
        for cs in ([charset] if charset else ["KSC_5601", "UTF8"]):
            try:
                self.conn = firebirdsql.connect(host=host, port=int(port), database=path, user=user, password=password, charset=cs)
                self.charset = cs
                return
            except Exception as e:
                # 문자셋 문제일 때만 다음 문자셋으로, 그 밖(파일 없음·암호 틀림·서버 꺼짐)은 그 오류를 그대로
                if "charset" not in str(e).lower() and "character set" not in str(e).lower():
                    raise
                last = e
        raise last

    def recover(self):
        """읽다 오류가 나면 연결 흐름이 깨질 수 있어 다시 연결한다"""
        import firebirdsql
        try:
            self.conn.close()
        except Exception:
            pass
        host, path, user, password, port = self._args
        self.conn = firebirdsql.connect(host=host, port=int(port), database=path, user=user, password=password, charset=self.charset)

    def tables(self):
        _, rows = self._q("SELECT TRIM(RDB$RELATION_NAME) FROM RDB$RELATIONS "
                          "WHERE COALESCE(RDB$SYSTEM_FLAG,0)=0 AND RDB$VIEW_BLR IS NULL ORDER BY 1")
        return [r[0] for r in rows]

    TYPES = {7: "SMALLINT", 8: "INTEGER", 10: "FLOAT", 12: "DATE", 13: "TIME", 14: "CHAR", 16: "BIGINT", 27: "DOUBLE",
             35: "TIMESTAMP", 37: "VARCHAR", 261: "BLOB"}

    def columns(self, table):
        _, rows = self._q(
            "SELECT TRIM(rf.RDB$FIELD_NAME), f.RDB$FIELD_TYPE, f.RDB$FIELD_SUB_TYPE, f.RDB$CHARACTER_LENGTH, "
            "f.RDB$FIELD_SCALE, rf.RDB$NULL_FLAG FROM RDB$RELATION_FIELDS rf "
            "JOIN RDB$FIELDS f ON f.RDB$FIELD_NAME = rf.RDB$FIELD_SOURCE "
            "WHERE rf.RDB$RELATION_NAME = ? ORDER BY rf.RDB$FIELD_POSITION", (table,))
        out = []
        for name, t, sub, clen, scale, notnull in rows:
            tn = self.TYPES.get(t, str(t))
            if t == 261:
                tn = "BLOB TEXT" if sub == 1 else "BLOB"
            if scale and scale < 0:
                tn = f"NUMERIC(scale {-scale})"
            out.append({"name": name, "type": tn, "nullable": not notnull, "length": clen})
        return out

    def keys(self):
        _, pk = self._q(
            "SELECT TRIM(rc.RDB$RELATION_NAME), TRIM(s.RDB$FIELD_NAME) FROM RDB$RELATION_CONSTRAINTS rc "
            "JOIN RDB$INDEX_SEGMENTS s ON s.RDB$INDEX_NAME = rc.RDB$INDEX_NAME WHERE rc.RDB$CONSTRAINT_TYPE = 'PRIMARY KEY'")
        _, fk = self._q(
            "SELECT TRIM(rc.RDB$RELATION_NAME), TRIM(s.RDB$FIELD_NAME), TRIM(rc2.RDB$RELATION_NAME), TRIM(s2.RDB$FIELD_NAME) "
            "FROM RDB$RELATION_CONSTRAINTS rc JOIN RDB$REF_CONSTRAINTS r ON r.RDB$CONSTRAINT_NAME = rc.RDB$CONSTRAINT_NAME "
            "JOIN RDB$RELATION_CONSTRAINTS rc2 ON rc2.RDB$CONSTRAINT_NAME = r.RDB$CONST_NAME_UQ "
            "JOIN RDB$INDEX_SEGMENTS s ON s.RDB$INDEX_NAME = rc.RDB$INDEX_NAME "
            "JOIN RDB$INDEX_SEGMENTS s2 ON s2.RDB$INDEX_NAME = rc2.RDB$INDEX_NAME AND s2.RDB$FIELD_POSITION = s.RDB$FIELD_POSITION "
            "WHERE rc.RDB$CONSTRAINT_TYPE = 'FOREIGN KEY'")
        prim = {}
        for t, c in pk:
            prim.setdefault(t, []).append(c)
        return {"primary": prim, "foreign": [list(r) for r in fk]}

    def row_count(self, table):
        _, rows = self._q(f'SELECT COUNT(*) FROM "{table}"')
        return rows[0][0]

    def sample(self, table, n):
        return self._q(f'SELECT FIRST {int(n)} * FROM "{table}"')

    def info(self):
        try:
            _, rows = self._q("SELECT rdb$get_context('SYSTEM','ENGINE_VERSION') FROM RDB$DATABASE")
            ver = rows[0][0]
        except Exception:
            ver = "2.x 이하 (버전 함수 없음)"
        return {"engine_version": ver, "charset": self.charset}


# ── MS SQL Server (.mdf) ─────────────────────────────────────────
class MsSql(Engine):
    kind = "mssql"

    def __init__(self, server, database, user=None, password=None):
        import pyodbc
        auth = f"UID={user};PWD={password}" if user else "Trusted_Connection=yes"
        last = None
        for drv in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"):
            if drv not in pyodbc.drivers():
                continue
            try:
                extra = ";TrustServerCertificate=yes" if "18" in drv or "17" in drv else ""
                self.conn = pyodbc.connect(f"DRIVER={{{drv}}};SERVER={server};DATABASE={database};{auth}{extra}",
                                           timeout=10, readonly=True)
                self.database = database
                return
            except Exception as e:
                last = e
        raise last or RuntimeError("SQL Server ODBC 드라이버가 없습니다")

    @staticmethod
    def databases(server, user=None, password=None) -> list[str]:
        import pyodbc
        auth = f"UID={user};PWD={password}" if user else "Trusted_Connection=yes"
        c = pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={server};{auth}", timeout=10)
        rows = c.cursor().execute("SELECT name FROM sys.databases WHERE database_id > 4 ORDER BY name").fetchall()
        c.close()
        return [r[0] for r in rows]

    def tables(self):
        _, rows = self._q("SELECT TABLE_SCHEMA + '.' + TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                          "WHERE TABLE_TYPE='BASE TABLE' ORDER BY 1")
        return [r[0] for r in rows]

    def columns(self, table):
        schema, name = table.split(".", 1)
        _, rows = self._q("SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS "
                          "WHERE TABLE_SCHEMA=? AND TABLE_NAME=? ORDER BY ORDINAL_POSITION", (schema, name))
        return [{"name": r[0], "type": r[1], "nullable": r[2] == "YES", "length": r[3]} for r in rows]

    def keys(self):
        _, pk = self._q("SELECT ku.TABLE_SCHEMA + '.' + ku.TABLE_NAME, ku.COLUMN_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc "
                        "JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku ON ku.CONSTRAINT_NAME = tc.CONSTRAINT_NAME "
                        "WHERE tc.CONSTRAINT_TYPE='PRIMARY KEY'")
        _, fk = self._q("SELECT OBJECT_SCHEMA_NAME(f.parent_object_id) + '.' + OBJECT_NAME(f.parent_object_id), "
                        "COL_NAME(fc.parent_object_id, fc.parent_column_id), "
                        "OBJECT_SCHEMA_NAME(f.referenced_object_id) + '.' + OBJECT_NAME(f.referenced_object_id), "
                        "COL_NAME(fc.referenced_object_id, fc.referenced_column_id) "
                        "FROM sys.foreign_keys f JOIN sys.foreign_key_columns fc ON fc.constraint_object_id = f.object_id")
        prim = {}
        for t, c in pk:
            prim.setdefault(t, []).append(c)
        return {"primary": prim, "foreign": [list(r) for r in fk]}

    def row_count(self, table):
        _, rows = self._q("SELECT SUM(p.rows) FROM sys.partitions p WHERE p.object_id = OBJECT_ID(?) AND p.index_id IN (0,1)", (table,))
        return int(rows[0][0] or 0)

    def sample(self, table, n):
        schema, name = table.split(".", 1)
        return self._q(f"SELECT TOP {int(n)} * FROM [{schema}].[{name}]")

    def info(self):
        _, v = self._q("SELECT @@VERSION")
        enc = None
        try:
            _, e = self._q("SELECT is_encrypted FROM sys.databases WHERE name = ?", (self.database,))
            enc = bool(e[0][0])
        except Exception:
            pass
        return {"engine_version": (v[0][0] or "").splitlines()[0], "database_encrypted": enc}


# ── MySQL / MariaDB ──────────────────────────────────────────────
class MySql(Engine):
    kind = "mysql"

    def __init__(self, host, database, user, password, port=3306):
        import pymysql
        self.conn = pymysql.connect(host=host, port=int(port), user=user, password=password, database=database,
                                    charset="utf8mb4", connect_timeout=10, read_timeout=120)
        self.database = database
        cur = self.conn.cursor()
        cur.execute("SET SESSION TRANSACTION READ ONLY")
        cur.close()

    @staticmethod
    def databases(host, user, password, port=3306) -> list[str]:
        import pymysql
        c = pymysql.connect(host=host, port=int(port), user=user, password=password, connect_timeout=10)
        cur = c.cursor()
        cur.execute("SHOW DATABASES")
        out = [r[0] for r in cur.fetchall() if r[0] not in ("information_schema", "mysql", "performance_schema", "sys")]
        c.close()
        return out

    def tables(self):
        _, rows = self._q("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' "
                          "ORDER BY 1", (self.database,))
        return [r[0] for r in rows]

    def columns(self, table):
        _, rows = self._q("SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH FROM information_schema.COLUMNS "
                          "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION", (self.database, table))
        return [{"name": r[0], "type": r[1], "nullable": r[2] == "YES", "length": r[3]} for r in rows]

    def keys(self):
        _, rows = self._q("SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME, CONSTRAINT_NAME "
                          "FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=%s", (self.database,))
        prim, fk = {}, []
        for t, c, rt, rc, cn in rows:
            if cn == "PRIMARY":
                prim.setdefault(t, []).append(c)
            elif rt:
                fk.append([t, c, rt, rc])
        return {"primary": prim, "foreign": fk}

    def row_count(self, table):
        _, rows = self._q(f"SELECT COUNT(*) FROM `{table}`")
        return rows[0][0]

    def sample(self, table, n):
        return self._q(f"SELECT * FROM `{table}` LIMIT {int(n)}")

    def info(self):
        _, v = self._q("SELECT VERSION()")
        return {"engine_version": v[0][0]}


# ── PostgreSQL ───────────────────────────────────────────────────
class Postgres(Engine):
    kind = "postgresql"

    def __init__(self, host, database, user, password, port=5432):
        import psycopg2
        self.conn = psycopg2.connect(host=host, port=int(port), dbname=database, user=user, password=password, connect_timeout=10)
        self.conn.set_session(readonly=True, autocommit=True)
        self.database = database

    @staticmethod
    def databases(host, user, password, port=5432) -> list[str]:
        import psycopg2
        c = psycopg2.connect(host=host, port=int(port), dbname="postgres", user=user, password=password, connect_timeout=10)
        cur = c.cursor()
        cur.execute("SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres' ORDER BY 1")
        out = [r[0] for r in cur.fetchall()]
        c.close()
        return out

    def tables(self):
        _, rows = self._q("SELECT table_schema || '.' || table_name FROM information_schema.tables WHERE table_type='BASE TABLE' "
                          "AND table_schema NOT IN ('pg_catalog','information_schema') ORDER BY 1")
        return [r[0] for r in rows]

    def columns(self, table):
        schema, name = table.split(".", 1)
        _, rows = self._q("SELECT column_name, data_type, is_nullable, character_maximum_length FROM information_schema.columns "
                          "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position", (schema, name))
        return [{"name": r[0], "type": r[1], "nullable": r[2] == "YES", "length": r[3]} for r in rows]

    def keys(self):
        _, rows = self._q(
            "SELECT tc.table_schema || '.' || tc.table_name, kcu.column_name, tc.constraint_type, "
            "ccu.table_schema || '.' || ccu.table_name, ccu.column_name FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema "
            "LEFT JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name "
            "WHERE tc.constraint_type IN ('PRIMARY KEY','FOREIGN KEY')")
        prim, fk = {}, []
        for t, c, kind, rt, rc in rows:
            if kind == "PRIMARY KEY":
                prim.setdefault(t, []).append(c)
            else:
                fk.append([t, c, rt, rc])
        return {"primary": prim, "foreign": fk}

    def row_count(self, table):
        schema, name = table.split(".", 1)
        _, rows = self._q(f'SELECT COUNT(*) FROM "{schema}"."{name}"')
        return rows[0][0]

    def sample(self, table, n):
        schema, name = table.split(".", 1)
        return self._q(f'SELECT * FROM "{schema}"."{name}" LIMIT {int(n)}')

    def info(self):
        _, v = self._q("SHOW server_version")
        return {"engine_version": v[0][0]}
