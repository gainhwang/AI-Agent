import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from .generic_evidence import TOPICS
from .pdf_input import MAX_PDF_BYTES, load_pdf


ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="실손의료보험 PDF 비교")

PAGE = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>실손의료보험 PDF 비교</title>
  <style>
    body { font-family: sans-serif; max-width: 900px; margin: 40px auto;
           padding: 0 18px; color: #243247; background: #f6f8fb; }
    .card { background: white; border: 1px solid #dce4ee; border-radius: 12px;
            padding: 24px; margin: 20px 0; }
    label { display: block; margin: 16px 0 6px; font-weight: bold; }
    input, select, button { font: inherit; }
    input[type=file], select { width: 100%; max-width: 620px; padding: 10px;
                               border: 1px solid #b9c8d8; border-radius: 8px; }
    button { margin-top: 20px; padding: 12px 18px; border: 0; border-radius: 8px;
             color: white; background: #1769aa; cursor: pointer; }
    button:disabled { opacity: .6; cursor: wait; }
    table { width: 100%; border-collapse: collapse; margin-top: 16px; }
    th, td { border: 1px solid #dce4ee; padding: 12px; text-align: left;
             vertical-align: top; line-height: 1.6; white-space: pre-line; }
    th { background: #edf4fa; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #f2f5f8;
          padding: 12px; border-radius: 8px; line-height: 1.6; }
    .muted { color: #607087; }
    .notice { background: #fff6df; padding: 12px; border-radius: 8px; }
  </style>
</head>
<body>
  <h1>실손의료보험 PDF 비교</h1>
  <p class="muted">텍스트를 추출할 수 있는 실손약관 PDF 두 개를 선택하세요.</p>

  <section class="card">
    <form id="compare-form">
      <label for="first">첫 번째 약관 PDF</label>
      <input id="first" name="first" type="file"
             accept=".pdf,application/pdf" required>

      <label for="second">두 번째 약관 PDF</label>
      <input id="second" name="second" type="file"
             accept=".pdf,application/pdf" required>

      <label for="topic">비교 항목</label>
      <select id="topic" name="topic">
        <option value="therapy">비급여 도수치료</option>
        <option value="deductible">상해입원 자기부담금</option>
        <option value="limit">상해입원 보장 한도</option>
        <option value="exclusion">임신·출산 관련 면책 사항</option>
      </select>

      <button id="submit" type="submit">PDF 비교하기</button>
      <p id="message" role="status"></p>
    </form>
  </section>

  <section id="result" class="card" hidden>
    <h2 id="title">비교 결과</h2>
    <table>
      <thead>
        <tr>
          <th>첫 번째 PDF</th>
          <th>두 번째 PDF</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td id="left-summary"></td>
          <td id="right-summary"></td>
        </tr>
      </tbody>
    </table>

    <h3>차이 요약</h3>
    <p id="comparison"></p>
    <p class="notice">
      PDF 원문을 바탕으로 자동 생성한 비교입니다. 아래 근거와 실제 가입 내용을 확인하세요.
    </p>

    <details>
      <summary>인용 근거 및 검증 결과 보기</summary>
      <pre id="evidence"></pre>
    </details>
  </section>

  <script>
    const form = document.getElementById('compare-form');
    const button = document.getElementById('submit');
    const message = document.getElementById('message');
    const result = document.getElementById('result');

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      button.disabled = true;
      result.hidden = true;
      message.textContent = 'PDF에서 근거를 찾고 비교하고 있습니다…';

      try {
        const response = await fetch('/compare-upload', {
          method: 'POST',
          body: new FormData(form)
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || '비교에 실패했습니다.');
        }

        document.getElementById('title').textContent = data.topic;
        document.getElementById('left-summary').textContent =
          data.left.file + '\\n' + data.left.summary;
        document.getElementById('right-summary').textContent =
          data.right.file + '\\n' + data.right.summary;
        document.getElementById('comparison').textContent = data.comparison;

        const lines = [];
        for (const side of ['left', 'right']) {
          const item = data[side];
          lines.push(item.file + ' — ' + item.status);

          if (item.evidence.length === 0) {
            lines.push('확인된 인용 근거 없음');
          }

          for (const claim of item.evidence) {
            lines.push('PDF ' + claim.page + '쪽: ' + claim.quote);
          }
          lines.push('');
        }

        if (data.validation_notes.length > 0) {
          lines.push(
            '검증 메모: ' + data.validation_notes.join(' / ')
          );
        }

        document.getElementById('evidence').textContent =
          lines.join('\\n');
        result.hidden = false;
        message.textContent = '';
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


@app.get("/")
def index():
    return HTMLResponse(PAGE)


def read_upload(upload):
    content = upload.file.read(MAX_PDF_BYTES + 1)

    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=400,
            detail="PDF 파일은 각각 25MB 이하여야 합니다.",
        )

    try:
        document = load_pdf(
            upload.filename or "",
            content,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return document["file"], content


@app.post("/compare-upload")
def compare_upload(
    topic: str = Form(...),
    first: UploadFile = File(...),
    second: UploadFile = File(...),
):
    if topic not in TOPICS:
        raise HTTPException(
            status_code=400,
            detail="지원하지 않는 비교 항목입니다.",
        )

    first_name, first_content = read_upload(first)
    second_name, second_content = read_upload(second)

    with TemporaryDirectory(prefix="policy-compare-") as temporary:
        root = Path(temporary)
        first_dir = root / "first"
        second_dir = root / "second"
        first_dir.mkdir()
        second_dir.mkdir()

        first_path = first_dir / first_name
        second_path = second_dir / second_name
        first_path.write_bytes(first_content)
        second_path.write_bytes(second_content)

        try:
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "insurance_compare.generic_compare",
                    topic,
                    str(first_path),
                    str(second_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=120,
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