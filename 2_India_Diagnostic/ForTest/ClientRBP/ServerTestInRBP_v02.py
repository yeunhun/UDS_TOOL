#!/usr/bin/env python3
"""
Seed → Key UDP Test Client (Raspberry Pi Zero 2W)

실행 시 자동 흐름:
1) 서버 헬스체크(UDP) → 2) 테스트 실행 → 3) SEED/KEY CSV 저장 → 4) 요약 통계 출력

※ 설정은 CONFIG 섹션만 수정하세요.
"""

# =====================================================
# CONFIGURATION (여기만 수정하면 됩니다)
# =====================================================
SERVER_IP      = "172.30.1.29"   # Windows 키생성 서버 IP
SERVER_PORT    = 5005             # UDP 포트
TEST_COUNT     = 200              # 시험 횟수
UDP_TIMEOUT    = 2.0              # 응답 타임아웃 (초)
SLEEP_BETWEEN  = 0.0              # 각 요청 사이 대기 시간 (초)
FIXED_SEED     = None             # None = 랜덤 시드
# FIXED_SEED   = "0123456789ABCDEF"  # 같은 시드로만 시험할 경우

# 저장 파일
OUTPUT_DIR     = "output"
RESULT_CSV     = "seed_key_result.csv"

# 진행 로그 출력 주기 (N회마다 출력)
PROGRESS_EVERY = 20

# 시작 전 헬스체크용 시드(서버가 “아무 seed나” 받아야 함)
HEALTHCHECK_SEED = "0001020304050607"
# =====================================================

import os
import socket
import secrets
import time
import statistics


# -----------------------------------------------------
# Utility
# -----------------------------------------------------
def generate_seed_hex() -> str:
    """8바이트 시드를 HEX 문자열로 생성"""
    if FIXED_SEED:
        return FIXED_SEED
    return secrets.token_bytes(8).hex().upper()


def ensure_output():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUTPUT_DIR, RESULT_CSV)
    if not os.path.exists(csv_path):
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("timestamp,seed_hex,key_hex,latency_ms\n")
    return csv_path


def udp_request(seed_hex: str) -> bytes:
    """UDP로 seed 전송 후 raw 응답 수신"""
    message = (seed_hex + "\n").encode("ascii")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(UDP_TIMEOUT)

    try:
        sock.sendto(message, (SERVER_IP, SERVER_PORT))
        data, _ = sock.recvfrom(1024)
        return data
    finally:
        sock.close()


def parse_key_response(data: bytes) -> str:
    """
    서버 응답에서 key를 HEX 문자열로 반환.
    - 텍스트 에러 응답이면 예외 발생
    """
    if len(data) == 0:
        raise RuntimeError("Empty response")

    # 텍스트 에러 응답 감지
    try:
        txt = data.decode("ascii", errors="strict").strip()
        if "fail" in txt.lower() or "invalid" in txt.lower() or "error" in txt.lower():
            raise RuntimeError(txt)
        # 서버가 ASCII로 HEX 키를 보낼 수도 있으므로,
        # 길이/형태가 HEX 같으면 그대로 사용
        maybe_hex = txt.replace(" ", "").upper()
        if all(c in "0123456789ABCDEF" for c in maybe_hex) and len(maybe_hex) >= 2:
            return maybe_hex
    except UnicodeDecodeError:
        pass

    # 바이너리 키로 간주
    return data.hex().upper()


def healthcheck() -> str:
    """
    시작 전 서버가 응답 가능한지 확인.
    성공 시 key_hex 반환, 실패 시 예외.
    """
    t0 = time.perf_counter()
    data = udp_request(HEALTHCHECK_SEED)
    key_hex = parse_key_response(data)
    ms = (time.perf_counter() - t0) * 1000.0
    return key_hex, ms


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

    # 1) output 준비
    csv_path = ensure_output()
    print(f"[STEP] Output CSV: {csv_path}")

    # 2) 헬스체크
    print("[STEP] Healthcheck (UDP ping)...")
    try:
        key_hex, ms = healthcheck()
        print(f"[OK ] Healthcheck seed={HEALTHCHECK_SEED} key={key_hex} ({ms:.2f} ms)")
    except Exception as e:
        print(f"[FAIL] Healthcheck failed: {e}")
        print("→ 서버(Dll_Server.exe)가 실행 중인지, IP/PORT가 맞는지, 방화벽/네트워크를 확인하세요.")
        return

    # 3) 테스트 실행 + 저장
    ok = 0
    fail = 0
    latencies = []

    print("[STEP] Running tests...")
    for i in range(1, TEST_COUNT + 1):
        seed = generate_seed_hex()

        t0 = time.perf_counter()
        try:
            data = udp_request(seed)
            key_hex = parse_key_response(data)
            latency_ms = (time.perf_counter() - t0) * 1000.0

            # 저장
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(csv_path, "a", encoding="utf-8") as f:
                f.write(f"{ts},{seed},{key_hex},{latency_ms:.3f}\n")

            ok += 1
            latencies.append(latency_ms)

        except Exception as e:
            fail += 1
            print(f"[FAIL] {i}/{TEST_COUNT} seed={seed} reason={e}")

        if (i % PROGRESS_EVERY == 0) or (i == TEST_COUNT):
            if latencies:
                p50 = statistics.median(latencies)
                print(f"[INFO] {i}/{TEST_COUNT} ok={ok} fail={fail} p50={p50:.2f} ms")
            else:
                print(f"[INFO] {i}/{TEST_COUNT} ok={ok} fail={fail}")

        if SLEEP_BETWEEN > 0:
            time.sleep(SLEEP_BETWEEN)

    # 4) 결과 요약
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
