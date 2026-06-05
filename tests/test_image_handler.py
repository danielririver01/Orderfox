import io
from app.utils.image_handler import allowed_file


class TestAllowedFile:

    def test_allowed_png(self):
        assert allowed_file('photo.png') is True

    def test_allowed_jpg(self):
        assert allowed_file('photo.jpg') is True
        assert allowed_file('photo.jpeg') is True

    def test_allowed_webp(self):
        assert allowed_file('photo.webp') is True

    def test_rejected_pdf(self):
        assert allowed_file('document.pdf') is False

    def test_rejected_no_extension(self):
        assert allowed_file('photo') is False

    def test_rejected_empty_filename(self):
        assert allowed_file('') is False

    def test_case_insensitive(self):
        assert allowed_file('photo.PNG') is True
        assert allowed_file('photo.JPG') is True

    def test_none_file(self):
        assert allowed_file(None) is False
