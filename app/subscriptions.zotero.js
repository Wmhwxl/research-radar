// 智能订阅管理模块（原 Zotero）
// 负责：渲染智能订阅列表（query + 标签）、增加/删除订阅

window.SubscriptionsZotero = (function () {
  let zoteroListEl = null;
  let zoteroIdInput = null;
  let zoteroAliasInput = null;
  let zoteroAddBtn = null;
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
    if (!zoteroListEl) return;
    if (!items || !items.length) {
      zoteroListEl.innerHTML =
        '<div style="color:#999;">暂无智能订阅，可在下方新增。</div>';
      return;
    }
    zoteroListEl.innerHTML = '';
    items.forEach((item) => {
      const row = document.createElement('div');
      row.style.display = 'flex';
      row.style.alignItems = 'center';
      row.style.justifyContent = 'space-between';
      row.style.marginBottom = '2px';
      const tag = item.tag || item.alias || '';
      row.innerHTML = `
        <span>${
          tag
            ? '<span class="tag-label tag-blue">' +
              escapeHtml(tag) +
              '</span>'
            : ''
        }${escapeHtml(item.zotero_id || '')}</span>
        <button data-id="${
          item.id
        }" class="zotero-del-btn" style="border:none;background:none;color:#c00;font-size:11px;cursor:pointer;">删除</button>
      `;
      zoteroListEl.appendChild(row);
    });

    zoteroListEl.querySelectorAll('.zotero-del-btn').forEach((btn) => {
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
            const list = Array.isArray(subs.llm_queries)
              ? subs.llm_queries.slice()
              : [];
            if (index >= 0 && index < list.length) {
              list.splice(index, 1);
            }
            subs.llm_queries = list;
            next.subscriptions = subs;
            return next;
          });
          if (typeof reloadAll === 'function') reloadAll();
        } catch (err) {
          console.error(err);
        }
      });
    });
  };

  const addZotero = async () => {
    if (!zoteroIdInput || !zoteroAliasInput) return;

    const query = (zoteroIdInput.value || '').trim();
    const tag = (zoteroAliasInput.value || '').trim();
    if (!query) {
      if (msgEl) {
        msgEl.textContent = '查询语句不能为空';
        msgEl.style.color = '#c00';
      }
      return;
    }
    if (!tag) {
      if (msgEl) {
        msgEl.textContent = '标签为必填项';
        msgEl.style.color = '#c00';
      }
      return;
    }
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
        const list = Array.isArray(subs.llm_queries)
          ? subs.llm_queries.slice()
          : [];
        list.push({
          query,
          tag,
        });
        subs.llm_queries = list;
        next.subscriptions = subs;
        return next;
      });

      if (msgEl) {
        msgEl.textContent = '智能订阅已添加到本地草稿，点击「保存」后才会同步到云端。';
        msgEl.style.color = '#666';
      }
      zoteroIdInput.value = '';
      zoteroAliasInput.value = '';
      if (typeof reloadAll === 'function') reloadAll();
    } catch (e) {
      console.error(e);
      if (msgEl) {
        msgEl.textContent = '新增智能订阅失败，请稍后重试';
        msgEl.style.color = '#c00';
      }
    }
  };

  const attach = (context) => {
    zoteroListEl = context.zoteroListEl || null;
    zoteroIdInput = context.zoteroIdInput || null;
    zoteroAliasInput = context.zoteroAliasInput || null;
    zoteroAddBtn = context.zoteroAddBtn || null;
    msgEl = context.msgEl || null;
    reloadAll = context.reloadAll || null;

    // 首次挂载时渲染占位提示，避免面板初次打开时列表区域为空白
    if (zoteroListEl && !zoteroListEl._initialized) {
      zoteroListEl._initialized = true;
      render([]);
    }

    if (zoteroAddBtn && !zoteroAddBtn._bound) {
      zoteroAddBtn._bound = true;
      zoteroAddBtn.addEventListener('click', addZotero);
    }

    if (zoteroAliasInput && !zoteroAliasInput._bound) {
      zoteroAliasInput._bound = true;
      zoteroAliasInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
          e.preventDefault();
          addZotero();
        }
      });
    }
  };

  return {
    attach,
    render,
  };
})();
