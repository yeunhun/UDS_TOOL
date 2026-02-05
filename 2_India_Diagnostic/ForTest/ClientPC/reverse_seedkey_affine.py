import socket
import argparse
import json
import time
import random
from typing import Dict, Any, List, Tuple, Optional

# =========================
# 기본 Target
# =========================
DEFAULT_SERVER_IP = "192.168.0.29"
DEFAULT_SERVER_PORT = 5005
DEFAULT_BIND_TO_LOCAL_IP = True
# =========================


def bytes_to_u64_le(b: bytes) -> int:
    return int.from_bytes(b, byteorder="little", signed=False)


def u64_to_bytes_le(x: int) -> bytes:
    return x.to_bytes(8, byteorder="little", signed=False)


def is_printable_ascii(b: bytes) -> bool:
    try:
        s = b.decode("ascii")
        return all(32 <= ord(ch) <= 126 or ch in "\r\n\t" for ch in s)
    except Exception:
        return False


def udp_query_key(ip: str, port: int, seed8: bytes, timeout: float, bind_local: bool) -> bytes:
    """
    서버(C)는 ASCII hex 문자열을 받아서 파싱하므로 seed를 ASCII hex로 전송.
    성공 시 8바이트 key(binary) 반환.
    """
    if len(seed8) != 8:
        raise ValueError("seed must be 8 bytes")

    payload = seed8.hex().upper().encode("ascii")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        if bind_local:
            # 같은 PC에서 loopback 대신 LAN IP 경로를 확실히 타고 싶을 때 유용
            sock.bind((ip, 0))

        sock.sendto(payload, (ip, port))
        data, _ = sock.recvfrom(4096)

    if is_printable_ascii(data):
        raise RuntimeError(f"Server returned ASCII error: {data.decode('ascii', errors='replace')}")

    if len(data) != 8:
        raise RuntimeError(f"Expected 8-byte key, got {len(data)} bytes: {data.hex().upper()}")

    return data


def learn_affine_columns(ip: str, port: int, f0: int, bind_local: bool, timeout: float) -> List[int]:
    """
    아핀이라고 가정하고 column[0..63]을 구함.
    column[i] = f(e_i) XOR f(0)
    """
    cols = []
    for i in range(64):
        seed = 1 << i
        ki = udp_query_key(ip, port, u64_to_bytes_le(seed), timeout, bind_local)
        fi = bytes_to_u64_le(ki)
        cols.append(fi ^ f0)
    return cols


def affine_check_with_counterexample(
    ip: str, port: int, f0: int, bind_local: bool, timeout: float, rounds: int = 30
) -> Tuple[bool, Optional[Dict[str, str]]]:
    """
    g(x)=f(x) XOR f(0)이 선형이면 g(a)^g(b)==g(a^b)
    선형이 아니면 반례(counterexample)를 하나 반환.
    """
    def f_u64(x: int) -> int:
        k = udp_query_key(ip, port, u64_to_bytes_le(x), timeout, bind_local)
        return bytes_to_u64_le(k)

    for _ in range(rounds):
        a = random.getrandbits(64)
        b = random.getrandbits(64)

        ga = f_u64(a) ^ f0
        gb = f_u64(b) ^ f0
        gab = f_u64(a ^ b) ^ f0

        if (ga ^ gb) != gab:
            # 반례 저장
            ce = {
                "a_seed_hex": u64_to_bytes_le(a).hex().upper(),
                "b_seed_hex": u64_to_bytes_le(b).hex().upper(),
                "a_xor_b_seed_hex": u64_to_bytes_le(a ^ b).hex().upper(),
                "g(a)_hex": u64_to_bytes_le(ga).hex().upper(),
                "g(b)_hex": u64_to_bytes_le(gb).hex().upper(),
                "g(a)^g(b)_hex": u64_to_bytes_le(ga ^ gb).hex().upper(),
                "g(a^b)_hex": u64_to_bytes_le(gab).hex().upper(),
            }
            return False, ce

    return True, None


