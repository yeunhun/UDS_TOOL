import os
import can
import logging
from datetime import datetime
from can.io.asc import ASCWriter


class CANLogger:
    def __init__(self, channel='can0', interface='socketcan', can_fd=True, filters=None, log_dir=None):
        """
        Initializes the CANLogger with the provided CAN interface settings
        and log directory.
        """
        self.channel = channel
        self.interface = interface
        self.can_fd = can_fd
        self.log_dir = log_dir
        self.filters = filters

        self.bus = None
        self.notifier = None
        self.writer = None
        self.file = None
        self.log_path = None
        self.running = False

    def start(self, filename=None):
        """
        Start CAN bus logging with ASCWriter attached to notifier.
        """
        # 이미 실행 중이면 먼저 정리
        if self.running or self.notifier or self.writer:
            self.stop()

        if not self.log_dir:
            raise ValueError("log_dir is not set for CANLogger")

        os.makedirs(self.log_dir, exist_ok=True)

        # 파일명 결정
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"can_log_{timestamp}.asc"

        self.log_path = os.path.join(self.log_dir, filename)

        try:
            # Open log file for writing
            self.file = open(self.log_path, 'w')

            # Create CAN bus interface
            self.bus = can.interface.Bus(
                channel=self.channel,
                bustype=self.interface,
                can_filters=self.filters,
                fd=self.can_fd
            )

            # Attach ASCWriter to bus via Notifier
            self.writer = ASCWriter(self.file)
            self.notifier = can.Notifier(self.bus, [self.writer])

            self.running = True
            logging.info(f"CAN logging started: {self.log_path}")

        except Exception as e:
            logging.error(f"[CANLogger] Failed to start: {e}")
            # start 실패 시 리소스 정리
            self.running = False
            try:
                if self.notifier:
                    self.notifier.stop()
            except Exception:
                pass
            self.notifier = None
            self.writer = None
            try:
                if self.bus:
                    self.bus.shutdown()
            except Exception:
                pass
            self.bus = None
            try:
                if self.file and not self.file.closed:
                    self.file.close()
            except Exception:
                pass
            self.file = None

    def stop(self):
        """
        Stop CAN logging safely (idempotent).
        - 중복 stop 호출되어도 예외 없이 빠져나오도록 함
        - notifier/bus/file 닫는 순서 안정화
        """
        if not self.running and not (self.notifier or self.bus or self.file):
            return

        # 1) Notifier 먼저 stop (writer가 bus에서 더 이상 호출되지 않게)
        try:
            if self.notifier:
                self.notifier.stop()
        except Exception as e:
            logging.debug(f"[CANLogger] notifier.stop() ignored: {e}")
        finally:
            self.notifier = None

        # 2) Writer 정리
        try:
            if self.writer:
                # ASCWriter는 file로 기록하므로 file close가 핵심.
                pass
        except Exception:
            pass
        finally:
            self.writer = None

        # 3) Bus shutdown (SocketcanBus 경고 방지)
        try:
            if self.bus:
                self.bus.shutdown()
        except Exception as e:
            logging.debug(f"[CANLogger] bus.shutdown() ignored: {e}")
        finally:
            self.bus = None

        # 4) File close (이미 닫혔으면 그냥 무시)
        try:
            if self.file and not self.file.closed:
                try:
                    self.file.flush()
                except Exception:
                    pass
                self.file.close()
        except Exception as e:
            logging.debug(f"[CANLogger] file.close() ignored: {e}")
        finally:
            self.file = None

        self.running = False
        logging.info("CAN logging stopped")

    def get_log_path(self):
        """
        uds_client.py에서 report 생성 시 사용.
        """
        return self.log_path
