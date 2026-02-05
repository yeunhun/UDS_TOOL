import sys
import os
import time
import logging
import subprocess
import select

import RPi.GPIO as GPIO

# Ensure we can import ./drivers/*
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler("uds_debug.log", mode='w'), logging.StreamHandler()],
    force=True
)

from drivers import oled_display, config_loader, uds_client, transfer_file  # noqa: E402


class UDSApp:
    def __init__(self):
        self.config = None
        self.oled = None
        self.uds = None
        self.usb = None

        self.initialized_once = False
        self._btn_prev = {}

        self.initialize_dependencies()

    def check_can0_present(self):
        result = subprocess.run("ip link show can0", shell=True, stdout=subprocess.PIPE)
        return "can0" in result.stdout.decode()

    def bringup_can_interface(self):
        try:
            subprocess.run(["sudo", "ip", "link", "set", "can0", "down"], check=True)
            subprocess.run(
                [
                    "sudo", "ip", "link", "set", "can0", "up",
                    "type", "can",
                    "bitrate", str(self.bitrate),
                    "dbitrate", str(self.dbitrate),
                    "restart-ms", str(self.restart_ms),
                    "fd", "on",
                ],
                check=True
            )
        except subprocess.CalledProcessError as e:
            logging.error(f"CAN bringup failed: {e}")

    def _normalize_display_config(self, display_cfg):
        cfg = dict(display_cfg)
        if "bus" not in cfg and "i2c_bus" in cfg:
            cfg["bus"] = cfg["i2c_bus"]
        if "address" not in cfg and "i2c_address" in cfg:
            cfg["address"] = cfg["i2c_address"]
        return cfg

    def _setup_buttons(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        self.btn_map = self.config.get("gpio", {}).get("buttons", {})
        self.BTN_FIRST = self.btn_map.get("first")
        self.BTN_SECOND = self.btn_map.get("second")
        self.BTN_ENTER = self.btn_map.get("enter")
        self.BTN_POWER = self.btn_map.get("power")

        for pin in (self.BTN_FIRST, self.BTN_SECOND, self.BTN_ENTER, self.BTN_POWER):
            if isinstance(pin, int):
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                self._btn_prev[pin] = 1

    def _btn_edge_pressed(self, pin):
        cur = GPIO.input(pin)
        prev = self._btn_prev.get(pin, 1)
        self._btn_prev[pin] = cur
        return prev == 1 and cur == 0

    def initialize_dependencies(self):
        GPIO.cleanup()

        self.config = config_loader.load_config("config.json")
        can_cfg = self.config.get("uds", {}).get("can", {})

        self.bitrate = can_cfg.get("bitrate", 500000)
        self.dbitrate = can_cfg.get("dbitrate", 1000000)
        self.restart_ms = can_cfg.get("restart_ms", 1000)

        display_cfg = self._normalize_display_config(self.config.get("display", {}))
        self.oled = oled_display.OLEDDisplay(display_cfg)

        self._setup_buttons()

        bringup_enabled = can_cfg.get("bringup_on_startup", True)
        if bringup_enabled:
            self.bringup_can_interface()

        if bringup_enabled:
            timeout_seconds = 60
            start_time = time.time()

            while time.time() - start_time < timeout_seconds:
                try:
                    temp_uds = uds_client.UDSClient(self.config)
                    ok = temp_uds.try_basic_communication()

                    if ok:
                        break
                    else:
                        if self.oled:
                            self.oled.display_centered_text("Waiting for ECU...")
                        time.sleep(2)

                except Exception as e:
                    logging.error(f"ECU ready check failed: {e}", exc_info=True)
                    if self.oled:
                        self.oled.display_centered_text("Waiting for ECU...")
                    time.sleep(2)
            else:
                if self.oled:
                    self.oled.display_centered_text("ECU Timeout")
                raise SystemExit("Initialization failed: ECU not responding.")

        self.uds = uds_client.UDSClient(self.config)
        self.usb = transfer_file.USBTransfer(self.oled)

    def main_menu(self):
        selected_option = None
        menu_refresh = True

        def show_menu():
            print("\nSelect an option:")
            print("1. Read ECU Info")
            print("2. Run Test Cases")
            print("3. Reboot")
            print("Select NO.& Enter>")   # ✅ 추가된 한 줄

            if self.oled:
                self.oled.display_centered_text(
                    "1. ECU Info\n"
                    "2. Run Test\n"
                    "3. Reboot\n"
                    "Select NO.& Enter>"   # ✅ 추가된 한 줄
                )

        while True:
            if menu_refresh:
                show_menu()
                menu_refresh = False

            if self.BTN_POWER and self._btn_edge_pressed(self.BTN_POWER):
                if self.oled:
                    self.oled.display_centered_text("Rebooting...")
                time.sleep(0.5)
                os.system("sudo reboot")

            if self.BTN_FIRST and self._btn_edge_pressed(self.BTN_FIRST):
                selected_option = "1"
                if self.oled:
                    self.oled.display_centered_text("Selected: 1")

            if self.BTN_SECOND and self._btn_edge_pressed(self.BTN_SECOND):
                selected_option = "2"
                if self.oled:
                    self.oled.display_centered_text("Selected: 2")

            if self.BTN_ENTER and self._btn_edge_pressed(self.BTN_ENTER):
                if selected_option == "1":
                    if self.oled:
                        self.oled.display_centered_text("Read ECU Info")
                    self.uds.get_ecu_information(self.oled)
                    menu_refresh = True
                    selected_option = None

                elif selected_option == "2":
                    if self.oled:
                        self.oled.display_centered_text("Run Test Cases")
                    self.uds.run_testcase(self.oled)
                    menu_refresh = True
                    selected_option = None

            rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
            if rlist:
                cmd = sys.stdin.readline().strip()
                if cmd == "1":
                    self.uds.get_ecu_information(self.oled)
                    menu_refresh = True
                elif cmd == "2":
                    self.uds.run_testcase(self.oled)
                    menu_refresh = True
                elif cmd == "3":
                    if self.oled:
                        self.oled.display_centered_text("Rebooting...")
                    time.sleep(0.5)
                    os.system("sudo reboot")

            time.sleep(0.01)


def main():
    app = UDSApp()
    app.main_menu()


if __name__ == "__main__":
    main()
