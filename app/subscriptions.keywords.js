// 订阅关键词管理模块
// 负责：渲染关键词列表、增加/删除关键词

window.SubscriptionsKeywords = (function () {
  let keywordsListEl = null;
  let keywordInput = null;
  let keywordAliasInput = null;
  let addBtn = null;
  let msgEl = null;
  let reloadAll = null;

  // 简单的 HTML 转义，避免 XSS
  const escapeHtml = (str) => {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  };

  // 校验关键词语法，避免生成无法被 YAML 正常解析的配置
  const validateKeywordSyntax = (keyword) => {
    const raw = (keyword || '').trim();
    if (!raw) {
      return { valid: false, message: '关键词不能为空' };
    }
    return { valid: true, message: '' };
  };

  const render = (items) => {
    if (!keywordsListEl) return;
    if (!items || !items.length) {
      keywordsListEl.innerHTML =
        '<div style="color:#999;">暂无关键词订阅，可在下方新增。</div>';
      return;
    }
    keywordsListEl.innerHTML = '';
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
            ? '<span class="tag-label tag-green">' +
              escapeHtml(tag) +
              '</span>'
            : ''
        }${escapeHtml(item.keyword || '')}</span>
        <button data-id="${
          item.id
        }" class="arxiv-keyword-del" style="border:none;background:none;color:#c00;font-size:11px;cursor:pointer;">删除</button>
      `;
      keywordsListEl.appendChild(row);
    });

    keywordsListEl.querySelectorAll('.arxiv-keyword-del').forEach((btn) => {
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
            const list = Array.isArray(subs.keywords)
              ? subs.keywords.slice()
              : [];
            if (index >= 0 && index < list.length) {
              list.splice(index, 1);
            }
            subs.keywords = list;
            next.subscriptions = subs;
            return next;
          });
          if (typeof reloadAll === 'function') reloadAll();
        } catch (err) {
          console.error(err);
          if (msgEl) {
            msgEl.textContent = '删除关键词失败，请稍后重试';
            msgEl.style.color = '#c00';
          }
        }
      });
    });
  };

  const addKeyword = async () => {
    if (!keywordInput || !keywordAliasInput) return;
    const keyword = (keywordInput.value || '').trim();
    const tag = (keywordAliasInput.value || '').trim();
    if (!keyword) {
      if (msgEl) {
        msgEl.textContent = '关键词不能为空';
        msgEl.style.color = '#c00';
      }
      return;
    }

    // 关键词语法校验
    const { valid, message } = validateKeywordSyntax(keyword);
    if (!valid) {
      if (msgEl) {
        msgEl.textContent = message || '关键词格式不合法';
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
        const list = Array.isArray(subs.keywords) ? subs.keywords.slice() : [];
        list.push({ keyword, tag });
        subs.keywords = list;
        next.subscriptions = subs;
        return next;
      });

      if (msgEl) {
        msgEl.textContent = '关键词已添加到本地草稿，点击「保存」后才会同步到云端。';
        msgEl.style.color = '#666';
      }
      keywordInput.value = '';
      keywordAliasInput.value = '';
      if (typeof reloadAll === 'function') reloadAll();
    } catch (e) {
      console.error(e);
      if (msgEl) {
        msgEl.textContent = '新增关键词失败，请稍后重试';
        msgEl.style.color = '#c00';
      }
    }
  };

  const attach = (context) => {
    keywordsListEl = context.keywordsListEl || null;
    keywordInput = context.keywordInput || null;
    keywordAliasInput = context.keywordAliasInput || null;
    addBtn = context.keywordAddBtn || null;
    msgEl = context.msgEl || null;
    reloadAll = context.reloadAll || null;

    // 首次挂载时渲染占位提示，避免面板初次打开时列表区域为空白
    if (keywordsListEl && !keywordsListEl._initialized) {
      keywordsListEl._initialized = true;
      render([]);
    }

    if (keywordInput && !keywordInput._advancedPlaceholderSet) {
      keywordInput._advancedPlaceholderSet = true;
      keywordInput.placeholder = '输入关键词';
    }

    if (addBtn && !addBtn._bound) {
      addBtn._bound = true;
      addBtn.addEventListener('click', addKeyword);
    }
    if (keywordAliasInput && !keywordAliasInput._bound) {
      keywordAliasInput._bound = true;
      keywordAliasInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
          e.preventDefault();
          addKeyword();
        }
      });
    }
  };

  return {
    attach,
    render,
  };
})();
