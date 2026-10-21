import json
import os

import httpx
from dotenv import load_dotenv

from .exclusion_finder import find_exclusion_evidence


def format_evidence(label, evidence):
    return (
        f"[{label} — 제4조 보상하지 않는 사항, 상해입원]\n"
        f"[{evidence['file']}, PDF {evidence['page']}쪽]\n"
        f"{evidence['text']}"
    )


def response_format():
    properties = {
        "regular_excluded": {"type": "boolean"},
        "regular_has_exception": {"type": "boolean"},
        "simplified_excluded": {"type": "boolean"},
        "simplified_has_exception": {"type": "boolean"},
        "same_rule": {"type": "boolean"},
        "regular_page": {"type": "integer"},
        "simplified_page": {"type": "integer"},
    }

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "injury_hospitalization_exclusion",
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
    required_text = (
        "피보험자가임신,출산(제왕절개를포함합니다),산후기로입원한경우",
        "다만,회사가보상하는상해로인하여입원한경우에는보상합니다",
    )

    normalized = {}

    for label in ("regular", "simplified"):
        text = "".join(evidence[label]["text"].split())
        normalized[label] = text

        if not all(phrase in text for phrase in required_text):
            raise RuntimeError(
                f"{label} 원문에서 면책 조항과 예외를 모두 확인하지 못했습니다."
            )

    if normalized["regular"] != normalized["simplified"]:
        raise RuntimeError("두 약관의 해당 조항이 동일하지 않습니다.")

    expected_true = (
        "regular_excluded",
        "regular_has_exception",
        "simplified_excluded",
        "simplified_has_exception",
        "same_rule",
    )

    for field in expected_true:
        if result[field] is not True:
            raise RuntimeError(
                f"AI의 {field} 판단이 원문과 다릅니다."
            )

    if result["regular_page"] != evidence["regular"]["page"]:
        raise RuntimeError("일반형 PDF 쪽수가 검색된 근거와 다릅니다.")

    if result["simplified_page"] != evidence["simplified"]["page"]:
        raise RuntimeError("간편가입형 PDF 쪽수가 검색된 근거와 다릅니다.")


def build_output(result, evidence):
    regular = evidence["regular"]
    simplified = evidence["simplified"]

    rule = (
        "임신·출산(제왕절개 포함)·산후기로 입원한 경우는 "
        "보상하지 않습니다. 다만, 회사가 보상하는 상해로 "
        "입원한 경우에는 보상합니다."
    )

    return {
        "topic": "상해입원 면책 사항",
        "regular": (
            f"{rule} ({regular['file']}, PDF {result['regular_page']}쪽)"
        ),
        "simplified": (
            f"{rule} ({simplified['file']}, PDF {result['simplified_page']}쪽)"
        ),
        "comparison": (
            "두 약관의 해당 보상 제외 조항과 예외는 같습니다. "
            "이 항목에서는 차이가 확인되지 않습니다."
        ),
        "regular_pages": [result["regular_page"]],
        "simplified_pages": [result["simplified_page"]],
        "needs_case_confirmation": True,
        "evidence": evidence,
    }


def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key or api_key == "sk-...":
        raise RuntimeError(".env의 OPENAI_API_KEY를 확인하세요.")

    evidence = find_exclusion_evidence()
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
                        "너는 보험 약관 비교 보조 에이전트다. "
                        "제공된 제4조 상해입원 조항만 근거로 판단하라. "
                        "임신·출산·산후기 입원의 보상 제외와 "
                        "'회사가 보상하는 상해로 인한 입원' 예외를 "
                        "각각 확인하라. 두 조항이 같으면 차이가 있다고 "
                        "만들어내지 마라. PDF 쪽수는 제공된 근거를 사용하라."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "두 약관의 상해입원 면책 조항과 예외를 "
                        f"비교해줘.\n\n{source_text}"
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