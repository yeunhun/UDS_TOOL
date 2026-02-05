#!/usr/bin/env python3
"""
Seed → Key UDP Test Client (Raspberry Pi)

- 실행하면:
  1) UDP 서버 헬스체크
  2) TEST_COUNT 만큼 seed 전송 → key 수신
  3) output/seed_key_result.csv 에 아래 형식으로 저장

예)
timestamp          ,seed_hex               ,key_hex                ,latency_ms
2025-12-13 19:51:42,5F C8 A2 49 B4 13 66 4D,3D 9D 7E E7 69 D4 8E D0,3.072
"""

# =====================================================
# CONFIGURATION (여기만 수정하면 됩니다)
# =====================================================
SERVER_IP      = "192.168.0.29"   # Windows 키생성 서버 IP
SERVER_PORT    = 5005             # UDP 포트
TEST_COUNT     = 200              # 시험 횟수
UDP_TIMEOUT    = 2.0              # 응답 타임아웃 (초)
SLEEP_BETWEEN  = 0.0              # 각 요청 사이 대기 시간 (초)
FIXED_SEED     = None             # None = 랜덤 시드
# FIXED_SEED   = "0123456789ABCDEF"  # 같은 시드로만 시험할 경우 (공백 없이 16 hex)

OUTPUT_DIR     = "output"
RESULT_CSV     = "seed_key_result.csv"
PROGRESS_EVERY = 20

HEALTHCHECK_SEED = "0001020304050607"  # 시작 전 서버 응답 확인용 seed
# =====================================================

import os
import socket
import secrets
import time
import statistics


# -----------------------------------------------------
# Formatting helpers
# -----------------------------------------------------
def hex_to_spaced(hex_str: str) -> str:
    """'5FC8A2...' 또는 '5F C8 A2 ...' -> '5F C8 A2 ...' 로 정규화"""
    s = hex_str.replace(" ", "").strip().upper()
    if len(s) % 2 != 0:
        # 홀수 길이면 마지막 0 보정(혹시 모를 방어)
        s = "0" + s
    return " ".join(s[i:i+2] for i in range(0, len(s), 2))


def bytes_to_spaced(b: bytes) -> str:
    """b'\\x5f\\xc8...' -> '5F C8 ...'"""
    return " ".join(f"{x:02X}" for x in b)


def now_timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


# -----------------------------------------------------
# Core
# -----------------------------------------------------
def generate_seed_hex_nospace() -> str:
    """8바이트 시드를 공백 없는 HEX 문자열(16 chars)로 생성"""
    if FIXED_SEED:
        return FIXED_SEED.replace(" ", "").strip().upper()
    return secrets.token_bytes(8).hex().upper()


def udp_request(seed_hex_nospace: str) -> bytes:
    """UDP로 seed 전송 후 raw 응답 수신"""
    message = (seed_hex_nospace + "\n").encode("ascii")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(UDP_TIMEOUT)
    try:
        sock.sendto(message, (SERVER_IP, SERVER_PORT))
        data, _ = sock.recvfrom(1024)
        return data
    finally:
        sock.close()


def parse_key_response_to_bytes(data: bytes) -> bytes:
    """
    서버 응답을 key bytes로 변환.
    - 텍스트 에러면 예외
    - ASCII HEX 키면 bytes로 변환
    - 바이너리면 그대로 반환
    """
    if not data:
        raise RuntimeError("Empty response")

    # ASCII로 디코드 시도
    try:
        txt = data.decode("ascii", errors="strict").strip()
        low = txt.lower()
        if "fail" in low or "invalid" in low or "error" in low:
            raise RuntimeError(txt)

        # ASCII HEX일 가능성: 공백 제거 후 fromhex 시도
        compact = txt.replace(" ", "").strip()
        if compact and all(c in "0123456789abcdefABCDEF" for c in compact) and len(compact) % 2 == 0:
            return bytes.fromhex(compact)

        # ASCII인데 HEX가 아니면(예: "OK" 같은 응답) -> 예외 처리
        # 필요하면 여기서 그대로 저장하도록 바꿀 수 있지만,
        # Seed-Key 용도로는 HEX/binary만 유효하므로 에러로 취급
        raise RuntimeError(f"Unexpected ASCII response: {txt}")

    except UnicodeDecodeError:
        # 바이너리 키로 간주
        return data


