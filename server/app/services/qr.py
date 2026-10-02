"""Генерация QR-кодов. Форматы: WMS:ITEM:{id}, WMS:BOX:{id}, WMS:LOC:{id}."""
import io

import qrcode


def make_qr_data(kind: str, obj_id: int) -> str:
    return f"WMS:{kind}:{obj_id}"


def qr_png_bytes(data: str, box_size: int = 8, caption: str = "") -> bytes:
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=box_size, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    if caption:
        from PIL import Image, ImageDraw, ImageFont
        w, h = img.size
        canvas = Image.new("RGB", (w, h + 30), "white")
        canvas.paste(img.convert("RGB"), (0, 0))
        d = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        d.text((w // 2, h + 15), caption, fill="black", anchor="mm", font=font)
        img = canvas
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
