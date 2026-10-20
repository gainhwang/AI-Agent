from pathlib import Path

from .pdf_reader import extract_pages


POLICY_DIR = Path("data/policies")
REGULAR_PDF = POLICY_DIR / "kb_regular_2020.pdf"
SIMPLIFIED_PDF = POLICY_DIR / "kb_simplified_2020.pdf"


def normalize(text):
    return " ".join(text.split())


def find_row(pages, pdf_path, start_marker, end_marker):
    for page in pages:
        text = normalize(page["text"])
        start = text.find(start_marker)

        if start < 0:
            continue

        end = text.find(end_marker, start + len(start_marker))
        if end < 0:
            continue

        row = text[start:end]
        room_charge = row.find("상급병실료 차액")

        if room_charge < 0:
            continue

        # 이번 비교 대상은 입원실료·입원제비용·입원수술비다.
        # 상급병실료 차액의 별도 공제 조건은 제외한다.
        excerpt = row[:room_charge].rstrip(" ∙")

        if "입원실료, 입원제비용, 입원수술비" not in excerpt:
            continue

        return {
            "file": pdf_path.name,
            "page": page["page"],
            "text": excerpt,
        }

    raise ValueError(
        f"{pdf_path.name}에서 '{start_marker}' 행을 찾지 못했습니다."
    )


def find_deductible_rows():
    regular_pages = extract_pages(REGULAR_PDF)
    simplified_pages = extract_pages(SIMPLIFIED_PDF)

    return {
        "regular_standard": find_row(
            regular_pages,
            REGULAR_PDF,
            "표준형 상해입원",
            "상해통원(외래)",
        ),
        "regular_selected": find_row(
            regular_pages,
            REGULAR_PDF,
            "선택형Ⅱ 상해입원",
            "상해통원(외래)",
        ),
        "simplified": find_row(
            simplified_pages,
            SIMPLIFIED_PDF,
            "유병력자실손의료비(상해입원형)",
            "유병력자실손의료비(상해통원형)",
        ),
    }


def main():
    labels = {
        "regular_standard": "일반형 표준형",
        "regular_selected": "일반형 선택형Ⅱ",
        "simplified": "간편가입형 상해입원형",
    }

    for key, evidence in find_deductible_rows().items():
        print(f"\n{labels[key]}")
        print(f"{evidence['file']}, PDF {evidence['page']}쪽")
        print(evidence["text"])


if __name__ == "__main__":
    main()