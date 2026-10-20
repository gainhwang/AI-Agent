import json
import os

import httpx
from dotenv import load_dotenv

from .deductible_finder import find_deductible_rows


def format_evidence(label, evidence):
    return (
        f"[{label} — {evidence['file']}, PDF {evidence['page']}쪽]\n"
        f"{evidence['text']}"
    )


def response_format():
    properties = {
        "regular_standard_rate": {"type": "string"},
        "regular_selected_paid_rate": {"type": "string"},
        "regular_selected_nonpaid_rate": {"type": "string"},
        "simplified_fixed_amount": {"type": "string"},
        "simplified_rate": {"type": "string"},
        "regular_page": {"type": "integer"},
        "simplified_page": {"type": "integer"},
    }

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "deductible_comparison",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
        },
    }


def validate_result(result, rows):
    expected_values = {
        "regular_standard_rate": "20%",
        "regular_selected_paid_rate": "10%",
        "regular_selected_nonpaid_rate": "20%",
        "simplified_fixed_amount": "10만원",
        "simplified_rate": "30%",
    }

    for field, expected in expected_values.items():
        if result[field].strip() != expected:
            raise RuntimeError(
                f"{field} 추출 결과가 원문 기준값과 다릅니다: "
                f"{result[field]}"
            )

    regular_page = rows["regular_standard"]["page"]
    selected_page = rows["regular_selected"]["page"]
    simplified_page = rows["simplified"]["page"]

    if result["regular_page"] not in {regular_page, selected_page}:
        raise RuntimeError("일반형 PDF 쪽수가 검색된 근거와 다릅니다.")

    if result["simplified_page"] != simplified_page:
        raise RuntimeError("간편가입형 PDF 쪽수가 검색된 근거와 다릅니다.")

    source_checks = {
        "regular_standard": ("20%",),
        "regular_selected": ("급여 10%", "비급여 20%", "합산액"),
        "simplified": ("10만원", "30%", "큰 금액"),
    }

    for label, markers in source_checks.items():
        source = rows[label]["text"]

        if not all(marker in source for marker in markers):
            raise RuntimeError(
                f"{label}의 원문에서 기준 수치를 확인하지 못했습니다."
            )


def build_output(result, rows):
    regular_file = rows["regular_standard"]["file"]
    simplified_file = rows["simplified"]["file"]
    regular_page = result["regular_page"]
    simplified_page = result["simplified_page"]

    regular_standard = (
        "일반형 표준형의 상해입원 입원실료·입원제비용·입원수술비 "
        f"자기부담금은 보상대상의료비의 "
        f"{result['regular_standard_rate']}입니다. "
        f"({regular_file}, PDF {regular_page}쪽)"
    )

    regular_selected = (
        "일반형 선택형Ⅱ의 같은 항목 자기부담금은 "
        f"급여 {result['regular_selected_paid_rate']} 해당액과 "
        f"비급여 {result['regular_selected_nonpaid_rate']} 해당액의 "
        f"합산액입니다. ({regular_file}, PDF {regular_page}쪽)"
    )

    simplified = (
        "간편가입형 상해입원형의 같은 항목 자기부담금은 "
        f"{result['simplified_fixed_amount']}과 "
        f"보상대상의료비의 {result['simplified_rate']} 중 "
        f"큰 금액입니다. ({simplified_file}, PDF {simplified_page}쪽)"
    )

    return {
        "topic": "상해입원 자기부담금",
        "regular_standard": regular_standard,
        "regular_selected": regular_selected,
        "simplified": simplified,
        "comparison": (
            "일반형은 표준형과 선택형Ⅱ의 공제 방식이 서로 다르고, "
            "간편가입형은 정액 10만원과 30% 중 큰 금액을 공제합니다. "
            "실제 비교에는 가입한 일반형 유형 확인이 필요합니다."
        ),
        "regular_pages": [regular_page],
        "simplified_pages": [simplified_page],
        "needs_plan_confirmation": True,
        "evidence": rows,
    }


def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key or api_key == "sk-...":
        raise RuntimeError(".env의 OPENAI_API_KEY를 확인하세요.")

    rows = find_deductible_rows()

    evidence = "\n\n".join(
        (
            format_evidence("일반형 표준형", rows["regular_standard"]),
            format_evidence("일반형 선택형Ⅱ", rows["regular_selected"]),
            format_evidence("간편가입형 상해입원형", rows["simplified"]),
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
                        "제공된 세 행에서 상해입원 입원실료·입원제비용·"
                        "입원수술비의 자기부담금 수치만 추출하라. "
                        "일반형 표준형과 선택형Ⅱ를 구분하라. "
                        "선택형Ⅱ의 급여 비율과 비급여 비율을 구분하라. "
                        "수치는 20%, 10만원처럼 원문 표기로 적고, "
                        "상급병실료 차액은 이번 비교에서 제외하라."
                    ),
                },
                {
                    "role": "user",
                    "content": f"세 약관 행의 수치와 PDF 쪽수를 추출해줘.\n\n{evidence}",
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

    extracted = json.loads(message["content"])
    validate_result(extracted, rows)
    output = build_output(extracted, rows)

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()