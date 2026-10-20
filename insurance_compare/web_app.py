import json
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="실손의료보험 약관 비교")

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
    }
    th { background: #edf4fa; }
    .notice { background: #fff6df; padding: 12px; border-radius: 8px; }
    #message { min-height: 24px; }
  </style>
</head>
<body>
  <h1>실손의료보험 약관 비교</h1>
  <p class="muted">약관 원문에서 근거를 찾고, AI가 차이를 설명합니다.</p>

  <section class="card">
    <h2>비교할 약관</h2>
    <p>일반형: kb_regular_2020.pdf</p>
    <p>간편가입형: kb_simplified_2020.pdf</p>
    <p><strong>비교 항목:</strong> 비급여 도수치료</p>
    <button id="compare" type="button">약관 비교하기</button>
    <p id="message" role="status"></p>
  </section>

  <section id="result" class="card" hidden>
    <h2>비교 결과</h2>
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
          <th>판단</th>
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
    <p id="confirmation" class="notice" hidden>
      실제 적용 여부는 가입한 특별약관을 확인해야 합니다.
    </p>
  </section>

  <script>
    const button = document.getElementById("compare");
    const message = document.getElementById("message");
    const resultBox = document.getElementById("result");

    const statusNames = {
      special_rider: "특별약관 보상 조항",
      covered: "보상 조항",
      excluded: "보상 제외",
      unclear: "확인 필요"
    };

    button.addEventListener("click", async () => {
      button.disabled = true;
      resultBox.hidden = true;
      message.textContent = "약관을 비교하고 있습니다…";

      try {
        const response = await fetch("/compare", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ keyword: "도수치료" })
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "비교에 실패했습니다.");
        }

        document.getElementById("regular-status").textContent =
          statusNames[data.regular_status] || data.regular_status;
        document.getElementById("simplified-status").textContent =
          statusNames[data.simplified_status] || data.simplified_status;
        document.getElementById("regular").textContent = data.regular;
        document.getElementById("simplified").textContent = data.simplified;
        document.getElementById("regular-pages").textContent =
          data.regular_pages.join(", ") + "쪽";
        document.getElementById("simplified-pages").textContent =
          data.simplified_pages.join(", ") + "쪽";
        document.getElementById("comparison").textContent = data.comparison;
        document.getElementById("confirmation").hidden =
          !data.needs_confirmation;

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
    keyword: str = Field(min_length=1, max_length=30)


@app.get("/")
def index():
    return HTMLResponse(PAGE)


@app.post("/compare")
def compare(request: CompareRequest):
    if request.keyword.strip() != "도수치료":
        raise HTTPException(
            status_code=400,
            detail="현재 시연에서는 도수치료 비교만 지원합니다.",
        )

    try:
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "insurance_compare.ai_demo",
                request.keyword,
            ],
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
