#!/usr/bin/env python3
import time
from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306  # 만약 sh1106 모듈이면 sh1106로 바꾸세요


BUS = 1
ADDR = 0x3C
TEXT = "MOBASE ASEC"

SLEEP_SEC = 0.03   # 숫자가 작을수록 더 빠름 (0.02~0.05 추천)
PAD = 2            # 좌우 가장자리 여백

def text_size(draw, text, font):
    # Pillow 호환
    if hasattr(draw, "textbbox"):
        x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
        return x1 - x0, y1 - y0
    if hasattr(font, "getbbox"):
        x0, y0, x1, y1 = font.getbbox(text)
        return x1 - x0, y1 - y0
    return draw.textsize(text, font=font)

def main():
    serial = i2c(port=BUS, address=ADDR)
    device = ssd1306(serial)

    W, H = device.width, device.height
    font = ImageFont.load_default()

    # 텍스트 폭 측정용 임시 캔버스
    tmp = Image.new("1", (W, H))
    tmp_draw = ImageDraw.Draw(tmp)
    tw, th = text_size(tmp_draw, TEXT, font)

    # 세로 중앙 정렬
    y = (H - th) // 2

    # 좌우 이동 범위
    left_x = PAD
    right_x = max(PAD, W - tw - PAD)

    x = left_x
    dx = 1  # 이동 방향 (+1 오른쪽, -1 왼쪽)

    while True:
        img = Image.new("1", (W, H), 0)
        draw = ImageDraw.Draw(img)

        draw.text((x, y), TEXT, font=font, fill=255)
        device.display(img)

        x += dx
        if x >= right_x:
            x = right_x
            dx = -1
        elif x <= left_x:
            x = left_x
            dx = 1

        time.sleep(SLEEP_SEC)

if __name__ == "__main__":
    main()
