import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

from .pdf_reader import extract_pages


REGULAR_PDF = Path("data/policies/kb_regular_2020.pdf")
SIMPLIFIED_PDF = Path("data/policies/kb_simplified_2020.pdf")


def text_between(text, start, end):
    start_at = text.find(start)
    end_at = text.find(end, start_at + len(start))

    if start_at < 0 or end_at < 0:
        raise ValueError(f"약관에서 조항을 찾지 못했습니다: {start}")

    return text[start_at:end_at].strip()


def build_evidence():
    regular_pages = extract_pages(REGULAR_PDF)
    simplified_pages = extract_pages(SIMPLIFIED_PDF)

    regular_clause = text_between(
        regular_pages[76]["text"],
        "제1장 비급여 실손의료비 특별약관",
        "제2조(용어의 정의)",
    )

    page_53 = simplified_pages[52]["text"]
    page_54 = simplified_pages[53]["text"]

    heading_start = page_53.find("제3관 회사가 보상하지 않는 사항")
    heading_end = page_53.find("(1) 상해입원", heading_start)
    exclusion_line = "회사는 다음의 입원의료비에 대해서는 보상하지 않습니다."

    if (
        heading_start < 0
        or heading_end < 0
        or exclusion_line not in page_53
    ):
        raise ValueError("간편가입형의 보상 제외 제목을 찾지 못했습니다.")

    heading = page_53[
        heading_start:heading_end + len("(1) 상해입원")
    ].strip()

    simplified_clause = text_between(
        page_54,
        "11. 도수치료",
        "12. 비급여 주사료",
    )

    regular_evidence = (
        f"[{REGULAR_PDF.name}, PDF 77쪽]\n{regular_clause}"
    )
    simplified_evidence = (
        f"[{SIMPLIFIED_PDF.name}, PDF 53쪽]\n"
        f"{heading}\n{exclusion_line}\n\n"
        f"[{SIMPLIFIED_PDF.name}, PDF 54쪽 — 위 제외 목록의 11호]\n"
        f"{simplified_clause}"
    )

    return regular_evidence, simplified_evidence


def response_format():
    status_options = ["special_rider", "covered", "excluded", "unclear"]

    properties = {
        "regular_status": {
            "type": "string",
            "enum": status_options,
        },
        "simplified_status": {
            "type": "string",
            "enum": status_options,
        },
        "regular": {"type": "string"},
        "simplified": {"type": "string"},
        "comparison": {"type": "string"},
        "regular_pages": {
            "type": "array",
            "items": {"type": "integer"},
        },
        "simplified_pages": {
            "type": "array",
            "items": {"type": "integer"},
        },
        "needs_confirmation": {"type": "boolean"},
    }

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "policy_comparison",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
        },
    }


def validate_result(result):
    if result["regular_status"] != "special_rider":
        raise RuntimeError("일반형의 특별약관을 잘못 해석했습니다.")

    if result["simplified_status"] != "excluded":
        raise RuntimeError("간편가입형의 보상 제외 조항을 잘못 해석했습니다.")

    if not result["regular_pages"] or not set(
        result["regular_pages"]
    ).issubset({77}):
        raise RuntimeError("일반형 근거 페이지가 잘못되었습니다.")

    if not result["simplified_pages"] or not set(
        result["simplified_pages"]
    ).issubset({53, 54}):
        raise RuntimeError("간편가입형 근거 페이지가 잘못되었습니다.")

    if result["needs_confirmation"] is not True:
        raise RuntimeError("특약 가입 확인 필요 여부가 누락되었습니다.")

    exclusion_words = (
        "보상하지",
        "보장되지",
        "보상 제외",
        "보장 제외",
        "제외",
    )

    if not any(word in result["simplified"] for word in exclusion_words):
        raise RuntimeError("간편가입형 설명에 보상 제외 내용이 없습니다.")

    if not any(word in result["comparison"] for word in exclusion_words):
        raise RuntimeError("비교 설명에 보상 제외 내용이 없습니다.")


def add_confirmation_notice(result):
    # 현재 도수치료 시연 사례에 한정한 안전 문구
    if result["regular_status"] == "special_rider":
        result["regular"] = (
            "비급여 도수치료 특별약관에 보상 조항이 있습니다. "
            "실제 적용 여부는 해당 특약 가입 확인이 필요합니다. "
            f"({REGULAR_PDF.name}, PDF 77쪽)"
        )

    return result


def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key or api_key == "sk-...":
        raise RuntimeError(".env의 OPENAI_API_KEY를 확인하세요.")

    regular, simplified = build_evidence()

    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": os.getenv("OPENAI_FAST_MODEL", "gpt-4o-mini"),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "너는 보험 약관 비교 보조 에이전트다. "
                        "제공된 조항만 근거로 답하라. "
                        "special_rider는 특별약관의 보상 조항, "
                        "excluded는 보상하지 않는 사항을 뜻한다. "
                        "특별약관은 실제 가입 여부를 확인해야 한다. "
                        "보상 제외 목록의 항목을 보장한다고 해석하지 마라. "
                        "각 설명에 파일명과 PDF 쪽수를 표시하라."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "비급여 도수치료를 비교해줘. "
                        "간편가입형 PDF 53쪽의 제목과 54쪽의 11호는 "
                        "이어지는 조항이다.\n\n"
                        f"{regular}\n\n{simplified}"
                    ),
                },
            ],
            "response_format": response_format(),
        },
        timeout=60.0,
    )

    response.raise_for_status()
    choice = response.json()["choices"][0]
    message = choice["message"]

    if (
        choice["finish_reason"] != "stop"
        or message.get("refusal")
        or not message.get("content")
    ):
        raise RuntimeError("AI 답변이 완료되지 않았습니다.")

    result = json.loads(message["content"])
    validate_result(result)
    result = add_confirmation_notice(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()