(function (root, factory) {
  const api = factory(root || globalThis);
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.DPRFeedback = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
  const ISSUE_TYPES = Object.freeze([
    '功能新增',
    'BUG反馈',
    '体验问题',
    '论文 / 会议数据',
    '其他',
  ]);
  const TARGET_OWNER = 'ziwenhahaha';
  const TARGET_REPO = 'daily-paper-reader';
  const FEEDBACK_ANIMATION_MS = 180;

  const getFeedbackMotionStyles = (isVisible) => ({
    overlay: {
      opacity: isVisible ? '1' : '0',
    },
    panel: {
      opacity: isVisible ? '1' : '0',
      transform: isVisible
        ? 'translateY(0) scale(1)'
        : 'translateY(12px) scale(0.98)',
    },
  });

  const state = {
    overlay: null,
    refs: null,
    bodyOverflow: '',
    attemptedSubmit: false,
    submitting: false,
    submitted: false,
    submittedLabel: '',
    pendingDraftUrl: '',
    restoreFocus: null,
    keydownHandler: null,
    openFrame: null,
    closingTimer: null,
    isClosing: false,
  };

  const normalizeText = (value) => String(value == null ? '' : value).replace(/\r\n/g, '\n').trim();

  const normalizeInlineText = (value) => normalizeText(value).replace(/\s+/g, ' ');

  const normalizeSelectedTypes = (values) => {
    const rawValues = Array.isArray(values)
      ? values
      : values && typeof values[Symbol.iterator] === 'function'
        ? Array.from(values)
        : values == null
          ? []
          : [values];
    const selected = new Set(rawValues.map((item) => String(item || '').trim()).filter(Boolean));
    return ISSUE_TYPES.filter((item) => selected.has(item));
  };

  const stripExistingTypePrefix = (title) => normalizeInlineText(title).replace(/^\[[^\]]*\]\s*/u, '');

  const buildIssueTitle = (types, rawTitle) => {
    const normalizedTypes = normalizeSelectedTypes(types);
    const cleanTitle = stripExistingTypePrefix(rawTitle);
    if (!normalizedTypes.length || !cleanTitle) return '';
    return `[${normalizedTypes.join('|')}] ${cleanTitle}`;
  };

  const buildIssueBody = (content) => normalizeText(content);

  const validateFeedbackForm = (form) => {
    const normalizedTypes = normalizeSelectedTypes(form && form.types);
    const plainTitle = stripExistingTypePrefix(form && form.title);
    const body = buildIssueBody(form && form.content);
    const confirmPublic = Boolean(form && form.confirmPublic);
    const errors = {};

    if (!normalizedTypes.length) {
      errors.types = '请至少选择一个反馈类型。';
    }
    if (!plainTitle) {
      errors.title = '请填写标题。';
    }
    if (!body) {
      errors.content = '请填写反馈内容。';
    }
    if (!confirmPublic) {
      errors.confirmPublic = '请先确认将公开提交。';
    }

    const formattedTitle = buildIssueTitle(normalizedTypes, plainTitle);
    return {
      valid: Object.keys(errors).length === 0,
      errors,
      types: normalizedTypes,
      plainTitle,
      formattedTitle,
      body,
      confirmPublic,
    };
  };

  const buildIssueDraftUrl = ({ title, body, owner = TARGET_OWNER, repo = TARGET_REPO } = {}) => {
    const params = new URLSearchParams();
    params.set('title', normalizeInlineText(title));
    params.set('body', buildIssueBody(body));
    return `https://github.com/${owner}/${repo}/issues/new?${params.toString()}`;
  };

  const readTokenFromStoredData = (tokenData) => {
    if (!tokenData) return '';
    if (typeof tokenData === 'string') return String(tokenData).trim();
    return String((tokenData && tokenData.token) || '').trim();
  };

  const resolveGithubToken = (scopeRoot) => {
    const safeRoot = scopeRoot || root || {};
    const secret = safeRoot.decoded_secret_private || {};
    if (secret.github && secret.github.token) {
      return String(secret.github.token || '').trim();
    }
    const tokenLoader = safeRoot.SubscriptionsGithubToken
      && typeof safeRoot.SubscriptionsGithubToken.loadGithubToken === 'function'
      ? safeRoot.SubscriptionsGithubToken.loadGithubToken
      : null;
    if (!tokenLoader) return '';
    return readTokenFromStoredData(tokenLoader.call(safeRoot.SubscriptionsGithubToken));
  };

  const classifyIssueError = (error) => {
    const status = Number(error && error.status);
    if (status === 401 || status === 403 || status === 404) return 'auth';
    if (status === 422) return 'validation';
    return 'unknown';
  };

  const parseGitHubErrorPayload = async (response) => {
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      try {
        const text = await response.text();
        if (text) payload = { message: text };
      } catch {
        payload = null;
      }
    }
    const message = payload && typeof payload.message === 'string'
      ? payload.message
      : `GitHub API 请求失败（HTTP ${response.status}）`;
    return {
      status: response.status,
      message,
      payload,
    };
  };

  const createIssueViaApi = async ({ token, title, body, fetchImpl }) => {
    const response = await fetchImpl(
      `https://api.github.com/repos/${TARGET_OWNER}/${TARGET_REPO}/issues`,
      {
        method: 'POST',
        headers: {
          Authorization: `token ${token}`,
          Accept: 'application/vnd.github+json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title,
          body,
        }),
      },
    );

    if (!response.ok) {
      throw await parseGitHubErrorPayload(response);
    }

    const payload = await response.json().catch(() => ({}));
    return {
      number: payload.number || null,
      htmlUrl: payload.html_url || '',
      payload,
    };
  };

  const openDraftIssuePage = (scopeRoot, url) => {
    if (!url) return false;
    const safeRoot = scopeRoot || root || {};
    try {
      if (typeof safeRoot.open === 'function') {
        const opened = safeRoot.open(url, '_blank', 'noopener');
        if (opened) return true;
      }
    } catch {
      // ignore
    }
    return false;
  };

  const submitIssueWithFallback = async (form, options = {}) => {
    const validation = validateFeedbackForm(form);
    if (!validation.valid) {
      return {
        ok: false,
        mode: 'invalid',
        validation,
        message: Object.values(validation.errors)[0] || '表单校验失败。',
      };
    }

    const safeRoot = options.root || root || {};
    const fetchImpl = options.fetchImpl || (typeof safeRoot.fetch === 'function' ? safeRoot.fetch.bind(safeRoot) : null);
    const token = Object.prototype.hasOwnProperty.call(options, 'token')
      ? String(options.token || '').trim()
      : resolveGithubToken(safeRoot);
    const draftUrl = buildIssueDraftUrl({
      title: validation.formattedTitle,
      body: validation.body,
    });

    if (!token) {
      const opened = options.openDraft === false ? false : openDraftIssuePage(safeRoot, draftUrl);
      return {
        ok: true,
        mode: 'draft',
        opened,
        draftUrl,
        validation,
        message: opened
          ? '未检测到可用 GitHub Token，已为你打开预填好的公开 Issue 页面。'
          : '浏览器未能打开 GitHub，请再次点击提交按钮继续。',
      };
    }

    if (!fetchImpl) {
      const opened = options.openDraft === false ? false : openDraftIssuePage(safeRoot, draftUrl);
      return {
        ok: true,
        mode: 'draft',
        opened,
        draftUrl,
        validation,
        errorKind: 'unknown',
        message: opened
          ? '当前环境无法直接调用 GitHub API，已为你打开预填好的公开 Issue 页面。'
          : '当前环境无法直接调用 GitHub API，请再次点击提交按钮继续。',
      };
    }

    try {
      const created = await createIssueViaApi({
        token,
        title: validation.formattedTitle,
        body: validation.body,
        fetchImpl,
      });
      return {
        ok: true,
        mode: 'api',
        opened: false,
        validation,
        draftUrl,
        issueNumber: created.number,
        htmlUrl: created.htmlUrl,
        message: created.number
          ? `已公开提交到 GitHub Issues：#${created.number}`
          : '已公开提交到 GitHub Issues。',
      };
    } catch (error) {
      const errorKind = classifyIssueError(error);
      const opened = options.openDraft === false ? false : openDraftIssuePage(safeRoot, draftUrl);
      let message = '自动创建 issue 失败，已为你打开预填好的公开 issue 页面。';
      if (errorKind === 'auth') {
        message = opened
          ? 'GitHub Token 可能缺少仓库或 Issues 权限，已打开预填好的公开 Issue 页面。'
          : 'GitHub Token 可能缺少仓库或 Issues 权限，请再次点击提交按钮继续。';
      } else if (errorKind === 'validation') {
        message = opened
          ? 'GitHub API 拒绝了当前内容，已打开预填好的公开 Issue 页面。'
          : 'GitHub API 拒绝了当前内容，请再次点击提交按钮继续。';
      } else if (!opened) {
        message = '自动创建 Issue 失败，请再次点击提交按钮继续。';
      }
      return {
        ok: true,
        mode: 'draft',
        opened,
        draftUrl,
        validation,
        errorKind,
        error,
        message,
      };
    }
  };

  const hasDom = () => Boolean(root && root.document && typeof root.document.createElement === 'function');

  const applyStyles = (node, styles) => {
    Object.keys(styles).forEach((key) => {
      node.style[key] = styles[key];
    });
  };

  const prefersReducedMotion = () => Boolean(
    root
      && typeof root.matchMedia === 'function'
      && root.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );

  const applyFeedbackMotionStyles = (overlay, panel, isVisible) => {
    if (!overlay || !panel) return;
    const styles = getFeedbackMotionStyles(isVisible);
    applyStyles(overlay, styles.overlay);
    applyStyles(panel, styles.panel);
  };

  const clearScheduledOpen = () => {
    if (state.openFrame == null) return;
    if (root && typeof root.cancelAnimationFrame === 'function') {
      root.cancelAnimationFrame(state.openFrame);
    } else {
      root.clearTimeout(state.openFrame);
    }
    state.openFrame = null;
  };

  const clearClosingTimer = () => {
    if (state.closingTimer == null) return;
    root.clearTimeout(state.closingTimer);
    state.closingTimer = null;
  };

  const setStatus = (text, tone) => {
    if (!state.refs || !state.refs.status) return;
    const colorMap = {
      error: '#b42318',
      success: '#067647',
      info: '#344054',
    };
    state.refs.status.textContent = text || '';
    state.refs.status.style.color = colorMap[tone] || colorMap.info;
  };

  const collectFormData = () => {
    const refs = state.refs;
    if (!refs) {
      return {
        types: [],
        title: '',
        content: '',
        confirmPublic: false,
      };
    }
    return {
      types: refs.typeInputs.filter((input) => input.checked).map((input) => input.value),
      title: refs.titleInput.value,
      content: refs.contentInput.value,
      confirmPublic: refs.confirmInput.checked,
    };
  };

  const renderValidationState = () => {
    if (!state.refs) return;
    const validation = validateFeedbackForm(collectFormData());
    const refs = state.refs;
    const canSubmit = (validation.valid || Boolean(state.pendingDraftUrl))
      && !state.submitting
      && !state.submitted;

    refs.submitButton.disabled = !canSubmit;
    refs.submitButton.style.opacity = canSubmit ? '1' : '0.55';
    refs.submitButton.style.cursor = canSubmit ? 'pointer' : 'not-allowed';

    if (refs.titlePreview) {
      refs.titlePreview.textContent = validation.formattedTitle
        ? `Issue 标题：${validation.formattedTitle}`
        : 'Issue 标题将在选择类型并填写标题后生成。';
    }

    if (state.submitted) return validation;

    if (!state.attemptedSubmit) {
      setStatus('公开提交前请确认类型、标题、内容，并勾选公开确认。', 'info');
      return validation;
    }

    if (!validation.valid) {
      const firstError = validation.errors.types
        || validation.errors.title
        || validation.errors.content
        || validation.errors.confirmPublic
        || '表单校验失败。';
      setStatus(firstError, 'error');
      return validation;
    }

    if (!state.submitting) {
      setStatus('确认后将公开提交到 GitHub Issues。', 'info');
    }
    return validation;
  };

  const updateButtonBusyState = () => {
    if (!state.refs) return;
    if (state.submitting) {
      state.refs.submitButton.textContent = '提交中...';
    } else if (state.submitted) {
      state.refs.submitButton.textContent = state.submittedLabel || '已提交';
    } else if (state.pendingDraftUrl) {
      state.refs.submitButton.textContent = '在 GitHub 打开';
    } else {
      state.refs.submitButton.textContent = '公开提交反馈';
    }
    renderValidationState();
  };

  const finishClose = (snapshot) => {
    if (snapshot.overlay && snapshot.overlay.parentNode) {
      snapshot.overlay.parentNode.removeChild(snapshot.overlay);
    }
    if (state.overlay !== snapshot.overlay) return;

    state.overlay = null;
    state.refs = null;
    state.attemptedSubmit = false;
    state.submitting = false;
    state.submitted = false;
    state.submittedLabel = '';
    state.pendingDraftUrl = '';
    state.restoreFocus = null;
    state.keydownHandler = null;
    state.openFrame = null;
    state.closingTimer = null;
    state.isClosing = false;
    state.bodyOverflow = '';
    if (hasDom() && root.document && root.document.body) {
      root.document.body.style.overflow = snapshot.bodyOverflow || '';
    }
    if (snapshot.shouldRestoreFocus
      && snapshot.restoreFocus
      && typeof snapshot.restoreFocus.focus === 'function') {
      snapshot.restoreFocus.focus();
    }
  };

  const close = (options = {}) => {
    if (!state.overlay) return;
    const immediate = Boolean(options && options.immediate);
    const snapshot = {
      overlay: state.overlay,
      restoreFocus: state.restoreFocus,
      bodyOverflow: state.bodyOverflow,
      shouldRestoreFocus: !(options && options.restoreFocus === false),
    };

    if (state.keydownHandler && hasDom()) {
      root.document.removeEventListener('keydown', state.keydownHandler);
    }
    state.keydownHandler = null;
    clearScheduledOpen();

    if (state.isClosing && !immediate) return;
    clearClosingTimer();

    if (immediate || prefersReducedMotion()) {
      finishClose(snapshot);
      return;
    }

    state.isClosing = true;
    state.overlay.style.pointerEvents = 'none';
    state.overlay.setAttribute('aria-hidden', 'true');
    applyFeedbackMotionStyles(state.overlay, state.refs && state.refs.panel, false);
    state.closingTimer = root.setTimeout(() => {
      state.closingTimer = null;
      finishClose(snapshot);
    }, FEEDBACK_ANIMATION_MS);
  };

  const handleSubmit = async () => {
    if (!state.refs || state.submitting) return;
    if (state.pendingDraftUrl) {
      const opened = openDraftIssuePage(root, state.pendingDraftUrl);
      if (opened) {
        state.pendingDraftUrl = '';
        state.submitted = true;
        state.submittedLabel = '已打开 GitHub';
        setStatus('已打开预填好的公开 Issue 页面，请在 GitHub 完成提交。', 'success');
      } else {
        setStatus('浏览器阻止了新窗口，请允许本站打开弹窗后重试。', 'error');
      }
      updateButtonBusyState();
      return;
    }
    state.attemptedSubmit = true;
    const validation = renderValidationState();
    if (!validation.valid) return;

    state.submitting = true;
    updateButtonBusyState();
    setStatus('正在提交公开 issue...', 'info');

    try {
      const result = await submitIssueWithFallback(collectFormData(), { root });
      if (result.mode === 'api') {
        state.submitted = true;
        state.submittedLabel = '提交成功';
        setStatus(result.message, 'success');
      } else {
        if (result.opened) {
          state.submitted = true;
          state.submittedLabel = '已打开 GitHub';
        } else if (result.draftUrl) {
          state.pendingDraftUrl = result.draftUrl;
        }
        setStatus(result.message, result.errorKind ? 'error' : 'info');
      }
    } finally {
      state.submitting = false;
      updateButtonBusyState();
    }
  };

  const createTypeCheckbox = (documentRef, typeLabel) => {
    const label = documentRef.createElement('label');
    label.className = 'dpr-feedback-type-option';
    applyStyles(label, {
      display: 'inline-flex',
      alignItems: 'center',
      gap: '8px',
      padding: '8px 10px',
      border: '1px solid #d0d5dd',
      borderRadius: '8px',
      background: '#f8fafc',
      color: '#101828',
      fontSize: '14px',
      lineHeight: '20px',
      cursor: 'pointer',
      userSelect: 'none',
    });

    const input = documentRef.createElement('input');
    input.type = 'checkbox';
    input.name = 'dpr-feedback-types';
    input.value = typeLabel;
    input.style.margin = '0';
    input.addEventListener('change', () => {
      state.attemptedSubmit = true;
      renderValidationState();
    });

    const text = documentRef.createElement('span');
    text.textContent = typeLabel;

    label.appendChild(input);
    label.appendChild(text);
    return { label, input };
  };

  const buildModal = () => {
    if (!hasDom()) return null;
    const documentRef = root.document;

    const overlay = documentRef.createElement('div');
    overlay.id = 'dpr-feedback-overlay';
    overlay.className = 'dpr-feedback-overlay';
    overlay.setAttribute('role', 'presentation');
    applyStyles(overlay, {
      position: 'fixed',
      inset: '0',
      zIndex: '9999',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px',
      background: 'rgba(15, 23, 42, 0.52)',
      boxSizing: 'border-box',
      opacity: '0',
      transition: `opacity ${FEEDBACK_ANIMATION_MS}ms ease`,
      willChange: 'opacity',
    });
    overlay.addEventListener('click', (event) => {
      if (event.target === overlay) {
        close();
      }
    });

    const panel = documentRef.createElement('section');
    panel.id = 'dpr-feedback-panel';
    panel.className = 'dpr-feedback-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-labelledby', 'dpr-feedback-heading');
    applyStyles(panel, {
      position: 'relative',
      width: 'min(680px, 100%)',
      maxHeight: 'min(760px, calc(100vh - 48px))',
      overflow: 'auto',
      padding: '28px 28px 24px',
      borderRadius: '8px',
      background: '#ffffff',
      boxShadow: '0 24px 72px rgba(15, 23, 42, 0.22)',
      boxSizing: 'border-box',
      color: '#101828',
      fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      opacity: '0',
      transform: 'translateY(12px) scale(0.98)',
      transformOrigin: 'center center',
      transition: `opacity ${FEEDBACK_ANIMATION_MS}ms ease, transform ${FEEDBACK_ANIMATION_MS}ms cubic-bezier(0.2, 0, 0, 1)`,
      willChange: 'opacity, transform',
    });

    const closeButton = documentRef.createElement('button');
    closeButton.id = 'dpr-feedback-close';
    closeButton.type = 'button';
    closeButton.setAttribute('aria-label', '关闭');
    closeButton.textContent = '×';
    applyStyles(closeButton, {
      position: 'absolute',
      top: '12px',
      right: '12px',
      width: '36px',
      height: '36px',
      border: '0',
      borderRadius: '999px',
      background: 'transparent',
      color: '#344054',
      fontSize: '24px',
      lineHeight: '36px',
      cursor: 'pointer',
    });
    closeButton.addEventListener('click', close);

    const title = documentRef.createElement('h2');
    title.id = 'dpr-feedback-heading';
    title.textContent = '公开反馈';
    applyStyles(title, {
      margin: '0 40px 8px 0',
      fontSize: '24px',
      lineHeight: '32px',
      fontWeight: '700',
    });

    const intro = documentRef.createElement('p');
    intro.textContent = '提交后会公开发布到 GitHub Issues，请不要填写隐私或敏感信息。';
    applyStyles(intro, {
      margin: '0 0 20px',
      color: '#475467',
      fontSize: '14px',
      lineHeight: '22px',
    });

    const typeTitle = documentRef.createElement('div');
    typeTitle.id = 'dpr-feedback-types-label';
    typeTitle.textContent = '反馈类型';
    applyStyles(typeTitle, {
      margin: '0 0 10px',
      fontSize: '14px',
      lineHeight: '20px',
      fontWeight: '600',
    });

    const typeWrap = documentRef.createElement('div');
    typeWrap.setAttribute('role', 'group');
    typeWrap.setAttribute('aria-labelledby', 'dpr-feedback-types-label');
    applyStyles(typeWrap, {
      display: 'flex',
      flexWrap: 'wrap',
      gap: '10px',
      marginBottom: '18px',
    });

    const typeInputs = ISSUE_TYPES.map((item) => createTypeCheckbox(documentRef, item));
    typeInputs.forEach(({ label }) => typeWrap.appendChild(label));

    const titleLabel = documentRef.createElement('label');
    titleLabel.htmlFor = 'dpr-feedback-title-input';
    titleLabel.textContent = '标题';
    applyStyles(titleLabel, {
      display: 'block',
      margin: '0 0 8px',
      fontSize: '14px',
      lineHeight: '20px',
      fontWeight: '600',
    });

    const titleInput = documentRef.createElement('input');
    titleInput.id = 'dpr-feedback-title-input';
    titleInput.type = 'text';
    titleInput.placeholder = '例如：会议标签切换后计数不刷新';
    applyStyles(titleInput, {
      width: '100%',
      padding: '11px 12px',
      margin: '0 0 18px',
      border: '1px solid #d0d5dd',
      borderRadius: '8px',
      fontSize: '14px',
      lineHeight: '20px',
      boxSizing: 'border-box',
    });
    titleInput.addEventListener('input', () => {
      state.attemptedSubmit = true;
      renderValidationState();
    });

    const titlePreview = documentRef.createElement('div');
    titlePreview.id = 'dpr-feedback-title-preview';
    applyStyles(titlePreview, {
      margin: '-10px 0 18px',
      color: '#667085',
      fontSize: '12px',
      lineHeight: '18px',
      overflowWrap: 'anywhere',
    });

    const contentLabel = documentRef.createElement('label');
    contentLabel.htmlFor = 'dpr-feedback-content-input';
    contentLabel.textContent = '内容';
    applyStyles(contentLabel, {
      display: 'block',
      margin: '0 0 8px',
      fontSize: '14px',
      lineHeight: '20px',
      fontWeight: '600',
    });

    const contentInput = documentRef.createElement('textarea');
    contentInput.id = 'dpr-feedback-content-input';
    contentInput.placeholder = '请直接写问题、现象、建议或缺失的数据。';
    applyStyles(contentInput, {
      width: '100%',
      minHeight: '180px',
      padding: '12px',
      border: '1px solid #d0d5dd',
      borderRadius: '8px',
      resize: 'vertical',
      fontSize: '14px',
      lineHeight: '22px',
      boxSizing: 'border-box',
    });
    contentInput.addEventListener('input', () => {
      state.attemptedSubmit = true;
      renderValidationState();
    });

    const confirmRow = documentRef.createElement('label');
    applyStyles(confirmRow, {
      display: 'flex',
      alignItems: 'flex-start',
      gap: '10px',
      marginTop: '18px',
      color: '#101828',
      fontSize: '14px',
      lineHeight: '22px',
      cursor: 'pointer',
    });

    const confirmInput = documentRef.createElement('input');
    confirmInput.id = 'dpr-feedback-public-confirm';
    confirmInput.type = 'checkbox';
    confirmInput.style.margin = '3px 0 0';
    confirmInput.addEventListener('change', () => {
      state.attemptedSubmit = true;
      renderValidationState();
    });

    const confirmText = documentRef.createElement('span');
    confirmText.textContent = '我已知晓这会公开提交到 GitHub Issues，任何人都可能看到。';

    confirmRow.appendChild(confirmInput);
    confirmRow.appendChild(confirmText);

    const status = documentRef.createElement('div');
    status.id = 'dpr-feedback-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    applyStyles(status, {
      minHeight: '22px',
      marginTop: '16px',
      fontSize: '14px',
      lineHeight: '22px',
      color: '#344054',
    });

    const submitButton = documentRef.createElement('button');
    submitButton.id = 'dpr-feedback-submit';
    submitButton.type = 'button';
    submitButton.textContent = '公开提交反馈';
    applyStyles(submitButton, {
      width: '100%',
      marginTop: '18px',
      padding: '12px 16px',
      border: '0',
      borderRadius: '8px',
      background: '#1d4ed8',
      color: '#ffffff',
      fontSize: '15px',
      lineHeight: '22px',
      fontWeight: '600',
      cursor: 'pointer',
    });
    submitButton.addEventListener('click', handleSubmit);

    panel.appendChild(closeButton);
    panel.appendChild(title);
    panel.appendChild(intro);
    panel.appendChild(typeTitle);
    panel.appendChild(typeWrap);
    panel.appendChild(titleLabel);
    panel.appendChild(titleInput);
    panel.appendChild(titlePreview);
    panel.appendChild(contentLabel);
    panel.appendChild(contentInput);
    panel.appendChild(confirmRow);
    panel.appendChild(status);
    panel.appendChild(submitButton);
    overlay.appendChild(panel);

    return {
      overlay,
      refs: {
        panel,
        closeButton,
        typeInputs: typeInputs.map((item) => item.input),
        titleInput,
        titlePreview,
        contentInput,
        confirmInput,
        status,
        submitButton,
      },
    };
  };

  const open = (prefill = {}) => {
    if (!hasDom()) return null;
    close({ immediate: true, restoreFocus: false });

    const built = buildModal();
    if (!built) return null;

    state.overlay = built.overlay;
    state.refs = built.refs;
    state.attemptedSubmit = false;
    state.submitting = false;
    state.submitted = false;
    state.submittedLabel = '';
    state.pendingDraftUrl = '';
    state.isClosing = false;
    state.restoreFocus = root.document.activeElement || null;
    state.bodyOverflow = root.document.body ? root.document.body.style.overflow || '' : '';

    state.keydownHandler = (event) => {
      if (event && event.key === 'Escape' && !state.submitting) close();
    };
    root.document.addEventListener('keydown', state.keydownHandler);

    if (root.document.body) {
      root.document.body.appendChild(state.overlay);
      root.document.body.style.overflow = 'hidden';
    }

    const reveal = () => {
      state.openFrame = null;
      if (state.overlay !== built.overlay || state.isClosing) return;
      applyFeedbackMotionStyles(built.overlay, built.refs.panel, true);
    };
    if (prefersReducedMotion()) {
      reveal();
    } else if (typeof root.requestAnimationFrame === 'function') {
      built.overlay.getBoundingClientRect();
      state.openFrame = root.requestAnimationFrame(reveal);
    } else {
      state.openFrame = root.setTimeout(reveal, 0);
    }

    const types = normalizeSelectedTypes(prefill.types);
    state.refs.typeInputs.forEach((input) => {
      input.checked = types.includes(input.value);
    });
    state.refs.titleInput.value = normalizeInlineText(prefill.title || '');
    state.refs.contentInput.value = normalizeText(prefill.content || '');
    state.refs.confirmInput.checked = Boolean(prefill.confirmPublic);

    renderValidationState();
    const focusTarget = state.refs.titleInput;
    if (focusTarget && typeof focusTarget.focus === 'function') {
      focusTarget.focus();
    }
    return state.overlay;
  };

  return {
    open,
    close,
    __test: {
      ISSUE_TYPES,
      TARGET_OWNER,
      TARGET_REPO,
      FEEDBACK_ANIMATION_MS,
      getFeedbackMotionStyles,
      normalizeText,
      normalizeInlineText,
      normalizeSelectedTypes,
      stripExistingTypePrefix,
      buildIssueTitle,
      buildIssueBody,
      validateFeedbackForm,
      buildIssueDraftUrl,
      readTokenFromStoredData,
      resolveGithubToken,
      classifyIssueError,
      submitIssueWithFallback,
    },
  };
});

if (typeof document !== 'undefined' && document.addEventListener) {
  document.addEventListener('dpr-open-feedback', function () {
    if (window.DPRFeedback && typeof window.DPRFeedback.open === 'function') {
      window.DPRFeedback.open();
    }
  });
}
