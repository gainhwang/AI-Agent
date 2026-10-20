import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

from .evidence_selector import select_evidence


REGULAR_PDF = Path("data/policies/kb_regular_2020.pdf")
SIMPLIFIED_PDF = Path("data/policies/kb_simplified_2020.pdf")


def format_evidence(evidence):
    parts = []

    if evidence["previous_page"] is not None and evidence["previous_context"]:
        parts.append(
            f"[{evidence['file']}, PDF {evidence['previous_page']}쪽 — 앞쪽 조항 문맥]\n"
            f"{evidence['previous_context']}"
        )

    parts.append(
        f"[{evidence['file']}, PDF {evidence['page']}쪽 — 검색된 조항]\n"
        f"{evidence['snippet']}"
    )

    return "\n\n".join(parts)


def allowed_pages(evidence):
    pages = {evidence["page"]}

    if evidence["previous_page"] is not None:
        pages.add(evidence["previous_page"])

    return pages


def expected_status(evidence):
    current = evidence["snippet"]
    previous = evidence["previous_context"]

    if (
        "보상하지 않는 사항" in previous
        and "보상하지 않습니다" in previous
    ):
        return "excluded"

    if (
        "보상하지 않는 사항" in current
        and "보상하지 않습니다" in current
    ):
        return "excluded"

    if "특별약관" in current and "보상하는 내용" in current:
        return "special_rider"

    return None


def response_format():
    status_options = [
        "special_rider",
        "covered",
        "excluded",
        "unclear",
    ]

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


def validate_result(result, evidence_by_type):
    exclusion_words = (
        "보상하지",
        "보장되지",
        "보상 제외",
        "보장 제외",
        "제외",
    )

    for label, evidence in evidence_by_type.items():
        status = result[f"{label}_status"]
        cited_pages = result[f"{label}_pages"]
        expected = expected_status(evidence)

        if expected is not None and status != expected:
            raise RuntimeError(
                f"{label} 약관의 보장 상태가 근거와 맞지 않습니다."
            )

        if (
            not cited_pages
            or evidence["page"] not in cited_pages
            or not set(cited_pages).issubset(allowed_pages(evidence))
        ):
            raise RuntimeError(
                f"{label} 약관의 근거 페이지가 실제 검색 결과와 다릅니다."
            )

        if status == "excluded" and not any(
            word in result[label] for word in exclusion_words
        ):
            raise RuntimeError(
                f"{label} 설명에 보상 제외 내용이 없습니다."
            )

    statuses = (
        result["regular_status"],
        result["simplified_status"],
    )

    if "special_rider" in statuses and result["needs_confirmation"] is not True:
        raise RuntimeError("특별약관 가입 확인 필요 여부가 누락되었습니다.")

    if "excluded" in statuses and not any(
        word in result["comparison"] for word in exclusion_words
    ):
        raise RuntimeError("비교 설명에 보상 제외 내용이 없습니다.")


def finalize_result(result, evidence_by_type, keyword):
    for label, evidence in evidence_by_type.items():
        if result[f"{label}_status"] == "special_rider":
            result[label] = (
                f"{keyword} 관련 특별약관에 보상 조항이 있습니다. "
                "실제 적용 여부는 해당 특약 가입 확인이 필요합니다. "
                f"({evidence['file']}, PDF {evidence['page']}쪽)"
            )

    if (
        result["regular_status"] == "special_rider"
        and result["simplified_status"] == "excluded"
    ):
        regular = evidence_by_type["regular"]
        simplified = evidence_by_type["simplified"]

        result["comparison"] = (
            f"일반형에는 {keyword} 관련 특별약관의 보상 조항이 있으나, "
            "실제 적용은 해당 특약 가입 확인이 필요합니다. "
            f"({regular['file']}, PDF {regular['page']}쪽) "
            f"간편가입형에서는 {keyword} 관련 비급여의료비가 "
            "보상 제외 항목에 포함됩니다. "
            f"({simplified['file']}, PDF {simplified['page']}쪽)"
        )

    return result


def main():
    keyword = sys.argv[1] if len(sys.argv) > 1 else "도수치료"

    if not keyword.strip():
        raise RuntimeError("검색어를 입력하세요.")

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key or api_key == "sk-...":
        raise RuntimeError(".env의 OPENAI_API_KEY를 확인하세요.")

    evidence_by_type = {
        "regular": select_evidence(REGULAR_PDF, keyword),
        "simplified": select_evidence(SIMPLIFIED_PDF, keyword),
    }

    for label, evidence in evidence_by_type.items():
        if evidence is None:
            raise RuntimeError(
                f"{label} 약관에서 '{keyword}' 근거를 찾지 못했습니다. "
                "AI 비교를 실행하지 않습니다."
            )

        pages = sorted(allowed_pages(evidence))
        print(
            f"{label} 자동 선택 근거: PDF {pages}쪽",
            file=sys.stderr,
        )

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
                        "제공된 근거만 사용하고, 없는 내용은 추정하지 마라. "
                        "special_rider는 특별약관의 보상 조항, "
                        "excluded는 보상하지 않는 사항을 뜻한다. "
                        "앞쪽 PDF 페이지의 조항 제목이 다음 페이지의 목록에 "
                        "이어질 수 있으므로 문맥을 함께 읽어라. "
                        "특별약관에 보상 조항이 있어도 실제 가입 여부는 "
                        "별도로 확인해야 한다. "
                        "보상 제외 목록을 보장한다고 해석하지 마라. "
                        "각 설명에 파일명과 PDF 쪽수를 표시하라."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"'{keyword}'에 대해 일반형과 간편가입형을 비교해줘.\n\n"
                        "일반형 근거:\n"
                        f"{format_evidence(evidence_by_type['regular'])}\n\n"
                        "간편가입형 근거:\n"
                        f"{format_evidence(evidence_by_type['simplified'])}"
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
    validate_result(result, evidence_by_type)
    result = finalize_result(
        result,
        evidence_by_type,
        keyword,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()