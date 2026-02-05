import socket
import argparse
import binascii
import time


def is_printable_ascii(b: bytes) -> bool:
    # 서버가 실패 시 "Key generation failed" 같은 문자열을 보낼 수 있음
    try:
        s = b.decode("ascii")
        return all(32 <= ord(ch) <= 126 or ch in "\r\n\t" for ch in s)
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Test UDP SeedKey PC Server (same PC).")
    parser.add_argument("--ip", default="127.0.0.1", help="Server IP (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5005, help="Server UDP port (default: 5005)")
    parser.add_argument("--seed", default="0102030405060708",
                        help="Seed hex string to send (default: 0102030405060708)")
    parser.add_argument("--timeout", type=float, default=5.0, help="Socket timeout seconds (default: 5)")
    parser.add_argument("--repeat", type=int, default=1, help="How many times to try (default: 1)")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between repeats (default: 0.5)")
    args = parser.parse_args()

    seed_str = args.seed.strip()

    # 서버(C 코드)는 "hex 문자열"을 받아서 bytes로 바꾸는 구조라서
    # 여기서는 문자열 그대로 UDP로 전송합니다.
    # 예) "0102030405060708" 또는 "01 02 03 04 05 06 07 08"
    payload = seed_str.encode("ascii")

    print(f"[INFO] Target: {args.ip}:{args.port}")
    print(f"[INFO] Sending seed string: '{seed_str}' (len={len(payload)})")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(args.timeout)

        for i in range(args.repeat):
            try:
                t0 = time.time()
                sock.sendto(payload, (args.ip, args.port))
                data, addr = sock.recvfrom(2048)
                dt_ms = (time.time() - t0) * 1000.0

                print(f"\n[SUCCESS] Reply from {addr} in {dt_ms:.1f} ms")
                print(f"  raw bytes len={len(data)}")

                # 서버가 key를 바이너리로 보내면 printable이 아닐 가능성이 큼
                if is_printable_ascii(data):
                    print("  as ASCII:", data.decode("ascii", errors="replace"))
                else:
                    print("  as HEX :", binascii.hexlify(data).decode("ascii").upper())
                    # 보통 key 길이가 8이면 8바이트가 기대됨
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
