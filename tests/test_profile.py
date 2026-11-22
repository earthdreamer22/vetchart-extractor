# -*- coding: utf-8 -*-
"""개인정보 규칙 시험 — 실제 값이 결과에 남지 않는지 (가짜 데이터)"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extractor.profile import profile_column, shape  # noqa: E402

NAMES = ["김철수", "이영희", "박민수", "최지우", "정다은"] * 40          # 사람 이름 (반복돼도 남기면 안 됨)
PHONES = [f"010-{1000 + i}-{2000 + i}" for i in range(200)]


def dump(p):
    return json.dumps(p, ensure_ascii=False, default=str)


def test_names_and_phones_never_appear():
    for col, vals in (("C_NAME", NAMES), ("OWNER", NAMES), ("VET", NAMES), ("CODE1", NAMES), ("C_MOBILE", PHONES), ("X", PHONES)):
        out = dump(profile_column(col, "VARCHAR", vals))
        assert not any(v in out for v in set(vals)), col


def test_staff_name_like_codes_are_dropped_even_in_neutral_column():
    vals = ["김원장"] * 300 + ["박수의"] * 150 + ["Canine"] * 50
    p = profile_column("S_GUBUN", "VARCHAR", vals)
    assert "김원장" not in dump(p) and "박수의" not in dump(p)


def test_category_codes_kept_rare_values_hidden():
    vals = ["Canine"] * 380 + ["Feline"] * 115 + ["Rabbit"] * 2 + ["Hamster"] * 3
    codes = profile_column("P_SPEC", "VARCHAR", vals)["text"]["code_values"]
    assert ["Canine", 380] in codes and ["Feline", 115] in codes
    out = json.dumps(codes, ensure_ascii=False)
    assert "Rabbit" not in out and "Hamster" not in out and "그 밖 2가지" in out


def test_free_text_has_no_codes_only_shapes():
    vals = [f"구토 {i}회, 식욕 저하 {i % 3}일째" for i in range(300)]
    p = profile_column("S_SUBJECT", "BLOB TEXT", vals)
    assert "code_values" not in p["text"] and "구토" not in dump(p)
    assert p["text"]["len_max"] >= p["text"]["len_min"]


def test_rrn_and_email_detected_not_stored():
    rrn = [f"9{i:05d}-1{i:06d}" for i in range(50)]
    mails = [f"user{i}@example.com" for i in range(50)]
    p1, p2 = profile_column("ID_NO", "VARCHAR", rrn), profile_column("CONTACT", "VARCHAR", mails)
    assert p1["text"]["looks_like"].get("rrn") == 1.0 and p2["text"]["looks_like"].get("email") == 1.0
    assert not any(v in dump(p1) for v in rrn) and not any(v in dump(p2) for v in mails)


def test_numbers_dates_binary_shapes_only():
    p = profile_column("PRICE", "NUMERIC", [Decimal("15000.00"), Decimal("33000"), 0, None])
    assert p["number"]["max"] == "10^4" and "15000" not in dump(p)
    d = profile_column("VISIT", "DATE", [date(2013, 2, 1), datetime(2026, 11, 3, 10, 30)])
    assert d["date"]["year_min"] == 2013 and d["date"]["year_max"] == 2026 and "11" not in json.dumps(d["date"])
    b = profile_column("PHOTO", "BLOB", [b"\xff\xd8\xff\xe0secret", b"%PDF-1.4 secret"])
    assert "secret" not in dump(b) and b["binary"]["ratio"] == 1.0


def test_small_integer_codes():
    p = profile_column("P_DEL", "INTEGER", [0] * 460 + [1] * 35 + [7] * 2)
    assert p["number"]["code_values"] == [[0, 460], [1, 35]]
    assert "code_values" not in profile_column("C_ID", "INTEGER", list(range(500)))["number"]


def test_shape():
    assert shape("2026-11-03") == "####-##-##" and shape("초코 Choco") == "가가 AAAAA"


def test_code_tables_and_code_columns_keep_no_values():
    from extractor.profile import is_master_table
    vals = ["PO"] * 300 + ["SC"] * 200
    assert "\"PO\"" not in dump(profile_column("PL_GROUP", "VARCHAR", vals, allow_codes=False))
    assert "\"PO\"" not in dump(profile_column("PLCODE", "VARCHAR", vals))        # 코드 칸
    assert "\"PO\"" in dump(profile_column("PL_GROUP", "VARCHAR", vals))           # 진료 기록 표의 구분 값은 남김
    for t in ("PLANLIST", "RX_CODE", "MEDICINE", "VACCINE", "dbo.DrugMaster", "약품목록"):
        assert is_master_table(t), t
    keys = {"foreign": [["charts", "patient_id", "patients", "id"], ["patients", "client_id", "clients", "id"],
                        ["invoice_items", "service_item_id", "service_items", "id"]]}
    assert not is_master_table("patients", keys) and not is_master_table("charts", keys)
    assert is_master_table("clients", keys)


def test_amounts_are_never_codes():
    assert "code_values" not in profile_column("price", "INTEGER", [0] * 300 + [7000] * 200)["number"]
    assert "code_values" not in profile_column("Q", "INTEGER", [0] * 300 + [7000] * 200)["number"]   # 99보다 큰 값


def test_clinic_names_dropped():
    out = dump(profile_column("PD_TREAT", "VARCHAR", ["행복동물병원"] * 480 + ["외부"] * 20))
    assert "행복동물병원" not in out
