from pathlib import Path

from .pdf_reader import extract_pages


POLICY_DIR = Path("data/policies")
POLICY_FILES = {
    "regular": POLICY_DIR / "kb_regular_2020.pdf",
    "simplified": POLICY_DIR / "kb_simplified_2020.pdf",
}


def find_exclusion(pdf_path):
    for page in extract_pages(pdf_path):
        text = " ".join(page["text"].split())

        if (
            "제4조(보상하지 않는 사항)" not in text
            or "상해입원" not in text
        ):
            continue

        start = text.find("4. 피보험자가 임신, 출산")
        if start < 0:
            continue

        end = text.find("5. 전쟁", start)
        if end < 0:
            continue

        excerpt = text[start:end].strip()
        required = (
            "산후기로 입원한 경우",
            "다만,",
            "회사가 보상하는 상해로 인하여 입원한 경우",
        )

        if not all(phrase in excerpt for phrase in required):
            continue

        return {
            "file": pdf_path.name,
            "page": page["page"],
            "text": excerpt,
        }

    raise ValueError(
        f"{pdf_path.name}에서 상해입원 면책 조항을 찾지 못했습니다."
    )


def find_exclusion_evidence():
    return {
        label: find_exclusion(path)
        for label, path in POLICY_FILES.items()
    }


def main():
    labels = {
        "regular": "일반형",
        "simplified": "간편가입형",
    }

    for key, evidence in find_exclusion_evidence().items():
        print(f"\n{labels[key]}")
        print(f"{evidence['file']}, PDF {evidence['page']}쪽")
        print(evidence["text"])


if __name__ == "__main__":
    main()