const form = document.getElementById('compare-form');
const button = document.getElementById('submit');
const buttonText = button.querySelector('.button-text');
const message = document.getElementById('message');
const result = document.getElementById('result');
const rows = document.getElementById('result-rows');
const stats = document.getElementById('result-stats');

const statusLabel = { same: '동일', different: '차이 있음', unclear: '확인 필요' };

for (const side of ['first', 'second']) {
  const input = document.getElementById(side);
  const name = document.getElementById(side + '-name');
  input.addEventListener('change', () => {
    const file = input.files[0];
    name.textContent = file ? '선택됨: ' + file.name : 'PDF 파일만 · 최대 25MB';
    name.classList.toggle('has-file', Boolean(file));
  });
}

function element(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined) node.textContent = value;
  return node;
}

function addCell(row, className) {
  const cell = element('td', className);
  row.appendChild(cell);
  return cell;
}

function renderEvidenceSide(container, entry, label) {
  const column = element('section', 'evidence-side');
  column.appendChild(element('h4', '', label + ' · ' + entry.file));
  if (!entry.evidence.length) {
    column.appendChild(element('p', 'evidence-empty', '확인된 인용 근거 없음'));
  } else {
    const list = element('ol', 'evidence-list');
    for (const claim of entry.evidence) {
      const item = element('li', 'evidence-item');
      item.appendChild(element('span', 'page-tag', 'PDF ' + claim.page + '쪽'));
      item.appendChild(element('p', 'evidence-quote', claim.quote));
      list.appendChild(item);
    }
    column.appendChild(list);
  }
  container.appendChild(column);
}

function renderItem(item, index) {
  const status = Object.hasOwn(statusLabel, item.comparison_status)
    ? item.comparison_status : 'unclear';
  const row = element('tr', 'comparison-row');
  row.dataset.status = status;

  const topic = addCell(row, 'topic-cell');
  topic.appendChild(element('span', 'topic-number', String(index + 1).padStart(2, '0')));
  topic.appendChild(element('strong', 'topic-name', item.topic));
  addCell(row, 'policy-cell').textContent = item.left.summary;
  addCell(row, 'policy-cell').textContent = item.right.summary;
  const comparison = addCell(row, 'comparison-cell');
  comparison.appendChild(element('span', 'status-badge status-' + status, statusLabel[status]));
  comparison.appendChild(element('p', 'comparison-copy', item.comparison));
  rows.appendChild(row);

  const detailsRow = element('tr', 'details-row');
  const detailsCell = addCell(detailsRow, 'details-cell');
  detailsCell.colSpan = 4;
  const details = element('details', 'evidence-details');
  details.appendChild(element('summary', '', '인용 원문과 검증 결과 보기'));
  const grid = element('div', 'evidence-grid');
  renderEvidenceSide(grid, item.left, '첫 번째 PDF');
  renderEvidenceSide(grid, item.right, '두 번째 PDF');
  details.appendChild(grid);
  if (item.validation_notes.length) {
    details.appendChild(element('p', 'validation-note', '검증 메모: ' + item.validation_notes.join(' / ')));
  }
  detailsCell.appendChild(details);
  rows.appendChild(detailsRow);
}

function renderStats(items) {
  const counts = { same: 0, different: 0, unclear: 0 };
  for (const item of items) {
    if (Object.hasOwn(counts, item.comparison_status)) counts[item.comparison_status]++;
  }
  stats.replaceChildren();
  for (const status of ['same', 'different', 'unclear']) {
    const chip = element('span', 'stat stat-' + status);
    chip.appendChild(element('strong', '', String(counts[status])));
    chip.appendChild(document.createTextNode(statusLabel[status]));
    stats.appendChild(chip);
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  button.disabled = true;
  button.classList.add('is-loading');
  buttonText.textContent = '비교하는 중';
  form.setAttribute('aria-busy', 'true');
  result.hidden = true;
  message.className = 'message-info';
  message.textContent = 'PDF를 읽고 항목별 근거를 확인하고 있습니다. 잠시만 기다려 주세요.';

  try {
    const response = await fetch('/compare-upload', {
      method: 'POST',
      body: new FormData(form)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || '비교에 실패했습니다.');

    const items = data.results || [data];
    rows.replaceChildren();
    items.forEach(renderItem);
    renderStats(items);
    document.getElementById('file-names').textContent =
      (data.first_file || data.left.file) + ' ↔ ' +
      (data.second_file || data.right.file);
    result.hidden = false;
    message.className = 'message-success';
    message.textContent = items.length + '개 항목 비교를 완료했습니다.';
    result.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    message.className = 'message-error';
    message.textContent = error.message;
  } finally {
    button.disabled = false;
    button.classList.remove('is-loading');
    buttonText.textContent = '약관 비교하기';
    form.removeAttribute('aria-busy');
  }
});
