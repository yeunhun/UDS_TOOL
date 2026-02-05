import sys
import datetime as dt

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except Exception as e:
    print("Tkinter import error:", e)
    sys.exit(1)

try:
    import serial
    import serial.tools.list_ports as list_ports
    HAS_SERIAL = True
except Exception:
    HAS_SERIAL = False

# ---------------- UI / 채널 설정 (이 부분만 수정하면 됨) -----------------
APP_TITLE = "Relay & CAN Controller — CH10~CH05"
WINDOW_GEOMETRY = "900x600"

# COM 콤보박스 폭
COMBO_WIDTH = 10

# 채널 이름 + 레지스터 주소
CHANNEL_CONFIG = [
    ("CH10", 0x0009),
    ("CH09", 0x0008),
    ("CH08", 0x0007),
    ("CH07", 0x0006),
    ("CH06", 0x0005),
    ("CH05", 0x0004),
]

# 채널 라벨 표시 형식
CHANNEL_LABEL_TEMPLATE = "{name} (Reg=0x{reg:04X})"

# 채널별 버튼 ON/OFF 이름 설정
CHANNEL_BUTTON_TEXT = {
    "CH10": {"on": "BAT ON",   "off": "BAT OFF"},
    "CH09": {"on": "IGN ON",   "off": "IGN OFF"},
    "CH08": {"on": "GREEN ON", "off": "GREEN OFF"},
    "CH07": {"on": "AMBER ON", "off": "AMBER OFF"},
    "CH06": {"on": "CH06 ON",  "off": "CH06 OFF"},
    "CH05": {"on": "CH05 ON",  "off": "CH05 OFF"},
}

# 버튼/로그 크기
BTN_WIDTH = 10
HEX_ENTRY_WIDTH = 60
LOG_TEXT_HEIGHT = 12

# 강조 회색
BUTTON_ACTIVE_BG = "#A0A0A0"

# ---------------- Modbus 프레임 (채널별 고정 HEX) -----------------
CHANNEL_FRAMES = {
    "CH10": {
        True:  "01 06 00 09 01 00 58 58",
        False: "01 06 00 09 02 00 58 A8",
    },
    "CH09": {
        True:  "01 06 00 08 01 00 09 98",
        False: "01 06 00 08 02 00 09 68",
    },
    "CH08": {
        True:  "01 06 00 07 01 00 39 9B",
        False: "01 06 00 07 02 00 39 6B",
    },
    "CH07": {
        True:  "01 06 00 06 01 00 68 5B",
        False: "01 06 00 06 02 00 68 AB",
    },
    "CH06": {
        True:  "01 06 00 05 01 00 98 5B",
        False: "01 06 00 05 02 00 98 AB",
    },
    "CH05": {
        True:  "01 06 00 04 01 00 C9 9B",
        False: "01 06 00 04 02 00 C9 6B",
    },
}

