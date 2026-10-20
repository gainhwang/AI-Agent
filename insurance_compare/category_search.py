from pathlib import Path
from .pdf_reader import extract_pages


CATEGORY_KEYWORDS = {
    "보장 항목": ("보장종목", "보상하는 내용"),
    "보장 한도": ("보상한도", "보험가입금액"),
    "자기부담금": ("공제금액", "자기부담금"),
    "면책 사항": ("보상하지 않는 사항", "보상하지 않습니다"),
}


def collect_candidates(pdf_path):
    results = {category: [] for category in CATEGORY_KEYWORDS}

    for page in extract_pages(pdf_path):
        text = " ".join(page["text"].split())

        for category, keywords in CATEGORY_KEYWORDS.items():
            matched = [word for word in keywords if word in text]
            if matched:
                results[category].append({
                    "page": page["page"],
                    "keywords": matched,
                })

    return results


if __name__ == "__main__":
    for filename in ("kb_regular_2020.pdf", "kb_simplified_2020.pdf"):
        print(f"\n{filename}")
        path = Path("data/policies") / filename

        for category, candidates in collect_candidates(path).items():
            pages = [item["page"] for item in candidates]
            print(f"{category}: {pages}")