def ensure_output_csv() -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, RESULT_CSV)

    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8", newline="") as f:
            # 요청하신 헤더 “모양” 유지(공백 포함)
            f.write("timestamp          ,seed_hex               ,key_hex                ,latency_ms\n")

    return path


def healthcheck():
    """시작 전 서버가 응답 가능한지 확인"""
    seed = HEALTHCHECK_SEED.replace(" ", "").strip().upper()
    t0 = time.perf_counter()
    data = udp_request(seed)
    key_b = parse_key_response_to_bytes(data)
    ms = (time.perf_counter() - t0) * 1000.0
    return seed, key_b, ms


def percentile(sorted_list, p: int) -> float:
    idx = int((p / 100.0) * (len(sorted_list) - 1))
    return sorted_list[idx]


# -----------------------------------------------------
# Main
# -----------------------------------------------------
def main():
    print("==============================================")
    print(" SeedKey UDP Test Client (Raspberry Pi)")
    print("==============================================")
    print(f"Server IP   : {SERVER_IP}")
    print(f"Server Port : {SERVER_PORT}")
    print(f"Test Count  : {TEST_COUNT}")
    print(f"Timeout     : {UDP_TIMEOUT}s")
    print(f"Sleep       : {SLEEP_BETWEEN}s")
    print(f"Seed Mode   : {'FIXED' if FIXED_SEED else 'RANDOM'}")
    print("----------------------------------------------")

    csv_path = ensure_output_csv()
    print(f"[STEP] CSV 저장 경로: {csv_path}")

    print("[STEP] Healthcheck...")
    try:
        seed_hc, key_hc_b, ms_hc = healthcheck()
        print(f"[OK ] Healthcheck seed={hex_to_spaced(seed_hc)} key={bytes_to_spaced(key_hc_b)} ({ms_hc:.3f} ms)")
    except Exception as e:
        print(f"[FAIL] Healthcheck failed: {e}")
        print("→ Dll_Server.exe 실행 여부, IP/PORT, 방화벽, 네트워크를 확인하세요.")
        return

    ok = 0
    fail = 0
    latencies = []

    print("[STEP] Running tests...")
    for i in range(1, TEST_COUNT + 1):
        seed = generate_seed_hex_nospace()

        t0 = time.perf_counter()
        try:
            data = udp_request(seed)
            key_b = parse_key_response_to_bytes(data)
            latency_ms = (time.perf_counter() - t0) * 1000.0

            ts = now_timestamp()
            seed_sp = hex_to_spaced(seed)
            key_sp  = bytes_to_spaced(key_b)

            # CSV 저장 (요청하신 모양 그대로)
            with open(csv_path, "a", encoding="utf-8", newline="") as f:
                f.write(f"{ts},{seed_sp},{key_sp},{latency_ms:.3f}\n")

            ok += 1
            latencies.append(latency_ms)

        except Exception as e:
            fail += 1
            print(f"[FAIL] {i}/{TEST_COUNT} seed={hex_to_spaced(seed)} reason={e}")

        if (i % PROGRESS_EVERY == 0) or (i == TEST_COUNT):
            if latencies:
                p50 = statistics.median(latencies)
                print(f"[INFO] {i}/{TEST_COUNT} ok={ok} fail={fail} p50={p50:.2f} ms")
            else:
                print(f"[INFO] {i}/{TEST_COUNT} ok={ok} fail={fail}")

        if SLEEP_BETWEEN > 0:
            time.sleep(SLEEP_BETWEEN)

    print("\n=============== RESULT =================")
    print(f"CSV Path    : {csv_path}")
    print(f"Total tests : {TEST_COUNT}")
    print(f"Success     : {ok}")
    print(f"Fail        : {fail}")

    if latencies:
        latencies.sort()
        print(
            "Latency(ms) : "
            f"p50={percentile(latencies, 50):.2f}, "
            f"p90={percentile(latencies, 90):.2f}, "
            f"p99={percentile(latencies, 99):.2f}, "
            f"max={max(latencies):.2f}"
        )
    else:
        print("No successful responses.")

    print("========================================")


if __name__ == "__main__":
    main()
