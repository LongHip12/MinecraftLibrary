(function () {

  document.querySelectorAll('.reply-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var msgId = btn.getAttribute('data-msg');
      var form = document.getElementById('reply-form-' + msgId);
      if (!form) return;
      var isOpen = form.style.display !== 'none';
      document.querySelectorAll('.reply-form-box').forEach(function (f) { f.style.display = 'none'; });
      form.style.display = isOpen ? 'none' : 'block';
      if (!isOpen) form.querySelector('textarea').focus();
    });
  });


  var _chatFiles = [];

  function formatBytes(b) {
    if (b < 1024) return b + ' B';
    if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB';
    return (b / 1024 / 1024).toFixed(1) + ' MB';
  }

  function renderChatFilePreviews() {
    var container = document.getElementById('chat-file-previews');
    if (!container) return;
    container.innerHTML = '';
    _chatFiles.forEach(function (file, idx) {
      var item = document.createElement('div');
      item.className = 'chat-file-preview-item';
      item.style.position = 'relative';

      if (file.type.startsWith('image/')) {
        var img = document.createElement('img');
        img.style.cssText = 'width:32px;height:32px;object-fit:cover;border-radius:4px;cursor:pointer;';
        img.title = 'Click to edit image';
        var reader = new FileReader();
        (function(capturedIdx, capturedName) {
          reader.onload = function (e) {
            var dataUrl = e.target.result;
            img.src = dataUrl;
            img.onclick = function () {
              if (typeof window.openFSEditor === 'function') {
                window.openFSEditor(dataUrl, function (editedDataUrl) {
                  fetch(editedDataUrl).then(function (res) { return res.blob(); }).then(function (blob) {
                    _chatFiles[capturedIdx] = new File([blob], capturedName, { type: blob.type });
                    renderChatFilePreviews();
                  });
                });
              }
            };
          };
        })(idx, file.name);
        reader.readAsDataURL(file);
        item.appendChild(img);
      } else {
        var icon = document.createElement('span');
        icon.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>';
        item.appendChild(icon);
      }

      var name = document.createElement('span');
      name.textContent = file.name.length > 20 ? file.name.slice(0, 18) + '…' : file.name;
      item.appendChild(name);

      var size = document.createElement('span');
      size.className = 'attach-size';
      size.textContent = formatBytes(file.size);
      item.appendChild(size);

      var xBtn = document.createElement('button');
      xBtn.type = 'button';
      xBtn.className = 'chat-file-remove';
      xBtn.title = 'Remove';
      xBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>';
      xBtn.addEventListener('click', function () {
        _chatFiles.splice(idx, 1);
        renderChatFilePreviews();
      });
      item.appendChild(xBtn);
      container.appendChild(item);
    });
  }

  function _updateChatAttachBtn() {
    var label = document.getElementById('chat-attach-label');
    var moreBtn = document.getElementById('chat-attach-more-btn');
    if (!label) return;
    if (_chatFiles.length > 0) {
      label.style.display = 'none';
      if (moreBtn) { moreBtn.style.display = 'flex'; moreBtn.title = 'Add more files (' + _chatFiles.length + ' selected)'; }
    } else {
      label.style.display = '';
      if (moreBtn) moreBtn.style.display = 'none';
    }
  }

  window.previewChatFiles = function (input) {
    Array.from(input.files).forEach(function (file) {
      _chatFiles.push(file);
    });
    input.value = '';
    renderChatFilePreviews();
    _updateChatAttachBtn();
  };

  window.getChatFiles = function () { return _chatFiles; };
  window.clearChatFiles = function () { _chatFiles = []; renderChatFilePreviews(); _updateChatAttachBtn(); };


  function initFileInput(input, previewArea) {
    if (!input) return;
    input.addEventListener('change', function () {
      previewArea.innerHTML = '';
      var files = Array.from(input.files);
      if (files.length === 0) return;
      files.forEach(function (file) {
        var item = document.createElement('div');
        item.className = 'attach-preview-item';
        if (file.type.startsWith('image/')) {
          var img = document.createElement('img');
          img.className = 'attach-preview-img';
          var reader = new FileReader();
          reader.onload = function (e) { img.src = e.target.result; };
          reader.readAsDataURL(file);
          item.appendChild(img);
        } else {
          item.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>';
        }
        var name = document.createElement('span');
        name.textContent = file.name.length > 24 ? file.name.slice(0, 22) + '…' : file.name;
        item.appendChild(name);
        var size = document.createElement('span');
        size.className = 'attach-size';
        size.textContent = formatBytes(file.size);
        item.appendChild(size);
        previewArea.appendChild(item);
      });
    });
  }

  var mainFileInput = document.getElementById('msg-files');
  var mainPreview = document.getElementById('msg-files-preview');
  if (mainFileInput && mainPreview) initFileInput(mainFileInput, mainPreview);

  document.querySelectorAll('.reply-files-input').forEach(function (inp) {
    var previewArea = inp.closest('.reply-form-box').querySelector('.reply-files-preview');
    if (previewArea) initFileInput(inp, previewArea);
  });


  var _postFiles = [];

  function renderPostFilePreviews() {
    var container = document.getElementById('post-files-preview');
    if (!container) return;
    container.innerHTML = '';
    _postFiles.forEach(function(file, idx) {
      var item = document.createElement('div');
      item.className = 'attach-preview-item';
      item.style.position = 'relative';
      if (file.type.startsWith('image/')) {
        var img = document.createElement('img');
        img.className = 'attach-preview-img';
        var reader = new FileReader();
        reader.onload = function(e) { img.src = e.target.result; };
        reader.readAsDataURL(file);
        item.appendChild(img);
      } else {
        var icon = document.createElement('span');
        icon.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>';
        item.appendChild(icon);
      }
      var name = document.createElement('span');
      name.textContent = file.name.length > 24 ? file.name.slice(0, 22) + '…' : file.name;
      item.appendChild(name);
      var size = document.createElement('span');
      size.className = 'attach-size';
      size.textContent = formatBytes(file.size);
      item.appendChild(size);
      var xBtn = document.createElement('button');
      xBtn.type = 'button';
      xBtn.className = 'chat-file-remove';
      xBtn.title = 'Remove';
      xBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>';
      xBtn.addEventListener('click', function() {
        _postFiles.splice(idx, 1);
        renderPostFilePreviews();
        _updatePostAttachBtn();
      });
      item.appendChild(xBtn);
      container.appendChild(item);
    });
  }

  function _updatePostAttachBtn() {
    var label = document.getElementById('post-attach-label');
    var moreBtn = document.getElementById('post-attach-more-btn');
    if (!label) return;
    if (_postFiles.length > 0) {
      label.style.display = 'none';
      if (moreBtn) moreBtn.style.display = 'inline-flex';
    } else {
      label.style.display = '';
      if (moreBtn) moreBtn.style.display = 'none';
    }
  }

  window.previewPostFiles = function(input) {
    Array.from(input.files).forEach(function(file) { _postFiles.push(file); });
    input.value = '';
    renderPostFilePreviews();
    _updatePostAttachBtn();
  };

  window.getPostFiles = function() { return _postFiles; };


  var modal = document.getElementById('dl-warning-modal');
  var okBtn = document.getElementById('dl-ok-btn');
  var cancelBtn = document.getElementById('dl-cancel-btn');
  if (modal && okBtn && cancelBtn) {
    okBtn.addEventListener('click', function () {
      window.location.href = okBtn.getAttribute('data-href');
    });
    cancelBtn.addEventListener('click', function () {
      history.back();
    });
    setTimeout(function () { modal.classList.add('visible'); }, 80);
  }


  document.querySelectorAll('.toggle-replies-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var targetId = btn.getAttribute('data-target');
      var list = document.getElementById(targetId);
      if (!list) return;
      var isOpen = list.style.display !== 'none' && list.style.display !== '';
      list.style.display = isOpen ? 'none' : 'flex';
      var svg = btn.querySelector('svg');
      if (svg) svg.style.transform = isOpen ? '' : 'rotate(180deg)';
      var span = btn.querySelector('span');
      if (span) {
        var count = list.querySelectorAll('.reply-card, .subreply-card').length;
        span.textContent = isOpen ? (count === 1 ? '1 reply' : count + ' replies') : 'Hide ' + (count === 1 ? '1 reply' : count + ' replies');
      }
    });
  });


  var currentCat = new URLSearchParams(window.location.search).get('category') || '';
  document.querySelectorAll('.forum-cat-item').forEach(function (el) {
    if (el.getAttribute('data-cat') === currentCat) el.classList.add('active');
  });


  var nlForum = document.getElementById('nl-forum');
  var ndForum = document.getElementById('nd-forum');
  if (window.location.pathname.startsWith('/forum')) {
    if (nlForum) nlForum.classList.add('active');
    if (ndForum) ndForum.classList.add('active');
  }


  /* ===== TOAST ===== */
  window.showToast = function(msg, type, duration) {
    var ct = document.getElementById('toast-container');
    if (!ct) { ct = document.createElement('div'); ct.id = 'toast-container'; document.body.appendChild(ct); }
    var item = document.createElement('div');
    item.className = 'toast-item' + (type ? ' ' + type : '');
    item.textContent = msg;
    ct.appendChild(item);
    setTimeout(function() { item.classList.add('hiding'); setTimeout(function() { item.remove(); }, 320); }, duration || 3000);
  };

  /* ===== ACTION PANEL ===== */
  var _AP = null;
  var _APState = { msgId: null, postId: null, content: '', canDelete: false, canReport: false };

  var _QREACTS = [
    { e: '\u2764\ufe0f', c: '2764', l: 'Love' },
    { e: '\U0001f602', c: '1f602', l: 'Haha' },
    { e: '\U0001f62e', c: '1f62e', l: 'Wow' },
    { e: '\U0001f622', c: '1f622', l: 'Sad' },
    { e: '\U0001f620', c: '1f620', l: 'Angry' },
    { e: '\U0001f44d', c: '1f44d', l: 'Like' },
  ];

  // actual emoji chars
  var _QR = [
    { e: '\u2764\uFE0F', c: '2764', l: 'Love' },
    { e: '\uD83D\uDE02', c: '1f602', l: 'Haha' },
    { e: '\uD83D\uDE2E', c: '1f62e', l: 'Wow' },
    { e: '\uD83D\uDE22', c: '1f622', l: 'Sad' },
    { e: '\uD83D\uDE20', c: '1f620', l: 'Angry' },
    { e: '\uD83D\uDC4D', c: '1f44d', l: 'Like' },
  ];

  function _buildAP() {
    var p = document.createElement('div');
    p.className = 'msg-action-panel';
    p.id = '_map';
    p.style.display = 'none';

    var qr = document.createElement('div');
    qr.className = 'msg-qr-row';
    _QR.forEach(function(r) {
      var b = document.createElement('button');
      b.className = 'msg-qr-btn';
      b.title = r.l;
      b.innerHTML = '<img src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/' + r.c + '.png" alt="' + r.e + '">';
      b.onclick = function(e) {
        e.stopPropagation();
        if (window.toggleMsgReact && _APState.postId && _APState.msgId) window.toggleMsgReact(_APState.postId, _APState.msgId, r.e);
        _hideAP();
      };
      qr.appendChild(b);
    });
    var mb = document.createElement('button');
    mb.className = 'msg-qr-btn msg-qr-more';
    mb.title = 'More reactions';
    mb.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M8 14s1.5 2 4 2 4-2 4-2"></path><line x1="9" y1="9" x2="9.01" y2="9"></line><line x1="15" y1="9" x2="15.01" y2="9"></line><line x1="12" y1="6" x2="12" y2="10"></line></svg>';
    mb.onclick = function(e) {
      e.stopPropagation();
      _hideAP();
      var ab = document.querySelector('[data-react-add-msg="' + _APState.msgId + '"]');
      if (ab) ab.click();
      else if (window.toggleForumReactPicker && _APState.postId && _APState.msgId) {
        var fe = { preventDefault: function(){}, stopPropagation: function(){}, clientX: window.innerWidth/2, clientY: window.innerHeight/2, target: document.body };
        window.toggleForumReactPicker(fe, 'msg', _APState.postId, _APState.msgId);
      }
    };
    qr.appendChild(mb);
    p.appendChild(qr);

    function _mkItem(svgHtml, label, cls, onClick) {
      var b = document.createElement('button');
      b.className = 'msg-action-item' + (cls ? ' ' + cls : '');
      b.innerHTML = svgHtml + '<span>' + label + '</span>';
      b.onclick = function() { _hideAP(); onClick(); };
      return b;
    }
    p.appendChild(_mkItem('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 17 4 12 9 7"></polyline><path d="M20 18v-2a4 4 0 0 0-4-4H4"></path></svg>', 'Reply', '', function() {
      var btn = document.querySelector('.reply-btn[data-msg="' + _APState.msgId + '"]');
      if (btn && window.triggerReply) window.triggerReply(btn);
    }));
    p.appendChild(_mkItem('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>', 'Copy', '', function() {
      if (!_APState.content) return;
      navigator.clipboard.writeText(_APState.content).then(function() { window.showToast('Copied!', 'success'); }).catch(function() {
        var ta = document.createElement('textarea'); ta.value = _APState.content; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); window.showToast('Copied!', 'success');
      });
    }));
    var delBtn = _mkItem('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"></path></svg>', 'Delete', 'danger', function() {
      if (window.deleteMsg && _APState.postId && _APState.msgId) window.deleteMsg(_APState.postId, _APState.msgId);
    });
    delBtn.id = '_apDel';
    p.appendChild(delBtn);

    var repBtn = _mkItem('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"></path><line x1="4" y1="22" x2="4" y2="15"></line></svg>', 'Report', '', function() {
      if (window.openReportModal && _APState.msgId) window.openReportModal('post', _APState.msgId, window.location.pathname + '#msg-' + _APState.msgId);
    });
    repBtn.id = '_apRep';
    p.appendChild(repBtn);

    document.body.appendChild(p);
    document.addEventListener('click', function(e) { if (_AP && !_AP.contains(e.target)) _hideAP(); }, true);
    return p;
  }

  function _showAP(x, y, msgId, postId, content, canDelete, canReport) {
    Object.assign(_APState, { msgId: msgId, postId: postId, content: content, canDelete: canDelete, canReport: canReport });
    if (!_AP) _AP = _buildAP();
    _AP.style.display = 'block';
    var del = document.getElementById('_apDel'), rep = document.getElementById('_apRep');
    if (del) del.style.display = canDelete ? '' : 'none';
    if (rep) rep.style.display = canReport ? '' : 'none';
    var pw = _AP.offsetWidth || 200, ph = _AP.offsetHeight || 260;
    var lx = Math.min(x, window.innerWidth - pw - 8);
    var ly = Math.min(y, window.innerHeight - ph - 8);
    if (ly < 8) ly = 8;
    _AP.style.left = lx + 'px';
    _AP.style.top = ly + 'px';
  }

  function _hideAP() { if (_AP) _AP.style.display = 'none'; }

  window._showMsgActionPanel = _showAP;
  window._hideMsgActionPanel = _hideAP;

  function _initMsgInteractions() {
    document.querySelectorAll('.message-card').forEach(function(card) {
      if (card.dataset.apInit) return;
      card.dataset.apInit = '1';
      var msgId = card.id.replace('msg-', '');
      var postId = card.dataset.postId || '';
      var bodyEl = card.querySelector('.msg-body');
      var bubble = card.querySelector('.msg-bubble');
      var content = bodyEl ? bodyEl.textContent.trim() : '';
      var isOwn = card.classList.contains('own-msg');
      var canDelete = card.querySelector('.delete-msg-btn') !== null;
      var canReport = !!card.querySelector('.reply-btn[style*="rgba(250,80,80"]');
      if (!bubble) return;

      var dot = document.createElement('button');
      dot.className = 'msg-3dot-hover';
      dot.title = 'Options';
      dot.setAttribute('type', 'button');
      dot.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="12" cy="19" r="1.8"/></svg>';
      dot.onclick = function(e) {
        e.stopPropagation();
        var rect = bubble.getBoundingClientRect();
        var x = isOwn ? rect.left - 210 : rect.right + 6;
        var y = rect.top + rect.height / 2 - 60;
        _showAP(x, y, msgId, postId, content, canDelete, canReport);
      };
      card.style.position = 'relative';
      card.appendChild(dot);

      var _lp = null;
      bubble.addEventListener('touchstart', function(e) {
        _lp = setTimeout(function() {
          var t = e.touches[0];
          _showAP(Math.max(8, t.clientX - 95), Math.max(8, t.clientY - 280), msgId, postId, content, canDelete, canReport);
        }, 550);
      }, { passive: true });
      bubble.addEventListener('touchend', function() { clearTimeout(_lp); });
      bubble.addEventListener('touchmove', function() { clearTimeout(_lp); });
      bubble.addEventListener('contextmenu', function(e) {
        e.preventDefault();
        _showAP(e.clientX, e.clientY - 120, msgId, postId, content, canDelete, canReport);
      });
    });
  }

  /* ===== CUSTOM SELECTS ===== */
  window._initCustomSelects = function() {
    document.querySelectorAll('select[data-custom]').forEach(function(sel) {
      if (sel.dataset.customDone) return;
      sel.dataset.customDone = '1';
      sel.style.display = 'none';
      var wrap = document.createElement('div');
      wrap.className = 'custom-select-wrap';
      sel.parentNode.insertBefore(wrap, sel);
      wrap.appendChild(sel);

      var curText = sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].text : 'Select…';
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'custom-select-btn';
      btn.innerHTML = '<span class="cs-lbl">' + curText + '</span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>';
      wrap.insertBefore(btn, sel);

      var drop = document.createElement('div');
      drop.className = 'custom-select-drop';
      Array.from(sel.options).forEach(function(opt, i) {
        var item = document.createElement('div');
        item.className = 'custom-select-opt' + (i === sel.selectedIndex ? ' selected' : '');
        item.textContent = opt.text;
        item.dataset.val = opt.value;
        item.addEventListener('click', function() {
          sel.value = opt.value;
          sel.dispatchEvent(new Event('change'));
          btn.querySelector('.cs-lbl').textContent = opt.text;
          drop.querySelectorAll('.custom-select-opt').forEach(function(o) { o.classList.remove('selected'); });
          item.classList.add('selected');
          drop.classList.remove('open');
          btn.classList.remove('open');
        });
        drop.appendChild(item);
      });
      wrap.appendChild(drop);

      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var isOpen = drop.classList.contains('open');
        document.querySelectorAll('.custom-select-drop.open').forEach(function(d) { d.classList.remove('open'); });
        document.querySelectorAll('.custom-select-btn.open').forEach(function(b) { b.classList.remove('open'); });
        if (!isOpen) { drop.classList.add('open'); btn.classList.add('open'); }
      });
      document.addEventListener('click', function() { drop.classList.remove('open'); btn.classList.remove('open'); });
    });
  };

  /* ===== FULL-SCREEN IMAGE EDITOR ===== */
  (function() {
    var _fse = null;
    var _fseCanvas = null;
    var _fseCtx = null;
    var _fseMode = 'draw';
    var _fseColor = '#fa5050';
    var _fseBrushSize = 4;
    var _fseFontSize = 24;
    var _fseText = 'Text';
    var _fseDrawing = false;
    var _fseLX = 0, _fseLY = 0;
    var _fseUndoStack = [];
    var _fseScale = 1;
    var _fseOnSave = null;

    function _saveUndo() {
      _fseUndoStack.push(_fseCanvas.toDataURL());
      if (_fseUndoStack.length > 30) _fseUndoStack.shift();
    }

    window.openFSEditor = function(imgSrc, onSave) {
      _fseOnSave = onSave;
      if (!_fse) _buildFSE();
      _fseUndoStack = [];
      _fseScale = 1;
      var img = new Image();
      img.onload = function() {
        var maxW = window.innerWidth - 32, maxH = window.innerHeight - 120;
        var scale = Math.min(1, maxW / img.width, maxH / img.height);
        _fseCanvas.width = Math.round(img.width * scale);
        _fseCanvas.height = Math.round(img.height * scale);
        _fseCtx.drawImage(img, 0, 0, _fseCanvas.width, _fseCanvas.height);
        _updateZoomLabel();
      };
      img.src = imgSrc;
      _fse.classList.add('open');
    };

    function _buildFSE() {
      _fse = document.createElement('div');
      _fse.id = 'fs-img-editor';

      var tb = document.createElement('div');
      tb.className = 'fse-toolbar';

      function _toolBtn(label, svg, mode) {
        var b = document.createElement('button');
        b.className = 'fse-tool-btn' + (_fseMode === mode ? ' active' : '');
        b.innerHTML = (svg || '') + label;
        b.dataset.mode = mode;
        b.onclick = function() {
          _fseMode = mode;
          tb.querySelectorAll('.fse-tool-btn[data-mode]').forEach(function(x) { x.classList.toggle('active', x.dataset.mode === mode); });
          _fseCanvas.style.cursor = mode === 'text' ? 'text' : mode === 'eraser' ? 'cell' : 'crosshair';
        };
        return b;
      }

      tb.appendChild(_toolBtn('Draw', '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>', 'draw'));
      tb.appendChild(_toolBtn('Eraser', '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 20H7L3 16l10-10 7 7-1.5 1.5"/><path d="M6.5 17.5l5-5"/></svg>', 'eraser'));
      tb.appendChild(_toolBtn('Text', '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 7 4 4 20 4 20 7"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/></svg>', 'text'));

      var sep1 = document.createElement('div'); sep1.className = 'fse-sep'; tb.appendChild(sep1);

      var undoBtn = document.createElement('button');
      undoBtn.className = 'fse-tool-btn';
      undoBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.5"/></svg>Undo';
      undoBtn.onclick = function() {
        if (!_fseUndoStack.length) return;
        var prev = _fseUndoStack.pop();
        var img2 = new Image();
        img2.onload = function() { _fseCtx.clearRect(0, 0, _fseCanvas.width, _fseCanvas.height); _fseCtx.drawImage(img2, 0, 0); };
        img2.src = prev;
      };
      tb.appendChild(undoBtn);

      var sep2 = document.createElement('div'); sep2.className = 'fse-sep'; tb.appendChild(sep2);

      var zoomIn = document.createElement('button');
      zoomIn.className = 'fse-tool-btn';
      zoomIn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>';
      zoomIn.onclick = function() { _fseScale = Math.min(4, _fseScale + 0.25); _applyZoom(); };
      tb.appendChild(zoomIn);

      var zoomLabel = document.createElement('span');
      zoomLabel.className = 'fse-zoom-val';
      zoomLabel.id = 'fse-zoom-lbl';
      zoomLabel.textContent = '100%';
      tb.appendChild(zoomLabel);

      var zoomOut = document.createElement('button');
      zoomOut.className = 'fse-tool-btn';
      zoomOut.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/></svg>';
      zoomOut.onclick = function() { _fseScale = Math.max(0.25, _fseScale - 0.25); _applyZoom(); };
      tb.appendChild(zoomOut);

      var sep3 = document.createElement('div'); sep3.className = 'fse-sep'; tb.appendChild(sep3);

      var saveBtn = document.createElement('button');
      saveBtn.className = 'fse-tool-btn';
      saveBtn.style.cssText = 'background:rgba(250,80,80,.18);border-color:var(--primary);color:var(--primary);margin-left:auto;';
      saveBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>Save';
      saveBtn.onclick = function() {
        var dataUrl = _fseCanvas.toDataURL('image/png');
        _fse.classList.remove('open');
        if (_fseOnSave) _fseOnSave(dataUrl);
      };
      tb.appendChild(saveBtn);

      var cancelBtn = document.createElement('button');
      cancelBtn.className = 'fse-tool-btn';
      cancelBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>Cancel';
      cancelBtn.onclick = function() { _fse.classList.remove('open'); };
      tb.appendChild(cancelBtn);

      _fse.appendChild(tb);

      var area = document.createElement('div');
      area.className = 'fse-canvas-area';
      _fseCanvas = document.createElement('canvas');
      _fseCanvas.id = 'fse-canvas';
      area.appendChild(_fseCanvas);
      _fse.appendChild(area);
      _fseCtx = _fseCanvas.getContext('2d');

      var bot = document.createElement('div');
      bot.className = 'fse-bottom';

      var colLabel = document.createElement('span'); colLabel.className = 'fse-label'; colLabel.textContent = 'Color:'; bot.appendChild(colLabel);
      var colInput = document.createElement('input'); colInput.type = 'color'; colInput.value = _fseColor; colInput.className = 'fse-color-input';
      colInput.oninput = function() { _fseColor = colInput.value; };
      bot.appendChild(colInput);

      var szLabel = document.createElement('span'); szLabel.className = 'fse-label'; szLabel.textContent = 'Brush:'; bot.appendChild(szLabel);
      var szInput = document.createElement('input'); szInput.type = 'number'; szInput.min = 1; szInput.max = 80; szInput.value = _fseBrushSize; szInput.className = 'fse-size-input';
      szInput.oninput = function() { _fseBrushSize = parseInt(szInput.value) || 4; };
      bot.appendChild(szInput);

      var fsLabel = document.createElement('span'); fsLabel.className = 'fse-label'; fsLabel.textContent = 'Font:'; bot.appendChild(fsLabel);
      var fsInput = document.createElement('input'); fsInput.type = 'number'; fsInput.min = 8; fsInput.max = 200; fsInput.value = _fseFontSize; fsInput.className = 'fse-size-input fse-font-input';
      fsInput.oninput = function() { _fseFontSize = parseInt(fsInput.value) || 24; };
      bot.appendChild(fsInput);

      var txLabel = document.createElement('span'); txLabel.className = 'fse-label'; txLabel.textContent = 'Text:'; bot.appendChild(txLabel);
      var txInput = document.createElement('input'); txInput.type = 'text'; txInput.value = _fseText; txInput.className = 'fse-text-input'; txInput.placeholder = 'Text to add…';
      txInput.oninput = function() { _fseText = txInput.value; };
      bot.appendChild(txInput);

      _fse.appendChild(bot);
      document.body.appendChild(_fse);

      _fseCtx = _fseCanvas.getContext('2d');

      function _pos(e) {
        var rect = _fseCanvas.getBoundingClientRect();
        var src = e.touches ? e.touches[0] : e;
        return { x: (src.clientX - rect.left) / _fseScale, y: (src.clientY - rect.top) / _fseScale };
      }

      _fseCanvas.addEventListener('mousedown', function(e) {
        _saveUndo();
        _fseDrawing = true;
        var p = _pos(e);
        if (_fseMode === 'text') {
          _fseCtx.font = 'bold ' + _fseFontSize + 'px sans-serif';
          _fseCtx.fillStyle = _fseColor;
          _fseCtx.fillText(_fseText, p.x, p.y);
          _fseDrawing = false;
        } else {
          _fseLX = p.x; _fseLY = p.y;
          _fseCtx.beginPath();
          _fseCtx.moveTo(p.x, p.y);
        }
      });
      _fseCanvas.addEventListener('mousemove', function(e) {
        if (!_fseDrawing) return;
        var p = _pos(e);
        _fseCtx.globalCompositeOperation = _fseMode === 'eraser' ? 'destination-out' : 'source-over';
        _fseCtx.strokeStyle = _fseColor;
        _fseCtx.lineWidth = _fseBrushSize;
        _fseCtx.lineCap = 'round';
        _fseCtx.lineJoin = 'round';
        _fseCtx.lineTo(p.x, p.y);
        _fseCtx.stroke();
        _fseCtx.beginPath();
        _fseCtx.moveTo(p.x, p.y);
        _fseLX = p.x; _fseLY = p.y;
      });
      document.addEventListener('mouseup', function() {
        if (_fseDrawing) { _fseCtx.globalCompositeOperation = 'source-over'; _fseDrawing = false; }
      });
      _fseCanvas.addEventListener('touchstart', function(e) {
        e.preventDefault();
        _saveUndo(); _fseDrawing = true;
        var p = _pos(e);
        if (_fseMode === 'text') {
          _fseCtx.font = 'bold ' + _fseFontSize + 'px sans-serif';
          _fseCtx.fillStyle = _fseColor;
          _fseCtx.fillText(_fseText, p.x, p.y);
          _fseDrawing = false;
        } else {
          _fseLX = p.x; _fseLY = p.y;
          _fseCtx.beginPath(); _fseCtx.moveTo(p.x, p.y);
        }
      }, { passive: false });
      _fseCanvas.addEventListener('touchmove', function(e) {
        e.preventDefault();
        if (!_fseDrawing) return;
        var p = _pos(e);
        _fseCtx.globalCompositeOperation = _fseMode === 'eraser' ? 'destination-out' : 'source-over';
        _fseCtx.strokeStyle = _fseColor; _fseCtx.lineWidth = _fseBrushSize; _fseCtx.lineCap = 'round'; _fseCtx.lineJoin = 'round';
        _fseCtx.lineTo(p.x, p.y); _fseCtx.stroke(); _fseCtx.beginPath(); _fseCtx.moveTo(p.x, p.y);
      }, { passive: false });
      _fseCanvas.addEventListener('touchend', function() { _fseCtx.globalCompositeOperation = 'source-over'; _fseDrawing = false; });
    }

    function _applyZoom() {
      var z = document.getElementById('fse-zoom-lbl');
      if (z) z.textContent = Math.round(_fseScale * 100) + '%';
      if (_fseCanvas) {
        _fseCanvas.style.width = (_fseCanvas.width * _fseScale) + 'px';
        _fseCanvas.style.height = (_fseCanvas.height * _fseScale) + 'px';
      }
    }
    function _updateZoomLabel() { _applyZoom(); }
  })();

  /* ===== INIT ===== */
  (function _msginit() {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function() { _initMsgInteractions(); window._initCustomSelects && window._initCustomSelects(); });
    } else {
      _initMsgInteractions();
      window._initCustomSelects && window._initCustomSelects();
    }
  })();
  

})();
