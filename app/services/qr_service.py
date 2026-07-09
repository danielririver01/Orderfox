"""
QRService — QR code generation for menus and tables.
Shared by web routes (dashboard_bp, tables_bp).
"""
import qrcode
from io import BytesIO
from PIL import Image, ImageFilter


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
    def generate_table_qr(menu_url, apply_blur=False, blur_radius=8):
        """
        Generate a QR code image for a table's menu URL.

        If apply_blur is True, applies GaussianBlur (for upselling UX).
        Returns BytesIO buffer with PNG data.
        """
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(menu_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white").convert('RGB')

        if apply_blur:
            img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        buffer = BytesIO()
        img.save(buffer, 'PNG')
        buffer.seek(0)
        return buffer
