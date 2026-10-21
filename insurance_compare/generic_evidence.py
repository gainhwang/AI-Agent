import sys
from pathlib import Path

from .pdf_input import load_pdf


TOPICS = {
    "therapy": {
        "groups": (("도수치료",),),
        "weights": {
            "도수치료": 8,
            "비급여": 2,
            "보상": 2,
            "특별약관": 2,
            "보상하지": 2,
            "350만원": 1,
            "50회": 1,
        },
        "focus": ("도수치료",),
    },
    "deductible": {
        "groups": (
            ("자기부담금", "공제금액", "공제"),
            ("입원",),
            ("상해",),
        ),
        "weights": {
            "자기부담금": 8,
            "공제금액": 7,
            "공제": 2,
            "입원": 2,
            "상해": 2,
            "보상대상의료비": 3,
            "급여": 1,
            "비급여": 1,
        },
        "focus": ("자기부담금", "공제금액", "공제"),
    },
    "limit": {
        "groups": (
            ("보험가입금액",),
            ("상해",),
            ("입원",),
        ),
        "weights": {
            "보험가입금액": 7,
            "상해": 2,
            "입원": 2,
            "한도": 3,
            "연간": 1,
            "5천만원": 2,
            "보상": 1,
        },
        "focus": ("보험가입금액",),
    },
    "exclusion": {
        "groups": (
            ("임신",),
            ("출산",),
            ("보상하지",),
            ("상해",),
        ),
        "weights": {
            "임신": 5,
            "출산": 5,
            "산후기": 3,
            "보상하지": 4,
            "상해": 2,
            "입원": 1,
            "제4조": 1,
            "다만": 2,
        },
        "focus": ("임신",),
    },
}


def normalize(text):
    return " ".join(text.split())


def find_candidates(document, topic, max_results=3):
    if topic not in TOPICS:
        raise ValueError(f"지원하지 않는 비교 항목입니다: {topic}")

    spec = TOPICS[topic]
    candidates = []

    for page in document["pages"]:
        text = normalize(page["text"])

        has_required_terms = all(
            any(term in text for term in group)
            for group in spec["groups"]
        )
        if not has_required_terms:
            continue

        score = sum(
            weight
            for term, weight in spec["weights"].items()
            if term in text
        )

        # 목차 페이지는 관련 단어가 많이 나와도 근거로 우선하지 않는다.
        if text.count("·") > 20 or "목 차" in text[:200]:
            score -= 100

        if score <= 0:
            continue

        focus = next(
            (term for term in spec["focus"] if term in text),
            None,
        )
        position = text.find(focus) if focus else 0

        snippet = text[
            max(0, position - 220):position + 900
        ]

        candidates.append({
            "file": document["file"],
            "page": page["page"],
            "score": score,
            "snippet": snippet,
        })

    return sorted(
        candidates,
        key=lambda item: (-item["score"], item["page"]),
    )[:max_results]


def main():
    if len(sys.argv) != 4:
        raise SystemExit(
            "사용법: python -m insurance_compare.generic_evidence "
            "therapy|deductible|limit|exclusion 첫번째.pdf 두번째.pdf"
        )

    topic = sys.argv[1]

    if topic not in TOPICS:
        raise SystemExit(f"지원하지 않는 비교 항목입니다: {topic}")

    for filename in sys.argv[2:]:
        path = Path(filename)
        document = load_pdf(path.name, path.read_bytes())
        candidates = find_candidates(document, topic)

        print(f"\n{document['file']} — {topic}")

        if not candidates:
            print("근거 후보를 찾지 못했습니다.")
            continue

        for candidate in candidates:
            print(
                f"\nPDF {candidate['page']}쪽 "
                f"(검색 점수 {candidate['score']})"
            )
            print(candidate["snippet"])


if __name__ == "__main__":
    main()