// 订阅论文新引用（跟踪论文）模块
// 负责：渲染已跟踪论文列表、删除跟踪

window.SubscriptionsTrackedPapers = (function () {
  let trackedListEl = null;
  let msgEl = null;
  let reloadAll = null;

  const escapeHtml = (str) => {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  };

  const render = (items) => {
    if (!trackedListEl) return;
    if (!items || !items.length) {
      trackedListEl.innerHTML =
        '<div style="color:#999;">暂无订阅论文，可通过下方搜索添加。</div>';
      return;
    }
    trackedListEl.innerHTML = '';
    items.forEach((item) => {
      const row = document.createElement('div');
      row.className = 'arxiv-tracked-item';
      const allAuthors = item.authors || [];
      const displayAuthors =
        allAuthors.slice(0, 5).join(', ') +
        (allAuthors.length > 5 ? ', ...' : '');
      const tag = item.tag || item.alias || '';
      row.innerHTML = `
        <div style="flex:1; min-width:0;">
          <div style="font-size:14px; font-weight:500; margin-bottom:2px;">${
            tag
              ? '<span class="tag-label tag-pink">' +
                escapeHtml(tag) +
                '</span>'
              : ''
          }${escapeHtml(item.title || '')}</div>
          <div style="font-size:12px;color:#666;">${
            displayAuthors ? escapeHtml(displayAuthors) : ''
          }</div>
          <div style="font-size:12px;color:#666;">
            ${
              item.published
                ? '发表于：' + escapeHtml(item.published)
                : ''
            }
            ${
              item.arxiv_id
                ? (item.published ? ' ｜ ' : '') +
                  'arXiv: ' +
                  escapeHtml(item.arxiv_id)
                : ''
            }
          </div>
        </div>
        <button data-id="${
          item.id
        }" class="arxiv-tracked-del" style="flex-shrink:0;border:none;background:none;color:#c00;font-size:11px;cursor:pointer;padding:2px 4px;">取消订阅</button>
      `;
      trackedListEl.appendChild(row);
    });

    trackedListEl.querySelectorAll('.arxiv-tracked-del').forEach((btn) => {
      if (btn._bound) return;
      btn._bound = true;
      btn.addEventListener('click', async () => {
        const idStr = btn.getAttribute('data-id');
        if (idStr == null) return;
        const index = parseInt(idStr, 10);
        if (Number.isNaN(index)) return;
        try {
          if (
            !window.SubscriptionsManager ||
            !window.SubscriptionsManager.updateDraftConfig
          ) {
            throw new Error('缺少本地草稿更新能力');
          }
          window.SubscriptionsManager.updateDraftConfig((cfg) => {
            const next = cfg || {};
            if (!next.subscriptions) next.subscriptions = {};
            const subs = next.subscriptions;
            const list = Array.isArray(subs.tracked_papers)
              ? subs.tracked_papers.slice()
              : [];
            if (index >= 0 && index < list.length) {
              list.splice(index, 1);
            }
            subs.tracked_papers = list;
            next.subscriptions = subs;
            return next;
          });
          if (typeof reloadAll === 'function') reloadAll();
        } catch (err) {
          console.error(err);
          if (msgEl) {
            msgEl.textContent = '取消订阅失败，请稍后重试';
            msgEl.style.color = '#c00';
          }
        }
      });
    });
  };

  const attach = (context) => {
    trackedListEl = context.trackedListEl || null;
    msgEl = context.msgEl || null;
    reloadAll = context.reloadAll || null;

    // 首次挂载时渲染占位提示，避免面板初次打开时列表区域为空白
    if (trackedListEl && !trackedListEl._initialized) {
      trackedListEl._initialized = true;
      render([]);
    }
  };

  return {
    attach,
    render,
  };
})();
