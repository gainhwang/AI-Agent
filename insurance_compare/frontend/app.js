const form = document.getElementById('compare-form');
const button = document.getElementById('submit');
const message = document.getElementById('message');
const result = document.getElementById('result');
const rows = document.getElementById('result-rows');

const statusLabel = { same: '동일', different: '차이 있음', unclear: '확인 필요' };

function evidenceText(item) {
  const lines = [];
  for (const side of ['left', 'right']) {
    const entry = item[side];
    lines.push(entry.file + ' — ' + entry.status);
    if (!entry.evidence.length) lines.push('확인된 인용 근거 없음');
    for (const claim of entry.evidence) {
      lines.push('PDF ' + claim.page + '쪽: ' + claim.quote);
    }
    lines.push('');
  }
  if (item.validation_notes.length) {
    lines.push('검증 메모: ' + item.validation_notes.join(' / '));
  }
  return lines.join('\n');
}

function addCell(row, value) {
  const cell = document.createElement('td');
  cell.textContent = value;
  row.appendChild(cell);
  return cell;
}

function renderItem(item) {
  const row = document.createElement('tr');
  addCell(row, item.topic);
  addCell(row, item.left.summary);
  addCell(row, item.right.summary);
  const comparison = addCell(row, statusLabel[item.comparison_status] + '\n' + item.comparison);
  comparison.classList.add('comparison');
  rows.appendChild(row);

  const detailsRow = document.createElement('tr');
  const detailsCell = document.createElement('td');
  detailsCell.colSpan = 4;
  const details = document.createElement('details');
  const summary = document.createElement('summary');
  summary.textContent = item.topic + ' — 인용 근거 및 검증 결과';
  const pre = document.createElement('pre');
  pre.textContent = evidenceText(item);
  details.append(summary, pre);
  detailsCell.appendChild(details);
  detailsRow.appendChild(detailsCell);
  rows.appendChild(detailsRow);
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  button.disabled = true;
  result.hidden = true;
  message.textContent = 'PDF를 읽고 항목별 근거를 검증하고 있습니다…';

  try {
    const response = await fetch('/compare-upload', {
      method: 'POST',
      body: new FormData(form)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || '비교에 실패했습니다.');

    const items = data.results || [data];
    rows.replaceChildren();
    for (const item of items) renderItem(item);
    document.getElementById('file-names').textContent =
      (data.first_file || data.left.file) + ' ↔ ' +
      (data.second_file || data.right.file);
    result.hidden = false;
    message.textContent = items.length + '개 항목 비교를 완료했습니다.';
    result.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    message.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
