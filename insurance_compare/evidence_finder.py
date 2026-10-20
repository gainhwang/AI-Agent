from pathlib import Path
from .pdf_reader import extract_pages


def find_evidence(pdf_path, keyword, context=80):
    results = []
    pages = extract_pages(pdf_path)

    for index, page in enumerate(pages):
        text = " ".join(page["text"].split())
        position = text.find(keyword)

        if position >= 0:
            previous = pages[index - 1] if index > 0 else None
            results.append({
                "file": Path(pdf_path).name,
                "page": page["page"],
                "snippet": text[max(0, position - context):position + len(keyword) + context],
                "previous_page": previous["page"] if previous else None,
                "previous_text": previous["text"] if previous else "",
            })

    return results


if __name__ == "__main__":
    for filename in ("kb_regular_2020.pdf", "kb_simplified_2020.pdf"):
        print(f"\n{filename}")
        path = Path("data/policies") / filename
        for result in find_evidence(path, "도수치료"):
            print(result["page"], result["snippet"])