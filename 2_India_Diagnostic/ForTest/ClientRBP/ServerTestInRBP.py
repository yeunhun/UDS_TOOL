#!/usr/bin/env python3
"""
Seed → Key UDP Test Client (Raspberry Pi Zero 2W)

▶ 설정은 이 파일 상단의 CONFIG 섹션만 수정하세요.
"""

# =====================================================
# CONFIGURATION (여기만 수정하면 됩니다)
# =====================================================
SERVER_IP      = "192.168.0.29"   # Windows 키생성 서버 IP
SERVER_PORT    = 5005             # UDP 포트
TEST_COUNT     = 200              # 시험 횟수 (--n 200 과 동일)
UDP_TIMEOUT    = 2.0              # 응답 타임아웃 (초)
SLEEP_BETWEEN  = 0.0              # 각 요청 사이 대기 시간 (초)
FIXED_SEED     = None             # None = 랜덤 시드
# FIXED_SEED   = "0123456789ABCDEF"  # 같은 시드로만 시험할 경우
# =====================================================


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


def send_seed_and_get_latency(seed_hex: str) -> float:
    """
    UDP로 seed 전송 후 응답 수신
    반환값: 응답 시간(ms)
    """
    message = (seed_hex + "\n").encode("ascii")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(UDP_TIMEOUT)

    t0 = time.perf_counter()
    try:
        sock.sendto(message, (SERVER_IP, SERVER_PORT))
        data, _ = sock.recvfrom(1024)
    finally:
        sock.close()

    latency_ms = (time.perf_counter() - t0) * 1000.0

    # 텍스트 에러 응답 감지
    try:
        txt = data.decode("ascii")
        if "fail" in txt.lower() or "invalid" in txt.lower():
            raise RuntimeError(txt.strip())
    except UnicodeDecodeError:
        pass  # 정상적인 바이너리 키

    if len(data) == 0:
        raise RuntimeError("Empty response")

    return latency_ms


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

    ok = 0
    fail = 0
    latencies = []

    for i in range(1, TEST_COUNT + 1):
        seed = generate_seed_hex()
        try:
            latency = send_seed_and_get_latency(seed)
            latencies.append(latency)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"[FAIL] {i}/{TEST_COUNT} seed={seed} reason={e}")

        if i % 20 == 0 or i == TEST_COUNT:
            if latencies:
                p50 = statistics.median(latencies)
                print(f"[INFO] {i}/{TEST_COUNT} ok={ok} fail={fail} p50={p50:.2f} ms")
            else:
                print(f"[INFO] {i}/{TEST_COUNT} ok={ok} fail={fail}")

        if SLEEP_BETWEEN > 0:
            time.sleep(SLEEP_BETWEEN)

    print("\n=============== RESULT =================")
    print(f"Total tests : {TEST_COUNT}")
    print(f"Success     : {ok}")
    print(f"Fail        : {fail}")

    if latencies:
        latencies.sort()

        def pct(p):
            idx = int((p / 100.0) * (len(latencies) - 1))
            return latencies[idx]

        print(f"Latency(ms) : "
              f"p50={pct(50):.2f}, "
              f"p90={pct(90):.2f}, "
              f"p99={pct(99):.2f}, "
              f"max={max(latencies):.2f}")
    else:
        print("No successful responses.")

    print("========================================")


if __name__ == "__main__":
    main()
