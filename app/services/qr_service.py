"""
QRService — QR code generation for menus and tables.
Shared by web routes (dashboard_bp, tables_bp).
"""
import qrcode
from io import BytesIO
from PIL import Image, ImageFilter, ImageDraw, ImageFont


class QRService:
    """Static methods for QR generation, shared by dashboard and tables routes."""

    @staticmethod
    def generate_menu_qr(menu_url, error_correction=qrcode.constants.ERROR_CORRECT_L,
                         box_size=10, border=4, fmt='png', quality=95):
        """
        Generate a QR code image for a menu URL.

        Returns (BytesIO_buffer, mime_type).
        Supports fmt='png' or 'jpg'/'jpeg'.
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=error_correction,
            box_size=box_size,
            border=border,
        )
        qr.add_data(menu_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        buf = BytesIO()

        if fmt in ('jpg', 'jpeg'):
            img.save(buf, format='JPEG', quality=quality)
            mime_type = 'image/jpeg'
        else:
            img.save(buf, format='PNG')
            mime_type = 'image/png'

        buf.seek(0)
        return buf, mime_type

    @staticmethod
    def generate_table_qr(menu_url, apply_blur=False, blur_radius=8, label=None):
        """
        Generate a QR code image for a table's menu URL.

        If apply_blur is True, applies GaussianBlur (for upselling UX).
        If label is provided, adds the label text below the QR code.
        Returns BytesIO buffer with PNG data.
        """
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(menu_url)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')

        if apply_blur:
            qr_img = qr_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        if label:
            label_img = QRService._add_label_to_qr(qr_img, label)
            img = label_img
        else:
            img = qr_img

        buffer = BytesIO()
        img.save(buffer, 'PNG')
        buffer.seek(0)
        return buffer

    @staticmethod
    def _add_label_to_qr(qr_img, label):
        """
        Add a text label below the QR code image.
        Creates a new taller image with QR on top and centered label below.
        """
        padding = 20
        label_height = 40

        qr_width, qr_height = qr_img.size
        new_width = qr_width + 2 * padding
        new_height = qr_height + label_height + 2 * padding

        new_img = Image.new('RGB', (new_width, new_height), 'white')
        new_img.paste(qr_img, (padding, padding))

        draw = ImageDraw.Draw(new_img)
        font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
        try:
            font = ImageFont.truetype(font_path, 18)
        except OSError:
            font = ImageFont.load_default()

        text_bbox = draw.textbbox((0, 0), label, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_x = (new_width - text_width) // 2
        text_y = qr_height + padding + (label_height - (text_bbox[3] - text_bbox[1])) // 2

        draw.text((text_x, text_y), label, fill='black', font=font)

        return new_img
