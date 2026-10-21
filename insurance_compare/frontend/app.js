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
          data.left.file + '\n' + data.left.summary;
        document.getElementById('right-summary').textContent =
          data.right.file + '\n' + data.right.summary;
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
          lines.join('\n');
        result.hidden = false;
        message.textContent = '';
      } catch (error) {
        message.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    });