def ts():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ---------------- Serial -----------------
class SerialManager:
    def __init__(self, port="COM3", baud=9600, bytesize=8, parity='N', stopbits=1, timeout=0.5):
        self.port = port
        self.baud = baud
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self._ser = None
        self.simulate = not HAS_SERIAL

    def configure(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def connect(self):
        if self.simulate:
            return False, f"pyserial 미설치 — 시뮬레이션 모드 ({self.port})"
        try:
            if self._ser and getattr(self._ser, 'is_open', False):
                self._ser.close()
            self._ser = serial.Serial(self.port, self.baud, self.bytesize,
                                      self.parity, self.stopbits, self.timeout)
            return True, f"{self.port} 연결됨"
        except Exception as e:
            self._ser = None
            return False, f"{self.port} 연결 실패: {e}"

    def is_connected(self):
        return self._ser is not None and getattr(self._ser, 'is_open', False)

    def send(self, payload: bytes):
        if self.is_connected():
            try:
                n = self._ser.write(payload)
                self._ser.flush()
                resp = self._ser.read(64)
                return True, f"전송 {n}바이트: {payload.hex(' ')} / 응답: {resp.hex(' ') if resp else '(없음)'}"
            except Exception as e:
                return False, f"전송 실패: {e}"
        else:
            return False, f"(미연결) 전송 시도됨: {payload.hex(' ')}"

# ---------------- Helpers -----------------
def scan_ports():
    if HAS_SERIAL:
        ports = [p.device for p in list_ports.comports()]
        return ports if ports else ["COM1"]
    return ["COM1", "COM2", "COM3"]

# ---------------- App -----------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(WINDOW_GEOMETRY)

        # ----- 로고 관련 -----
        self.logo_orig = None
        self.logo_img = None
        self.logo_label = None

        self._load_logo_image()

        self.serial_mgr = SerialManager()
        self.available_ports = scan_ports()
        self.com_var = tk.StringVar(value=self.available_ports[0])

        self.channels = {}
        self._build_ui()

        self._create_logo_widget()

        # 창 크기 변경 시 자동 조절
        self.bind("<Configure>", self._on_resize)

        # 초기 실행 시 로고 크기 재조정
        self.after(150, self._fix_initial_logo_size)

    def _fix_initial_logo_size(self):
        """초기 실행 시 윈도우 디자인 폭을 기준으로 로고 크기 재조정"""
        try:
            design_w = int(WINDOW_GEOMETRY.split("x")[0])
        except Exception:
            design_w = self.winfo_width() or 900
        self._update_logo_image(design_w)

    # --------- 로고 로드 ---------
    def _load_logo_image(self):
        try:
            self.logo_orig = tk.PhotoImage(file="ASEC_LOGO.png")
        except Exception as e:
            print("로고 이미지 로드 실패:", e)
            self.logo_orig = None

    def _create_logo_widget(self):
        if self.logo_orig is None:
            return
        # 배경을 창 배경색과 동일하게 해서 '투명처럼' 보이게
        self.logo_label = tk.Label(
            self,
            image=self.logo_orig,
            bg=self.cget("bg"),
            borderwidth=0,
            highlightthickness=0,
        )
        self.logo_label.place(relx=1.0, x=-10, y=5, anchor="ne")
        self.logo_img = self.logo_orig
        # 여기서는 크기 조정 안 하고, _fix_initial_logo_size에서 한 번에 처리

    def _update_logo_image(self, window_width):
        if self.logo_orig is None:
            return

        orig_w = self.logo_orig.width()
        if orig_w <= 0:
            return

        # 창 너비의 30%까지 사용, 최대 260px (기존보다 1.5배)
        max_logo_width = max(80, min(int(window_width * 0.30), 260))
        scale = max_logo_width / float(orig_w)

        img = self.logo_orig
        if scale >= 1.0:
            z = max(1, int(round(scale)))
            img = self.logo_orig.zoom(z, z)
        else:
            subs = max(1, int(round(1.0 / scale)))
            img = self.logo_orig.subsample(subs, subs)

        self.logo_img = img
        if self.logo_label is not None:
            self.logo_label.configure(image=self.logo_img)

    def _on_resize(self, event):
        if self.logo_orig is None:
            return
        self._update_logo_image(event.width)
        if self.logo_label is not None:
            self.logo_label.place_configure(relx=1.0, x=-10, y=5, anchor="ne")

    # --------- 기존 UI 코드 ---------
    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="COM Port:").grid(row=0, column=0)
        self.cb_port = ttk.Combobox(top, width=COMBO_WIDTH,
                                    values=self.available_ports,
                                    textvariable=self.com_var, state="readonly")
        self.cb_port.grid(row=0, column=1, padx=5)
        ttk.Button(top, text="연결", command=self.on_connect).grid(row=0, column=2, padx=5)

        grp = ttk.LabelFrame(self, text="Relay Control", padding=10)
        grp.pack(fill="x", padx=10, pady=10)

        ttk.Label(grp, text="채널(Reg)").grid(row=0, column=0, padx=3)
        ttk.Label(grp, text="명령 버튼").grid(row=0, column=1, padx=3)
        ttk.Label(grp, text="전송 HEX").grid(row=0, column=2, padx=3)

        for idx, (ch_name, reg) in enumerate(CHANNEL_CONFIG, start=1):
            label_text = CHANNEL_LABEL_TEMPLATE.format(name=ch_name, reg=reg)
            ttk.Label(grp, text=label_text).grid(row=idx, column=0, sticky="w")

            btn_row = ttk.Frame(grp)
            btn_row.grid(row=idx, column=1, sticky="w")

            state_var = tk.StringVar(value="OFF")
            hex_var = tk.StringVar(value="")

            btn_on = tk.Button(
                btn_row,
                text=CHANNEL_BUTTON_TEXT[ch_name]["on"],
                width=BTN_WIDTH,
                command=lambda n=ch_name: self.send_channel(n, True)
            )

            btn_off = tk.Button(
                btn_row,
                text=CHANNEL_BUTTON_TEXT[ch_name]["off"],
                width=BTN_WIDTH,
                command=lambda n=ch_name: self.send_channel(n, False)
            )

            btn_on.pack(side="left", padx=(0, 6))
            btn_off.pack(side="left")

            entry = ttk.Entry(grp, textvariable=hex_var, width=HEX_ENTRY_WIDTH, state="readonly")
            entry.grid(row=idx, column=2, padx=5, sticky="we")

            self.channels[ch_name] = {
                "reg": reg,
                "btn_on": btn_on,
                "btn_off": btn_off,
                "hex_var": hex_var,
                "state": state_var,
            }

            self.update_button_colors(ch_name)

        grp.columnconfigure(2, weight=1)
        self.set_buttons_enabled(False)

        logf = ttk.LabelFrame(self, text="Log", padding=6)
        logf.pack(fill="both", expand=True, padx=10, pady=10)
        self.log = tk.Text(logf, height=LOG_TEXT_HEIGHT)
        self.log.pack(fill="both", expand=True)

    # ---------------- UI helpers ----------------
    def set_buttons_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for ch in self.channels.values():
            ch["btn_on"].configure(state=state)
            ch["btn_off"].configure(state=state)

    def update_button_colors(self, ch_name):
        info = self.channels[ch_name]
        if info["state"].get() == "ON":
            info["btn_on"].configure(bg=BUTTON_ACTIVE_BG, fg="white", relief="sunken")
            info["btn_off"].configure(bg="SystemButtonFace", fg="black", relief="raised")
        else:
            info["btn_off"].configure(bg=BUTTON_ACTIVE_BG, fg="white", relief="sunken")
            info["btn_on"].configure(bg="SystemButtonFace", fg="black", relief="raised")

    # ---------------- Events ----------------
    def on_connect(self):
        port = self.com_var.get()
        self.serial_mgr.configure(port=port)
        ok, msg = self.serial_mgr.connect()
        self._log(msg)
        self.set_buttons_enabled(ok)
        if ok:
            messagebox.showinfo("COM", msg)

    def send_channel(self, ch_name, turn_on):
        if not self.serial_mgr.is_connected():
            self._log(f"{ch_name}: 미연결 상태")
            return

        frame_hex = CHANNEL_FRAMES[ch_name][turn_on]
        frame = bytes.fromhex(frame_hex)

        info = self.channels[ch_name]
        info["state"].set("ON" if turn_on else "OFF")
        self.update_button_colors(ch_name)
        info["hex_var"].set(frame_hex)

        ok, msg = self.serial_mgr.send(frame)
        self._log(f"{ch_name}: {msg}")

    def _log(self, msg):
        if not msg.endswith("\n"):
            msg += "\n"
        self.log.insert("end", f"[{ts()}] {msg}\n")
        self.log.see("end")


# ------------ main ------------
if __name__ == "__main__":
    app = App()
    app.mainloop()
