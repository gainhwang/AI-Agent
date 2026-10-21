import unittest
from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from insurance_compare.upload_web import app


def text_pdf(text):
    """외부 PDF 파일 없이 텍스트를 추출할 수 있는 작은 PDF를 만든다."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): writer._add_object(font),
        }),
    })
    contents = DecodedStreamObject()
    contents.set_data(
        f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    )
    page[NameObject("/Contents")] = writer._add_object(contents)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class UploadWebTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_frontend_assets_load(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn('/static/styles.css', page.text)
        self.assertIn('/static/app.js', page.text)

        for path in ("/static/styles.css", "/static/app.js"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_missing_evidence_is_unclear(self):
        pdf = text_pdf("No policy clauses here")
        response = self.client.post(
            "/compare-upload",
            data={"topic": "therapy"},
            files={
                "first": ("first.pdf", pdf, "application/pdf"),
                "second": ("second.pdf", pdf, "application/pdf"),
            },
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["comparison_status"], "unclear")
        self.assertEqual(result["left"]["status"], "unclear")
        self.assertEqual(result["right"]["status"], "unclear")
        self.assertEqual(result["left"]["evidence"], [])
        self.assertEqual(result["right"]["evidence"], [])

    def test_invalid_pdf_is_rejected(self):
        pdf = text_pdf("No policy clauses here")
        response = self.client.post(
            "/compare-upload",
            data={"topic": "therapy"},
            files={
                "first": ("first.pdf", b"not a pdf", "application/pdf"),
                "second": ("second.pdf", pdf, "application/pdf"),
            },
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
