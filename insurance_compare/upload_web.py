import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .generic_evidence import TOPICS
from .pdf_input import MAX_PDF_BYTES, load_pdf


ROOT = Path(__file__).resolve().parent.parent
FRONTEND = Path(__file__).resolve().parent / "frontend"
app = FastAPI(title="실손의료보험 PDF 비교")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


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