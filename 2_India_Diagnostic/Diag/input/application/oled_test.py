#!/usr/bin/env python3
# oled_buttons_test.py
# Raspberry Pi Zero 2 W: SSD1306 I2C OLED + 4 Buttons test (config.json-driven)

import os
import sys
import time
import json
import signal
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import RPi.GPIO as GPIO

# -----------------------------
# Config models
# -----------------------------
@dataclass
class DisplayConfig:
    width: int
    height: int
    i2c_bus: int
    i2c_address: int
    font_path: str
    font_size: int

@dataclass
class GPIOButtonsConfig:
    first: int
    second: int
    enter: int
    power: int

@dataclass
class AppConfig:
    display: DisplayConfig
    buttons: GPIOButtonsConfig

# -----------------------------
# Helpers: load config.json
# -----------------------------
def load_config(path: str) -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # display
    d = raw.get("display", {})
    width = int(d.get("width", 128))
    height = int(d.get("height", 64))
    i2c_bus = int(d.get("i2c_bus", 1))
    i2c_address_str = str(d.get("i2c_address", "0x3C"))
    i2c_address = int(i2c_address_str, 16) if i2c_address_str.lower().startswith("0x") else int(i2c_address_str)
    font_path = str(d.get("font_path", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    font_size = int(d.get("font_size", 10))

    display = DisplayConfig(
        width=width,
        height=height,
        i2c_bus=i2c_bus,
        i2c_address=i2c_address,
        font_path=font_path,
        font_size=font_size,
    )

    # buttons
    b = raw.get("gpio", {}).get("buttons", {})
    buttons = GPIOButtonsConfig(
        first=int(b.get("first")),
        second=int(b.get("second")),
        enter=int(b.get("enter")),
        power=int(b.get("power")),
    )

    return AppConfig(display=display, buttons=buttons)

# -----------------------------
# GPIO mapping helper (BCM -> Physical pin)
# -----------------------------
BCM_TO_PHYS = {
    2: 3,   # SDA1
    3: 5,   # SCL1
    12: 32,
    16: 36,
    20: 38,
    21: 40,
}

def bcm_to_physical(bcm: int) -> str:
    return str(BCM_TO_PHYS.get(bcm, "unknown"))

# -----------------------------
# OLED backends (auto select)
# 1) luma.oled (recommended)
# 2) adafruit_ssd1306 (fallback)
# -----------------------------
class OLEDBase:
    def clear(self) -> None:
        raise NotImplementedError

    def show_text(self, lines, invert: bool = False) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass

class OLEDLuma(OLEDBase):
    def __init__(self, disp_cfg: DisplayConfig):
        from luma.core.interface.serial import i2c
        from luma.oled.device import ssd1306
        from PIL import Image, ImageDraw, ImageFont

        self.Image = Image
        self.ImageDraw = ImageDraw
        self.ImageFont = ImageFont

        serial = i2c(port=disp_cfg.i2c_bus, address=disp_cfg.i2c_address)
        self.device = ssd1306(serial, width=disp_cfg.width, height=disp_cfg.height)

        self.font = self._load_font(disp_cfg.font_path, disp_cfg.font_size)

    def _load_font(self, path: str, size: int):
        try:
            return self.ImageFont.truetype(path, size)
        except Exception:
            # fallback to default
            return self.ImageFont.load_default()

    def clear(self) -> None:
        self.device.clear()

    def show_text(self, lines, invert: bool = False) -> None:
        w = self.device.width
        h = self.device.height
        img = self.Image.new("1", (w, h), color=1 if invert else 0)
        draw = self.ImageDraw.Draw(img)

        y = 0
        for line in lines:
            draw.text((0, y), line, font=self.font, fill=0 if invert else 1)
            y += (self.font.size + 2)

        self.device.display(img)

class OLEDAdafruit(OLEDBase):
    def __init__(self, disp_cfg: DisplayConfig):
        import board
        import busio
        import adafruit_ssd1306
        from PIL import Image, ImageDraw, ImageFont

        self.Image = Image
        self.ImageDraw = ImageDraw
        self.ImageFont = ImageFont

        # Pi uses I2C1 on pins 3/5
        i2c = busio.I2C(board.SCL, board.SDA)
        self.oled = adafruit_ssd1306.SSD1306_I2C(
            disp_cfg.width, disp_cfg.height, i2c, addr=disp_cfg.i2c_address
        )
        self.oled.fill(0)
        self.oled.show()

        self.font = self._load_font(disp_cfg.font_path, disp_cfg.font_size)

    def _load_font(self, path: str, size: int):
        try:
            return self.ImageFont.truetype(path, size)
        except Exception:
            return self.ImageFont.load_default()

    def clear(self) -> None:
        self.oled.fill(0)
        self.oled.show()

    def show_text(self, lines, invert: bool = False) -> None:
        w = self.oled.width
        h = self.oled.height
        img = self.Image.new("1", (w, h))
        draw = self.ImageDraw.Draw(img)

        if invert:
            draw.rectangle((0, 0, w, h), outline=1, fill=1)

        y = 0
        for line in lines:
            draw.text((0, y), line, font=self.font, fill=0 if invert else 1)
            y += (self.font.size + 2)

        self.oled.image(img)
        self.oled.show()

def init_oled(disp_cfg: DisplayConfig) -> OLEDBase:
    # try luma first
    try:
        return OLEDLuma(disp_cfg)
    except Exception as e_luma:
        # fallback to adafruit
        try:
            return OLEDAdafruit(disp_cfg)
        except Exception as e_ada:
            raise RuntimeError(
                "OLED init failed.\n"
                f"- luma error: {e_luma}\n"
                f"- adafruit error: {e_ada}\n"
                "Install one of:\n"
                "  pip3 install luma.oled pillow\n"
                "or\n"
                "  pip3 install adafruit-circuitpython-ssd1306 adafruit-blinka pillow"
            )

# -----------------------------
# Main test app
# -----------------------------
BUTTON_NAMES = ["first", "second", "enter", "power"]

class ButtonOLEDTest:
    def __init__(self, config_path: str = "config.json"):
        self.cfg = load_config(config_path)
        self.oled = init_oled(self.cfg.display)

        # GPIO setup: Active-Low buttons (pressed => LOW)
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        self.btn_pins: Dict[str, int] = {
            "first": self.cfg.buttons.first,
            "second": self.cfg.buttons.second,
            "enter": self.cfg.buttons.enter,
            "power": self.cfg.buttons.power,
        }

        for name, pin in self.btn_pins.items():
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        self.counts = {k: 0 for k in BUTTON_NAMES}
        self.last_press: Optional[Tuple[str, float]] = None

        self._running = True

        # Debounce state
        self._last_state = {k: 1 for k in BUTTON_NAMES}
        self._last_change_time = {k: 0.0 for k in BUTTON_NAMES}
        self.debounce_s = 0.05

        # Power long-press to quit
        self.power_hold_start: Optional[float] = None
        self.power_hold_to_exit_s = 2.0

    def stop(self, *_):
        self._running = False

    def _read_button(self, name: str) -> int:
        # returns 0 if pressed, 1 if released
        return GPIO.input(self.btn_pins[name])

    def _poll_buttons(self):
        now = time.time()

        for name in BUTTON_NAMES:
            state = self._read_button(name)  # 0 pressed, 1 released
            if state != self._last_state[name]:
                self._last_change_time[name] = now
                self._last_state[name] = state

            # stable change?
            if (now - self._last_change_time[name]) >= self.debounce_s:
                # detect press edge (released->pressed)
                if state == 0 and self._last_state[name] == 0:
                    # We only count once per press: use hold logic
                    pass

        # Use a simple edge detector with internal latch:
        # We’ll track "was pressed" and count on transition 1->0 only.
        # To keep code small, do separate state.
        # (re-init here if missing)
        if not hasattr(self, "_edge_prev"):
            self._edge_prev = {k: 1 for k in BUTTON_NAMES}

        for name in BUTTON_NAMES:
            cur = self._read_button(name)
            prev = self._edge_prev[name]

            if prev == 1 and cur == 0:  # falling edge => press
                self.counts[name] += 1
                self.last_press = (name, now)

            self._edge_prev[name] = cur

        # Power long press to exit
        power_state = self._read_button("power")
        if power_state == 0:
            if self.power_hold_start is None:
                self.power_hold_start = now
            elif (now - self.power_hold_start) >= self.power_hold_to_exit_s:
                self._running = False
        else:
            self.power_hold_start = None

    def _build_screen_lines(self):
        d = self.cfg.display

        lines = []
        lines.append("OLED+Buttons TEST")
        lines.append(f"I2C{d.i2c_bus} addr=0x{d.i2c_address:02X}")
        lines.append(f"SDA GPIO2(P{bcm_to_physical(2)}), SCL GPIO3(P{bcm_to_physical(3)})")

        # show pins
        lines.append(f"F:{self.btn_pins['first']}(P{bcm_to_physical(self.btn_pins['first'])}) "
                     f"S:{self.btn_pins['second']}(P{bcm_to_physical(self.btn_pins['second'])})")
        lines.append(f"E:{self.btn_pins['enter']}(P{bcm_to_physical(self.btn_pins['enter'])}) "
                     f"PWR:{self.btn_pins['power']}(P{bcm_to_physical(self.btn_pins['power'])})")

        # states
        st = {k: ("DOWN" if self._read_button(k) == 0 else "UP") for k in BUTTON_NAMES}
        lines.append(f"State F:{st['first']} S:{st['second']}")
        lines.append(f"      E:{st['enter']} P:{st['power']}")

        # counts + last press
        lp = "-" if not self.last_press else f"{self.last_press[0]} ({time.time()-self.last_press[1]:.1f}s)"
        lines.append(f"Cnt F{self.counts['first']} S{self.counts['second']}")
        lines.append(f"    E{self.counts['enter']} P{self.counts['power']}")
        lines.append(f"Last: {lp}")

        if self.power_hold_start is not None:
            held = time.time() - self.power_hold_start
            remain = max(0.0, self.power_hold_to_exit_s - held)
            lines.append(f"Hold PWR exit: {remain:.1f}s")
        else:
            lines.append("Hold PWR 2s: exit")

        # fit to screen height roughly (font-size dependent)
        # Keep only first 8~10 lines for 64px; user config font_size=9 is okay.
        return lines[:10]

    def run(self):
        # Splash
        self.oled.clear()
        self.oled.show_text(
            [
                "Starting...",
                f"{self.cfg.display.width}x{self.cfg.display.height}",
                f"addr=0x{self.cfg.display.i2c_address:02X}",
            ]
        )
        time.sleep(1.0)

        # main loop
        try:
            while self._running:
                self._poll_buttons()
                lines = self._build_screen_lines()
                self.oled.show_text(lines)
                time.sleep(0.05)
        finally:
            self.oled.clear()
            self.oled.show_text(["Bye!"], invert=False)
            time.sleep(0.5)
            self.oled.clear()
            GPIO.cleanup()

def main():
    config_path = "config.json"
    if len(sys.argv) >= 2:
        config_path = sys.argv[1]

    app = ButtonOLEDTest(config_path=config_path)

    # Ctrl+C handling
    signal.signal(signal.SIGINT, app.stop)
    signal.signal(signal.SIGTERM, app.stop)

    app.run()

if __name__ == "__main__":
    main()