def collect_samples(
    ip: str, port: int, bind_local: bool, timeout: float,
    count: int, mode: str, delay: float
) -> List[Dict[str, str]]:
    """
    비선형일 때 seed/key 샘플을 모아 JSON으로 저장하기 위한 함수
    """
    samples = []
    if mode == "random":
        seeds = [bytes(random.getrandbits(8) for _ in range(8)) for _ in range(count)]
    elif mode == "inc":
        base = bytearray(8)
        seeds = []
        for i in range(count):
            base[-1] = i & 0xFF
            seeds.append(bytes(base))
    elif mode == "flip1":
        base = bytearray(8)
        seeds = []
        for bit in range(min(count, 64)):
            b = bytearray(base)
            b[bit // 8] ^= (1 << (bit % 8))
            seeds.append(bytes(b))
    else:
        raise ValueError("Unknown mode")

    for s in seeds:
        k = udp_query_key(ip, port, s, timeout, bind_local)
        samples.append({
            "seed_hex": s.hex().upper(),
            "key_hex": k.hex().upper(),
        })
        if delay > 0:
            time.sleep(delay)
    return samples


def predict_with_affine(seed8: bytes, f0: int, cols: List[int]) -> bytes:
    """
    (아핀이라고 가정되는 경우) f(x)=f0 XOR XOR_{i where x_i=1}(col[i])
    """
    x = bytes_to_u64_le(seed8)
    y = f0
    for i in range(64):
        if (x >> i) & 1:
            y ^= cols[i]
    return u64_to_bytes_le(y)


def main():
    ap = argparse.ArgumentParser(
        description="Seed->Key reverse helper: if affine -> build model, else -> gracefully report and collect samples."
    )
    ap.add_argument("--ip", default=DEFAULT_SERVER_IP)
    ap.add_argument("--port", type=int, default=DEFAULT_SERVER_PORT)
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--bind", action="store_true", default=DEFAULT_BIND_TO_LOCAL_IP)
    ap.add_argument("--no-bind", action="store_false", dest="bind")

    sub = ap.add_subparsers(dest="cmd", required=True)

    sp_learn = sub.add_parser("learn", help="Try affine model; if not affine, save counterexample + samples (no crash).")
    sp_learn.add_argument("--out", default="seedkey_model.json", help="Output model JSON file (affine case)")
    sp_learn.add_argument("--nonlinear-out", default="nonlinear_samples.json", help="Output sample JSON if non-linear")
    sp_learn.add_argument("--sample-count", type=int, default=40, help="How many samples to collect if non-linear")
    sp_learn.add_argument("--sample-mode", choices=["random", "inc", "flip1"], default="random")
    sp_learn.add_argument("--sample-delay", type=float, default=0.01)

    sp_pred = sub.add_parser("predict", help="Predict using affine model JSON; optionally verify with server.")
    sp_pred.add_argument("--model", default="seedkey_model.json")
    sp_pred.add_argument("--seed", required=True, help="8-byte seed as hex string, e.g. 0102030405060708")
    sp_pred.add_argument("--verify", action="store_true")

    args = ap.parse_args()

    print(f"[INFO] Target: {args.ip}:{args.port} bind={'ON' if args.bind else 'OFF'}")

    if args.cmd == "learn":
        # f(0)
        k0 = udp_query_key(args.ip, args.port, b"\x00" * 8, args.timeout, args.bind)
        f0 = bytes_to_u64_le(k0)
        print(f"[INFO] f(0) = {k0.hex().upper()}")

        ok, ce = affine_check_with_counterexample(args.ip, args.port, f0, args.bind, args.timeout, rounds=30)

        if ok:
            print("[RESULT] ✅ Affine/Linear (GF(2))로 보입니다. 모델을 생성합니다...")
            cols = learn_affine_columns(args.ip, args.port, f0, args.bind, args.timeout)

            model = {
                "ip": args.ip,
                "port": args.port,
                "byteorder": "little",
                "f0_hex": u64_to_bytes_le(f0).hex().upper(),
                "columns_hex": [u64_to_bytes_le(c).hex().upper() for c in cols],
                "note": "Affine GF(2) model: f(x)=f0 XOR XOR(column[i] for each 1-bit in x)",
            }
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(model, f, indent=2)
            print(f"[OK] Model saved: {args.out}")
            return

        # 비선형인 경우: 크래시 대신 “결과+반례+샘플 저장”
        print("[RESULT] ❌ Affine/Linear가 아닙니다 (비선형). 모델 생성은 중단합니다.")
        if ce:
            print("[INFO] Counterexample (반례) 1개를 저장합니다.")
        payload = {
            "ip": args.ip,
            "port": args.port,
            "byteorder": "little",
            "f0_hex": u64_to_bytes_le(f0).hex().upper(),
            "affine_counterexample": ce,
            "samples": collect_samples(
                args.ip, args.port, args.bind, args.timeout,
                count=args.sample_count, mode=args.sample_mode, delay=args.sample_delay
            ),
            "note": "Non-linear suspected. Use these samples for further analysis (byte influence, avalanche, brute candidates, etc.).",
        }
        with open(args.nonlinear_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"[OK] Non-linear samples saved: {args.nonlinear_out}")
        return

    if args.cmd == "predict":
        with open(args.model, "r", encoding="utf-8") as f:
            model = json.load(f)

        seed8 = bytes.fromhex(args.seed)
        f0 = bytes_to_u64_le(bytes.fromhex(model["f0_hex"]))
        cols = [bytes_to_u64_le(bytes.fromhex(h)) for h in model["columns_hex"]]
        pred = predict_with_affine(seed8, f0, cols)
        print(f"[PRED] SEED={seed8.hex().upper()} -> KEY={pred.hex().upper()}")

        if args.verify:
            srv = udp_query_key(args.ip, args.port, seed8, args.timeout, args.bind)
            print(f"[SRV ] SEED={seed8.hex().upper()} -> KEY={srv.hex().upper()}")
            print("[MATCH]" if srv == pred else "[MISMATCH]")
        return


if __name__ == "__main__":
    main()
