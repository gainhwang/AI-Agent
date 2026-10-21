from pathlib import Path

from .pdf_reader import extract_pages


POLICY_DIR = Path("data/policies")
POLICY_FILES = {
    "regular": POLICY_DIR / "kb_regular_2020.pdf",
    "simplified": POLICY_DIR / "kb_simplified_2020.pdf",
}


def normalize(text):
    return " ".join(text.split())


def find_limit(pdf_path):
    for page in extract_pages(pdf_path):
        text = normalize(page["text"])
        start = text.find("(1) 상해입원")

        if start < 0:
            continue

        end = text.find("보상합니다.", start)
        if end < 0:
            continue

        excerpt = text[start:end + len("보상합니다.")]

        required = ("하나의 상해당", "보험가입금액", "5천만원")
        if not all(word in excerpt for word in required):
            continue

        return {
            "file": pdf_path.name,
            "page": page["page"],
            "text": excerpt,
        }

    raise ValueError(
        f"{pdf_path.name}에서 상해입원 보장 한도 조항을 찾지 못했습니다."
    )


def find_limit_evidence():
    return {
        label: find_limit(path)
        for label, path in POLICY_FILES.items()
    }


def main():
    labels = {
        "regular": "일반형",
        "simplified": "간편가입형",
    }

    for key, evidence in find_limit_evidence().items():
        print(f"\n{labels[key]}")
        print(f"{evidence['file']}, PDF {evidence['page']}쪽")
        print(evidence["text"])


if __name__ == "__main__":
    main()