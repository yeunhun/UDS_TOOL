import time
import textwrap
from PIL import ImageFont


def _to_int(v, default):
    if v is None:
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        try:
            if s.startswith("0x"):
                return int(s, 16)
            return int(s)
        except Exception:
            return default
    return default


class OLEDDisplay:
    def __init__(self, config):
        self.cfg = config if isinstance(config, dict) else {}

        self.port = _to_int(self.cfg.get("bus", self.cfg.get("port", 1)), 1)
        if self.port == 0:
            self.port = 1

        self.address = _to_int(self.cfg.get("address", 0x3C), 0x3C)
        self.rotate = _to_int(self.cfg.get("rotate", 0), 0)

        self.font_size = _to_int(self.cfg.get("font_size", 12), 12)
        self.font_path = self.cfg.get("font_path")
        self.font = self._load_font()

        self.device = None
        self._canvas = None

        self._init_device()

    def _load_font(self):
        if isinstance(self.font_path, str) and self.font_path:
            try:
                return ImageFont.truetype(self.font_path, self.font_size)
            except Exception:
                pass
        return ImageFont.load_default()

    def _init_device(self):
        try:
            from luma.core.interface.serial import i2c
            from luma.oled.device import ssd1306
            from luma.core.render import canvas

            self._canvas = canvas
            serial = i2c(port=self.port, address=self.address)
            self.device = ssd1306(serial, rotate=self.rotate)

            self.clear()
            time.sleep(0.05)

        except Exception as e:
            self.device = None
            self._canvas = None
            print(f"[OLED] init failed: {type(e).__name__}: {e}")

    def clear(self):
        if not self.device:
            return
        try:
            self.device.clear()
            self.device.show()
        except Exception as e:
            print(f"[OLED] clear failed: {type(e).__name__}: {e}")

    def display_text(self, text, x=0, y=0):
        if not self.device or not self._canvas:
            return
        try:
            with self._canvas(self.device) as draw:
                draw.text((int(x), int(y)), str(text), font=self.font, fill=255)
        except Exception as e:
            print(f"[OLED] display_text failed: {type(e).__name__}: {e}")

    # 🔧 여기만 변경됨: 중앙 정렬 → 좌측 정렬
    def display_centered_text(self, text):
        """
        NOTE:
        - 함수 이름은 그대로 유지 (main4.py 수정 불필요)
        - 실제 동작은 '좌측 정렬'
        """
        if not self.device or not self._canvas:
            return

        try:
            w, h = self.device.size

            raw = str(text).replace("\r\n", "\n").replace("\r", "\n")
            paragraphs = raw.split("\n")

            lines = []
            for p in paragraphs:
                if p.strip() == "":
                    lines.append("")
                else:
                    lines.extend(textwrap.wrap(p, width=20))

            if not lines:
                lines = [""]

            line_h = 10
            y = 0
            x_margin = 2  # 좌측 여백

            with self._canvas(self.device) as draw:
                for line in lines:
                    draw.text((x_margin, y), line, font=self.font, fill=255)
                    y += line_h

        except Exception as e:
            print(f"[OLED] display_left_text failed: {type(e).__name__}: {e}")
