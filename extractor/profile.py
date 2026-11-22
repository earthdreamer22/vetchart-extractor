# -*- coding: utf-8 -*-
"""칸(열) 하나의 '값의 모양'만 요약한다 — 실제 값은 결과에 남기지 않는다.

남기는 것: 비어 있는 비율, 날짜·전화번호·주민번호·이메일·RTF·HTML·암호화처럼 보이는 비율,
          글 길이(최소·평균·최대), 글자 종류 비율(한글·영문·숫자), 형식 틀(숫자→#, 한글→가, 영문→A),
          숫자 크기의 자릿수 범위, 날짜의 연도 범위
남기지 않는 것: 이름·전화번호·주소·진료 내용 같은 실제 값

예외 — 코드 값: 종류가 아주 적고(20가지 이하) 값마다 여러 번(5번 이상) 나오며 짧은 값(20자 이하)이고,
                이름·전화·주소·메모 같은 칸이 아니고, 전화·주민번호·이메일 모양이 아닐 때만
                값과 개수를 남긴다 (예: 성별 'M'·'F', 종 'Canine'·'Feline', 상태 코드) — 변환 규칙에 꼭 필요해서
"""
import math
import re
from collections import Counter
from datetime import date, datetime, time
from decimal import Decimal

RE = {
    "date": re.compile(r"^\d{4}[-./]?\d{1,2}[-./]?\d{1,2}$"),
    "datetime": re.compile(r"^\d{4}[-./]\d{1,2}[-./]\d{1,2}[ T]\d{1,2}:\d{2}"),
    "phone": re.compile(r"^0\d{1,2}[-) .]?\d{3,4}[- .]?\d{4}$"),
    "rrn": re.compile(r"^\d{6}-?[1-8]\d{6}$"),
    "email": re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"),
    "rtf": re.compile(r"^\{\\rtf", re.I),
    "html": re.compile(r"<(html|div|p|br|span|table)\b", re.I),
    "hex": re.compile(r"^[0-9A-Fa-f]{24,}$"),
    "base64": re.compile(r"^[A-Za-z0-9+/]{24,}={0,2}$"),
}
# 칸 이름이 이렇게 생겼으면 코드 값으로 보더라도 값을 남기지 않는다 (개인정보일 수 있음)
SENSITIVE_NAME = re.compile(
    r"(name|nm|이름|성명|tel|phone|mobile|hp|핸드폰|전화|addr|주소|email|mail|memo|note|메모|비고|"
    r"jumin|rrn|ssn|주민|birth|생년|card|카드|account|계좌|pass|pwd|비밀|doctor|doc|dr|vet|staff|user|emp|writer|담당|수의사|직원|의사|원장|작성)", re.I)

# 사람 이름처럼 생긴 값 (흔한 성씨로 시작하는 한글 2~4자) — 코드 값이어도 남기지 않는다 (직원·수의사 이름 등)
SURNAMES = set("김이박최정강조윤장임한오서신권황안송류전홍고문양손배백허유남심노하곽성차주우구민진나지엄채원천방공현함변염여추도소석선설마길연위표명기반라왕금옥육인맹제모탁국어은편용예봉경")
VET_WORDS = {"고양이", "강아지", "고양", "기타", "미상", "모름", "정상", "이상", "완료", "대기", "취소", "진료", "수납", "입원", "퇴원",
             "예약", "현금", "카드", "이체", "미수", "중성화", "수컷", "암컷", "유기", "보호", "사망", "전원", "신규", "재진"}


def looks_like_person_name(v: str) -> bool:
    return bool(re.fullmatch(r"[가-힣]{2,4}", v)) and v[0] in SURNAMES and v not in VET_WORDS

SAMPLE_ROWS = 500
MIN_CODE_COUNT = 5     # 코드 값으로 남기려면 표본에서 이만큼 이상 나와야 함


def _text(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray, memoryview)):
        return None
    return str(v)


def shape(s: str) -> str:
    """형식 틀 — 숫자는 #, 한글은 가, 영문은 A, 나머지 기호는 그대로 (20자까지)"""
    out = []
    for ch in s[:20]:
        if ch.isdigit():
            out.append("#")
        elif "가" <= ch <= "힣" or "ㄱ" <= ch <= "ㅣ":
            out.append("가")
        elif ch.isalpha():
            out.append("A")
        elif ch.isspace():
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out) + ("…" if len(s) > 20 else "")


def magnitude(x: float) -> str:
    """숫자 크기를 자릿수로만 (예: 0, 1~9, 10~99, …, 음수 표시)"""
    if x == 0:
        return "0"
    d = int(math.floor(math.log10(abs(x)))) if abs(x) >= 1 else -1
    sign = "-" if x < 0 else ""
    return f"{sign}<1" if d < 0 else f"{sign}10^{d}"


