import re
import sys
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_PAGES = 500


def load_pdf(filename, content):
    name = re.split(r"[\\/]", str(filename))[-1]

    if not name.lower().endswith(".pdf"):
        raise ValueError("PDF 파일만 사용할 수 있습니다.")

    if not content:
        raise ValueError(f"{name}: 파일이 비어 있습니다.")

    if len(content) > MAX_PDF_BYTES:
        raise ValueError(f"{name}: 파일 크기는 25MB 이하여야 합니다.")

    if not content.startswith(b"%PDF-"):
        raise ValueError(f"{name}: PDF 형식이 아닙니다.")

    try:
        reader = PdfReader(BytesIO(content))

        if reader.is_encrypted:
            raise ValueError(f"{name}: 암호화된 PDF는 사용할 수 없습니다.")

        page_count = len(reader.pages)
        if not 1 <= page_count <= MAX_PAGES:
            raise ValueError(f"{name}: PDF는 1~500쪽이어야 합니다.")

        pages = [
            {
                "page": number,
                "text": (page.extract_text() or "").strip(),
            }
            for number, page in enumerate(reader.pages, start=1)
        ]
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"{name}: PDF를 읽지 못했습니다.") from exc

    text_page_count = sum(bool(page["text"]) for page in pages)

    if text_page_count == 0:
        raise ValueError(
            f"{name}: 추출 가능한 텍스트가 없습니다. OCR이 필요합니다."
        )

    return {
        "file": name,
        "page_count": page_count,
        "text_page_count": text_page_count,
        "pages": pages,
    }


def main():
    if len(sys.argv) != 3:
        raise SystemExit(
            "사용법: python -m insurance_compare.pdf_input "
            "첫번째.pdf 두번째.pdf"
        )

    for filename in sys.argv[1:]:
        path = Path(filename)
        document = load_pdf(path.name, path.read_bytes())

        print(
            f"{document['file']}: "
            f"전체 {document['page_count']}쪽, "
            f"텍스트 {document['text_page_count']}쪽"
        )


if __name__ == "__main__":
    main()