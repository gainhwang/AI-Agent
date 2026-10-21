import json
import os

import httpx
from dotenv import load_dotenv

from .limit_finder import find_limit_evidence


def format_evidence(label, evidence):
    return (
        f"[{label} — {evidence['file']}, PDF {evidence['page']}쪽]\n"
        f"{evidence['text']}"
    )


def response_format():
    properties = {
        "regular_max": {"type": "string"},
        "regular_amount_selected_at_contract": {"type": "boolean"},
        "simplified_limit": {"type": "string"},
        "regular_page": {"type": "integer"},
        "simplified_page": {"type": "integer"},
    }

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "injury_hospitalization_limit",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
        },
    }


def validate_result(result, evidence):
    regular_text = "".join(evidence["regular"]["text"].split())
    simplified_text = "".join(evidence["simplified"]["text"].split())

    if not all(
        phrase in regular_text
        for phrase in ("하나의상해당", "5천만원이내에서", "계약자가정한금액")
    ):
        raise RuntimeError("일반형 원문에서 보장 한도 조건을 확인하지 못했습니다.")

    if not all(
        phrase in simplified_text
        for phrase in ("하나의상해당", "보험가입금액(5천만원)")
    ):
        raise RuntimeError("간편가입형 원문에서 보장 한도를 확인하지 못했습니다.")

    if result["regular_max"].strip() != "5천만원":
        raise RuntimeError("AI가 추출한 일반형 상한 금액이 원문과 다릅니다.")

    if result["regular_amount_selected_at_contract"] is not True:
        raise RuntimeError("일반형 가입금액을 계약 시 정한다는 조건이 누락됐습니다.")

    if result["simplified_limit"].strip() != "5천만원":
        raise RuntimeError("AI가 추출한 간편가입형 한도 금액이 원문과 다릅니다.")

    if result["regular_page"] != evidence["regular"]["page"]:
        raise RuntimeError("일반형 PDF 쪽수가 검색된 근거와 다릅니다.")

    if result["simplified_page"] != evidence["simplified"]["page"]:
        raise RuntimeError("간편가입형 PDF 쪽수가 검색된 근거와 다릅니다.")


def build_output(result, evidence):
    regular = evidence["regular"]
    simplified = evidence["simplified"]

    return {
        "topic": "상해입원 보장 한도",
        "regular": (
            "일반형은 하나의 상해당 5천만원 이내에서 계약자가 정한 "
            "보험가입금액을 한도로 합니다. "
            f"({regular['file']}, PDF {result['regular_page']}쪽)"
        ),
        "simplified": (
            "간편가입형은 하나의 상해당 보험가입금액 5천만원을 "
            "한도로 합니다. "
            f"({simplified['file']}, PDF {result['simplified_page']}쪽)"
        ),
        "comparison": (
            "일반형의 5천만원은 계약자가 정할 수 있는 가입금액의 "
            "상한이므로 실제 가입금액이 5천만원이라고 단정할 수 없습니다. "
            "간편가입형 약관에는 5천만원 한도가 명시되어 있습니다. "
            "실제 일반형 가입금액은 보험증권 확인이 필요합니다."
        ),
        "regular_pages": [result["regular_page"]],
        "simplified_pages": [result["simplified_page"]],
        "needs_contract_confirmation": True,
        "evidence": evidence,
    }


def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key or api_key == "sk-...":
        raise RuntimeError(".env의 OPENAI_API_KEY를 확인하세요.")

    evidence = find_limit_evidence()
    source_text = "\n\n".join(
        (
            format_evidence("일반형", evidence["regular"]),
            format_evidence("간편가입형", evidence["simplified"]),
        )
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
                        "너는 보험 약관 수치 추출 보조 에이전트다. "
                        "제공된 원문에서 상해입원의 '하나의 상해당' "
                        "보험가입금액 한도만 추출하라. "
                        "일반형의 5천만원은 계약자가 정하는 금액의 상한인지 "
                        "확인하고, 실제 가입금액이 5천만원이라고 단정하지 마라. "
                        "금액은 '5천만원'처럼 원문 표기로 적어라. "
                        "PDF 쪽수는 제공된 근거의 쪽수를 사용하라."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "두 약관의 상해입원 보장 한도 수치와 조건을 "
                        f"추출해줘.\n\n{source_text}"
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
    validate_result(result, evidence)
    output = build_output(result, evidence)

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()