def profile_column(name: str, sql_type: str, values: list) -> dict:
    """값 목록(표본)에서 모양만 뽑는다"""
    n = len(values)
    out = {"name": name, "type": sql_type, "sample": n}
    if n == 0:
        return out
    nulls = sum(1 for v in values if v is None)
    out["null_ratio"] = round(nulls / n, 3)
    present = [v for v in values if v is not None]
    if not present:
        return out

    # 바이너리(사진·파일·암호화 자료일 수 있음)는 크기만
    bins = [v for v in present if isinstance(v, (bytes, bytearray, memoryview))]
    if bins:
        sizes = [len(bytes(b)) for b in bins]
        out["binary"] = {"ratio": round(len(bins) / len(present), 3), "avg_bytes": int(sum(sizes) / len(sizes)),
                         "starts": Counter(_magic(bytes(b)) for b in bins).most_common(3)}

    nums = [float(v) for v in present if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)]
    if nums:
        out["number"] = {"ratio": round(len(nums) / len(present), 3), "min": magnitude(min(nums)), "max": magnitude(max(nums)),
                         "integer_ratio": round(sum(1 for x in nums if float(x).is_integer()) / len(nums), 3)}
        codes = _numeric_codes(name, nums)
        if codes:
            out["number"]["code_values"] = codes

    dts = [v for v in present if isinstance(v, (date, datetime))]
    if dts:
        years = [v.year for v in dts]
        out["date"] = {"ratio": round(len(dts) / len(present), 3), "year_min": min(years), "year_max": max(years),
                       "has_time": any(isinstance(v, datetime) and (v.hour or v.minute) for v in dts)}
    if any(isinstance(v, time) for v in present):
        out["time_ratio"] = round(sum(1 for v in present if isinstance(v, time)) / len(present), 3)

    texts = [t for t in (_text(v) for v in present
                         if not isinstance(v, (bytes, bytearray, memoryview, date, datetime, time, int, float, Decimal, bool)))
             if t is not None]
    if texts:
        stripped = [t.strip() for t in texts]
        empty = sum(1 for t in stripped if not t)
        filled = [t for t in stripped if t]
        info = {"ratio": round(len(texts) / len(present), 3), "empty_ratio": round(empty / len(texts), 3)}
        if filled:
            lens = [len(t) for t in filled]
            info["len_min"], info["len_avg"], info["len_max"] = min(lens), round(sum(lens) / len(lens), 1), max(lens)
            joined = "".join(filled)
            total = max(1, len(joined))
            info["chars"] = {"hangul": round(sum(1 for c in joined if "가" <= c <= "힣") / total, 3),
                             "latin": round(sum(1 for c in joined if c.isascii() and c.isalpha()) / total, 3),
                             "digit": round(sum(1 for c in joined if c.isdigit()) / total, 3)}
            looks = {k: round(sum(1 for t in filled if rx.search(t)) / len(filled), 3) for k, rx in RE.items()}
            info["looks_like"] = {k: v for k, v in looks.items() if v > 0}
            info["shapes"] = [s for s, _ in Counter(shape(t) for t in filled if len(t) <= 40).most_common(5)]
            enum = _enum_values(name, filled, looks)
            if enum:
                info["code_values"] = enum
        out["text"] = info
    return out


def _magic(b: bytes) -> str:
    """바이너리 앞부분으로 파일 종류만 (내용은 남기지 않음)"""
    sig = {b"\xff\xd8\xff": "jpeg", b"\x89PNG": "png", b"GIF8": "gif", b"%PDF": "pdf", b"{\\rtf": "rtf",
           b"PK\x03\x04": "zip/office", b"BM": "bmp", b"DICM": "dicom"}
    for k, v in sig.items():
        if b.startswith(k):
            return v
    if len(b) > 132 and b[128:132] == b"DICM":
        return "dicom"
    return "unknown"


def _enum_values(col: str, filled: list, looks: dict):
    """코드 값 — 자주 나오는 짧은 값만 (5번 이상). 드문 값은 개수만 세고 값은 남기지 않는다"""
    if SENSITIVE_NAME.search(col):
        return None
    if any(looks.get(k, 0) > 0 for k in ("phone", "rrn", "email", "hex", "base64")):
        return None
    c = Counter(filled)
    if len(c) > 30:
        return None
    if sum(1 for v in c if looks_like_person_name(v)) >= max(1, len(c) // 3):
        return None                       # 값 다수가 사람 이름 모양이면 칸 전체를 남기지 않는다
    common = [(v, k) for v, k in c.most_common() if k >= MIN_CODE_COUNT and len(v) <= 20
              and not re.fullmatch(r"\d{7,}", v) and not looks_like_person_name(v)]
    covered = sum(k for _, k in common)
    if not common or covered < 0.8 * len(filled):
        return None                       # 대부분이 드문 값이면 코드가 아니라 자유 입력으로 본다
    out = [[v, k] for v, k in common]
    rare = len(c) - len(common)
    if rare:
        out.append([f"(그 밖 {rare}가지 — 드물어 값은 남기지 않음)", len(filled) - covered])
    return out


def _numeric_codes(col: str, nums: list):
    """작은 정수 코드(상태·구분 0/1/2 등) — 자주 나오는 값만"""
    if SENSITIVE_NAME.search(col) or not nums or any(not float(x).is_integer() for x in nums):
        return None
    c = Counter(int(x) for x in nums)
    if len(c) > 10 or any(abs(v) > 9999 for v in c):
        return None
    common = [[v, k] for v, k in c.most_common() if k >= MIN_CODE_COUNT]
    if not common or sum(k for _, k in common) < 0.8 * len(nums):
        return None
    return common
