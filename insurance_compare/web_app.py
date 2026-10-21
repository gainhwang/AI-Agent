import json
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="실손의료보험 약관 비교")

MODULES = {
    "therapy": ("insurance_compare.ai_demo", ["도수치료"]),
    "deductible": ("insurance_compare.deductible_ai", []),
    "limit": ("insurance_compare.limit_ai", []),
}

PAGE = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>실손의료보험 약관 비교</title>
  <style>
    body {
      font-family: sans-serif;
      max-width: 900px;
      margin: 48px auto;
      padding: 0 20px;
      color: #243247;
      background: #f6f8fb;
    }
    h1 { margin-bottom: 8px; }
    .card {
      background: white;
      border: 1px solid #dce4ee;
      border-radius: 12px;
      padding: 24px;
      margin: 20px 0;
    }
    .muted { color: #607087; }
    label { display: block; margin-bottom: 10px; font-weight: bold; }
    select {
      font: inherit;
      padding: 10px;
      border: 1px solid #b9c8d8;
      border-radius: 8px;
      margin-right: 10px;
    }
    button {
      background: #1769aa;
      color: white;
      border: 0;
      border-radius: 8px;
      padding: 12px 18px;
      cursor: pointer;
      font-size: 15px;
    }
    button:disabled { opacity: .6; cursor: wait; }
    table { width: 100%; border-collapse: collapse; margin-top: 18px; }
    th, td {
      border: 1px solid #dce4ee;
      padding: 12px;
      text-align: left;
      vertical-align: top;
      line-height: 1.6;
      white-space: pre-line;
    }
    th { background: #edf4fa; }
    .notice { background: #fff6df; padding: 12px; border-radius: 8px; }
    #message { min-height: 24px; }
    details { margin-top: 20px; }
    pre {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: #f2f5f8;
      padding: 14px;
      border-radius: 8px;
      line-height: 1.6;
    }
  </style>
</head>
<body>
  <h1>실손의료보험 약관 비교</h1>
  <p class="muted">
    시연용 일반형·간편가입형 PDF에서 근거를 찾고 차이를 비교합니다.
  </p>

  <section class="card">
    <h2>비교 조건</h2>
    <p>일반형: kb_regular_2020.pdf</p>
    <p>간편가입형: kb_simplified_2020.pdf</p>

    <label for="topic">비교 항목</label>
    <select id="topic">
      <option value="therapy">비급여 도수치료</option>
      <option value="deductible">상해입원 자기부담금</option>
      <option value="limit">상해입원 보장 한도</option>
    </select>
    <button id="compare" type="button">약관 비교하기</button>
    <p id="message" role="status"></p>
  </section>

  <section id="result" class="card" hidden>
    <h2 id="result-title">비교 결과</h2>
    <table>
      <thead>
        <tr>
          <th>구분</th>
          <th>일반형</th>
          <th>간편가입형</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <th>유형·판단</th>
          <td id="regular-status"></td>
          <td id="simplified-status"></td>
        </tr>
        <tr>
          <th>약관 내용</th>
          <td id="regular"></td>
          <td id="simplified"></td>
        </tr>
        <tr>
          <th>근거 PDF 쪽수</th>
          <td id="regular-pages"></td>
          <td id="simplified-pages"></td>
        </tr>
      </tbody>
    </table>

    <h3>차이 요약</h3>
    <p id="comparison"></p>
    <p id="notice" class="notice" hidden></p>

    <details id="evidence-box" hidden>
      <summary>약관 원문 근거 보기</summary>
      <pre id="evidence-text"></pre>
    </details>
  </section>

  <script>
    const topicSelect = document.getElementById("topic");
    const button = document.getElementById("compare");
    const message = document.getElementById("message");
    const resultBox = document.getElementById("result");
    const notice = document.getElementById("notice");
    const evidenceBox = document.getElementById("evidence-box");
    const evidenceText = document.getElementById("evidence-text");

    const statusNames = {
      special_rider: "특별약관 보상 조항",
      covered: "보상 조항",
      excluded: "보상 제외",
      unclear: "확인 필요"
    };

    const titles = {
      therapy: "비급여 도수치료 비교",
      deductible: "상해입원 자기부담금 비교",
      limit: "상해입원 보장 한도 비교"
    };

    button.addEventListener("click", async () => {
      const topic = topicSelect.value;
      button.disabled = true;
      resultBox.hidden = true;
      message.textContent = "약관을 비교하고 있습니다…";

      try {
        const response = await fetch("/compare", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ topic })
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "비교에 실패했습니다.");
        }

        document.getElementById("result-title").textContent = titles[topic];
        evidenceBox.hidden = true;
        notice.hidden = true;

        if (topic === "therapy") {
          document.getElementById("regular-status").textContent =
            statusNames[data.regular_status] || data.regular_status;
          document.getElementById("simplified-status").textContent =
            statusNames[data.simplified_status] || data.simplified_status;
          document.getElementById("regular").textContent = data.regular;
          document.getElementById("simplified").textContent = data.simplified;

          notice.hidden = !data.needs_confirmation;
          notice.textContent =
            "실제 적용 여부는 가입한 특별약관을 확인해야 합니다.";

        } else if (topic === "deductible") {
          document.getElementById("regular-status").textContent =
            "표준형 / 선택형Ⅱ";
          document.getElementById("simplified-status").textContent =
            "유병력자실손 상해입원형";
          document.getElementById("regular").textContent =
            data.regular_standard + "\\n\\n" + data.regular_selected;
          document.getElementById("simplified").textContent =
            data.simplified;

          notice.hidden = !data.needs_plan_confirmation;
          notice.textContent =
            "실제 비교에는 가입한 일반형 유형 확인이 필요합니다.";

          const evidence = data.evidence;
          evidenceText.textContent =
            "일반형 표준형 — PDF " +
            evidence.regular_standard.page + "쪽\\n" +
            evidence.regular_standard.text + "\\n\\n" +
            "일반형 선택형Ⅱ — PDF " +
            evidence.regular_selected.page + "쪽\\n" +
            evidence.regular_selected.text + "\\n\\n" +
            "간편가입형 — PDF " +
            evidence.simplified.page + "쪽\\n" +
            evidence.simplified.text;
          evidenceBox.hidden = false;

        } else if (topic === "limit") {
          document.getElementById("regular-status").textContent =
            "계약 시 가입금액 선택";
          document.getElementById("simplified-status").textContent =
            "5천만원 한도";
          document.getElementById("regular").textContent = data.regular;
          document.getElementById("simplified").textContent = data.simplified;

          notice.hidden = !data.needs_contract_confirmation;
          notice.textContent =
            "일반형의 실제 가입금액은 보험증권 확인이 필요합니다.";

          const evidence = data.evidence;
          evidenceText.textContent =
            "일반형 — " + evidence.regular.file +
            ", PDF " + evidence.regular.page + "쪽\\n" +
            evidence.regular.text + "\\n\\n" +
            "간편가입형 — " + evidence.simplified.file +
            ", PDF " + evidence.simplified.page + "쪽\\n" +
            evidence.simplified.text;
          evidenceBox.hidden = false;
        }

        document.getElementById("regular-pages").textContent =
          data.regular_pages.join(", ") + "쪽";
        document.getElementById("simplified-pages").textContent =
          data.simplified_pages.join(", ") + "쪽";
        document.getElementById("comparison").textContent =
          data.comparison;

        resultBox.hidden = false;
        message.textContent = "";
      } catch (error) {
        message.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


class CompareRequest(BaseModel):
    topic: str


@app.get("/")
def index():
    return HTMLResponse(PAGE)


@app.post("/compare")
def compare(request: CompareRequest):
    selected = MODULES.get(request.topic)

    if selected is None:
        raise HTTPException(
            status_code=400,
            detail="지원하지 않는 비교 항목입니다.",
        )

    module, arguments = selected

    try:
        process = subprocess.run(
            [sys.executable, "-m", module, *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=504,
            detail="비교 시간이 초과됐습니다.",
        ) from exc

    if process.returncode != 0:
        print(process.stderr, file=sys.stderr)
        raise HTTPException(
            status_code=500,
            detail="비교에 실패했습니다. 서버 터미널의 오류를 확인하세요.",
        )

    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail="비교 결과를 읽지 못했습니다.",
        ) from exc