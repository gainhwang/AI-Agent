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


class ComparisonRulesTests(unittest.TestCase):
    def test_all_topics_with_no_evidence_are_unclear(self):
        from insurance_compare.compare_all import compare_all
        document = {"file": "plain.pdf", "pages": [{"page": 1, "text": "No policy clauses here"}]}
        output = compare_all({"left": document, "right": document})
        self.assertEqual(len(output["results"]), 4)
        self.assertTrue(all(item["comparison_status"] == "unclear" for item in output["results"]))

    def test_one_sided_evidence_stays_unclear(self):
        from insurance_compare.generic_compare import compare_documents
        documents = {"left": {"file": "a.pdf"}, "right": {"file": "b.pdf"}}
        candidates = {"left": [{"page": 1, "snippet": "도수치료", "file": "a.pdf"}], "right": []}
        result, _ = compare_documents("therapy", documents, candidates)
        self.assertEqual(result["comparison_status"], "unclear")

    def test_scoped_deductible_does_not_use_outpatient_row(self):
        from insurance_compare.scoped_rules import deductible
        document = {"file": "sample.pdf", "pages": [{"page": 9, "text":
            "자기부담금을 차감하는 담보 표준형 상해입원실손의료비 "
            "입원수술비: 보상대상의료비의 20%에 해당하는 금액 "
            "상해통원(외래) 2만원과 보상대상의료비의 30%중 큰 금액"}]}
        found = deductible(document)
        self.assertIn("20%", found["summary"])
        self.assertNotIn("30%", found["summary"])

    def test_exclusion_requires_injury_exception(self):
        from insurance_compare.scoped_rules import exclusion
        document = {"file": "sample.pdf", "pages": [{"page": 1, "text":
            "(1)상해입원 4.피보험자가 임신,출산,산후기로 입원한 경우. "
            "5.전쟁"}]}
        self.assertIsNone(exclusion(document))


class AllUploadTests(unittest.TestCase):
    def test_one_upload_returns_four_rows(self):
        client = TestClient(app)
        pdf = text_pdf("No policy clauses here")
        response = client.post(
            "/compare-upload",
            data={"topic": "all"},
            files={
                "first": ("first.pdf", pdf, "application/pdf"),
                "second": ("second.pdf", pdf, "application/pdf"),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 4)
        self.assertEqual(response.json()["workflow"]["retrieval"], "mcp_tool")
        self.assertTrue(all(row["comparison_status"] == "unclear"
                            for row in response.json()["results"]))


class PolicyGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_specialists_merge_in_topic_order_and_validate_evidence(self):
        from insurance_compare.generic_evidence import TOPICS
        from insurance_compare.policy_graph import PolicyDeps, build_graph

        class FakeEvidenceClient:
            def __init__(self):
                self.calls = []

            async def retrieve(self, document, topics):
                self.calls.append((document["file"], topics))
                return {topic: [] for topic in topics}

        def unsupported_comparison(topic, documents, candidates):
            return {
                "left_status": "found", "right_status": "found",
                "left_claims": [], "right_claims": [],
                "comparison_status": "same", "comparison": "동일합니다.",
            }, []

        client = FakeEvidenceClient()
        graph = build_graph(PolicyDeps(client, comparer=unsupported_comparison))
        documents = {
            "left": {"file": "a.pdf", "pages": []},
            "right": {"file": "b.pdf", "pages": []},
        }
        result = await graph.ainvoke({
            "documents": documents, "topics": list(TOPICS), "results": []
        })
        self.assertEqual(len(client.calls), 2)
        self.assertEqual([item["key"] for item in result["output"]["results"]], list(TOPICS))
        self.assertTrue(all(
            item["comparison_status"] == "unclear"
            for item in result["output"]["results"]
        ))


if __name__ == "__main__":
    unittest.main()
