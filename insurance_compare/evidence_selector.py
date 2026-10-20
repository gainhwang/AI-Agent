import sys
from pathlib import Path

from .pdf_reader import extract_pages


POLICY_DIR = Path("data/policies")
POLICY_FILES = (
    "kb_regular_2020.pdf",
    "kb_simplified_2020.pdf",
)


def normalize(text):
    return " ".join(text.split())


def select_evidence(pdf_path, keyword):
    if not keyword.strip():
        raise ValueError("검색어를 입력하세요.")

    pages = extract_pages(pdf_path)
    candidates = []

    for index, page in enumerate(pages):
        text = normalize(page["text"])

        if keyword not in text:
            continue

        previous_text = (
            normalize(pages[index - 1]["text"])
            if index > 0
            else ""
        )

        score = 2 * text.count(keyword)

        if f"비급여 {keyword}" in text:
            score += 5

        if "특별약관" in text and "보상하는 내용" in text:
            score += 6

        if "보상하지 않는 사항" in previous_text:
            score += 8

        if "보상하지 않습니다" in text:
            score += 3

        # 목차에 반복되는 점선이 많으면 우선순위를 낮춘다.
        if text.count("·") > 15:
            score -= 10

        candidates.append((score, index))

    if not candidates:
        return None

    # 점수가 같으면 앞쪽 PDF 페이지를 선택한다.
    score, index = sorted(
        candidates,
        key=lambda item: (-item[0], item[1]),
    )[0]

    page = pages[index]
    text = normalize(page["text"])
    position = text.find(keyword)

    snippet = text[
        max(0, position - 250):position + len(keyword) + 900
    ]

    previous_page = None
    previous_context = ""

    if index > 0:
        previous_text = normalize(pages[index - 1]["text"])

        if "보상하지 않는 사항" in previous_text:
            heading_at = previous_text.find(
                "제3관 회사가 보상하지 않는 사항"
            )
            if heading_at < 0:
                heading_at = previous_text.find("보상하지 않는 사항")

            previous_page = pages[index - 1]["page"]
            previous_context = previous_text[heading_at:]

    return {
        "file": Path(pdf_path).name,
        "page": page["page"],
        "score": score,
        "snippet": snippet,
        "previous_page": previous_page,
        "previous_context": previous_context,
    }


def main():
    keyword = sys.argv[1] if len(sys.argv) > 1 else "도수치료"

    for filename in POLICY_FILES:
        result = select_evidence(POLICY_DIR / filename, keyword)

        print(f"\n{filename}")

        if result is None:
            print(f"'{keyword}' 검색 결과가 없습니다.")
            continue

        print(f"선택된 근거: PDF {result['page']}쪽")
        print(f"검색 점수: {result['score']}")

        if result["previous_page"] is not None:
            print(f"\n이전 PDF {result['previous_page']}쪽의 조항 제목·문맥:")
            print(result["previous_context"])

        print(f"\nPDF {result['page']}쪽의 관련 문장:")
        print(result["snippet"])


if __name__ == "__main__":
    main()