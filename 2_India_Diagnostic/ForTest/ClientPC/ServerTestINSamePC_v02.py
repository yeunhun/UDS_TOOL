import socket
import argparse
import binascii
import time

# =========================
# ✅ 여기만 바꾸면 됩니다
# =========================
DEFAULT_SERVER_IP = "192.168.0.29"   # <-- PC의 Wi-Fi/LAN IPv4로 변경
DEFAULT_SERVER_PORT = 5005

# 같은 PC에서 "loopback(127.0.0.1)" 대신 "LAN IP"로 확실히 나가게 하려면 ON 추천
DEFAULT_BIND_TO_LOCAL_IP = True      # True: 출발지 IP를 DEFAULT_SERVER_IP로 고정(bind)
# =========================


def is_printable_ascii(b: bytes) -> bool:
    # 서버가 실패 시 "Key generation failed" 같은 문자열을 보낼 수 있음
    try:
        s = b.decode("ascii")
        return all(32 <= ord(ch) <= 126 or ch in "\r\n\t" for ch in s)
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Test UDP SeedKey PC Server (same PC or LAN).")
    parser.add_argument("--ip", default=DEFAULT_SERVER_IP,
                        help=f"Server IP (default: {DEFAULT_SERVER_IP})")
    parser.add_argument("--port", type=int, default=DEFAULT_SERVER_PORT,
                        help=f"Server UDP port (default: {DEFAULT_SERVER_PORT})")
    parser.add_argument("--seed", default="0102030405060708",
                        help="Seed hex string to send (default: 0102030405060708)")
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="Socket timeout seconds (default: 5.0)")
    parser.add_argument("--repeat", type=int, default=1,
                        help="How many times to try (default: 1)")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Delay between repeats (default: 0.5)")

    # LAN IP로 보내는 걸 확실히 하고 싶을 때(같은 PC에서도) bind를 켜는 옵션
    # 기본값은 DEFAULT_BIND_TO_LOCAL_IP
    parser.add_argument("--bind", action="store_true", default=DEFAULT_BIND_TO_LOCAL_IP,
                        help="Bind client socket to local IP same as --ip (default: ON)")
    parser.add_argument("--no-bind", action="store_false", dest="bind",
                        help="Do not bind client socket (let OS choose)")

    args = parser.parse_args()

    seed_str = args.seed.strip()

    # 서버(C 코드)는 "hex 문자열"을 받아서 bytes로 바꾸는 구조라서
    # 여기서는 문자열 그대로 UDP로 전송합니다.
    payload = seed_str.encode("ascii")

    print(f"[INFO] Target: {args.ip}:{args.port}")
    print(f"[INFO] Sending seed string: '{seed_str}' (len={len(payload)})")
    print(f"[INFO] Client bind: {'ON' if args.bind else 'OFF'}")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(args.timeout)

        # ✅ 같은 PC에서 loopback 대신 LAN IP 경로를 쓰고 싶을 때 유용
        # 출발지 IP를 args.ip로 고정 (포트는 OS가 임의 할당)
        if args.bind:
            try:
                sock.bind((args.ip, 0))
            except OSError as e:
                print(f"[WARN] bind({args.ip}, 0) failed: {e}")
                print("       -> Try --no-bind, or check that the IP is assigned on this PC.")
                return

        for i in range(args.repeat):
            try:
                t0 = time.time()
                sock.sendto(payload, (args.ip, args.port))
                data, addr = sock.recvfrom(2048)
                dt_ms = (time.time() - t0) * 1000.0

                print(f"\n[SUCCESS] Reply from {addr} in {dt_ms:.1f} ms")
                print(f"  raw bytes len={len(data)}")

                if is_printable_ascii(data):
                    print("  as ASCII:", data.decode("ascii", errors="replace"))
                else:
                    print("  as HEX :", binascii.hexlify(data).decode("ascii").upper())
                    print("  bytes  :", " ".join(f"{b:02X}" for b in data))

            except socket.timeout:
                print(f"\n[FAIL] Timeout waiting reply (>{args.timeout}s). "
                      f"Server not running / port blocked / wrong IP/port.")
            except Exception as e:
                print(f"\n[ERROR] {e}")

            if i != args.repeat - 1:
                time.sleep(args.delay)


if __name__ == "__main__":
    main()
