"""Compare all four topics after extracting each uploaded PDF once."""
import json
import sys
from pathlib import Path

from .generic_compare import build_output, compare_documents
from .generic_evidence import TOPICS, find_candidates
from .pdf_input import load_pdf
from .scoped_rules import unclear


def compare_all(documents):
    results = []
    for topic in TOPICS:
        candidates = {
            side: find_candidates(document, topic)
            for side, document in documents.items()
        }
        try:
            checked, notes = compare_documents(topic, documents, candidates)
        except Exception:
            # A failed model request must not be mistaken for a policy finding.
            checked, notes = unclear(
                "이 항목의 AI 비교를 완료하지 못했습니다. 원문을 확인하세요."
            )
        results.append({"key": topic, **build_output(topic, documents, checked, notes)})
    return {
        "first_file": documents["left"]["file"],
        "second_file": documents["right"]["file"],
        "results": results,
    }


def main():
    if len(sys.argv) != 3:
        raise SystemExit("사용법: python -m insurance_compare.compare_all 첫번째.pdf 두번째.pdf")
    documents = {
        side: load_pdf(Path(filename).name, Path(filename).read_bytes())
        for side, filename in zip(("left", "right"), sys.argv[1:])
    }
    print(json.dumps(compare_all(documents), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
