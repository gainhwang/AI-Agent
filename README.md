# 실손의료보험 약관 비교 에이전트

두 실손약관 PDF를 올려 4개 항목을 한 번에 비교하고 PDF 쪽수와 인용 원문을 확인하는 미니프로젝트입니다.

## 실행

```bash
python -m pip install -r requirements.txt
python -m uvicorn insurance_compare.upload_web:app --host 127.0.0.1 --port 8702
```

`http://127.0.0.1:8702/`에서 두 PDF를 업로드하세요. 기본값은 전체 4개 항목 비교입니다. 포트가 이미 사용 중이면 다른 포트로 실행하면 됩니다.

- [결과 보고서](RESULT_REPORT.md)
- [시연 가이드](DEMO_GUIDE.md)
- [시연 기준 답안](DEMO_EXPECTED.md)
- [발표자료](deliverables/insurance_policy_comparison_report.pptx)

익숙하지 않은 약관 문구의 AI 보조 비교에는 `.env`의 `OPENAI_API_KEY`가 필요합니다. 시연용 PDF와 `.env`는 Git에 포함하지 않습니다. PDF에 추출 가능한 텍스트가 있어야 하며, 출력은 실제 계약의 보장 확정이 아닙니다.

## 테스트

```bash
python -m unittest discover -s insurance_compare/tests -v
python -m insurance_compare.compare_all data/policies/kb_2022.pdf data/policies/kb_2023.pdf
```
