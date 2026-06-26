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
    var _fse = null, _fseCanvas = null, _fseCtx = null;
    var _fseMode = 'draw';
    var _fseColor = '#fa5050';
    var _fseBrushSize = 6;
    var _fseMosaicSize = 16;
    var _fseShape = 'rect';
    var _fseDrawing = false;
    var _fseSX = 0, _fseSY = 0;
    var _fseUndoStack = [];
    var _fseScale = 1;
    var _fseOnSave = null;
    var _fseSnap = null;
    var _fseArea = null;
    var _fseBot = null;
    var _fseTb = null;

    var PRESET_COLORS = ['#ffffff','#fa5050','#ff9900','#ffee00','#4cff6e','#00d4ff','#a855f7','#ff69b4','#000000'];
    var STICKERS = ['😀','😂','😍','🥰','😎','🤣','❤️','🔥','💯','👍','👏','🎉','✨','💪','😭','🤔','😅','🙏','💀','👀','🌈','⭐','💥','🎯','🍀','🦋','🎸','🏆','💎','🚀','🐱','🐶','🌸','🍕','🎮','🤡','👑','🫶','🤩','😈'];

    function _saveUndo() {
      _fseUndoStack.push(_fseCanvas.toDataURL());
      if (_fseUndoStack.length > 40) _fseUndoStack.shift();
    }

    window.openFSEditor = function(imgSrc, onSave) {
      _fseOnSave = onSave;
      if (!_fse) _buildFSE();
      _fseUndoStack = [];
      _fseScale = 1;
      _clearFloatingObjs();
      var img = new Image();
      img.onload = function() {
        var maxW = window.innerWidth - 32, maxH = window.innerHeight - 170;
        var sc = Math.min(1, maxW / img.width, maxH / img.height);
        _fseCanvas.width  = Math.round(img.width  * sc);
        _fseCanvas.height = Math.round(img.height * sc);
        _fseCtx.drawImage(img, 0, 0, _fseCanvas.width, _fseCanvas.height);
        _applyZoom();
      };
      img.src = imgSrc;
      _fse.classList.add('open');
    };

    function _clearFloatingObjs() {
      if (_fseArea) _fseArea.querySelectorAll('.fse-float-obj').forEach(function(e) { e.remove(); });
    }

    function _buildFSE() {
      _fse = document.createElement('div');
      _fse.id = 'fs-img-editor';

      /* ── TOOLBAR ── */
      _fseTb = document.createElement('div');
      _fseTb.className = 'fse-toolbar';

      function _toolBtn(svg, label, mode) {
        var b = document.createElement('button');
        b.className = 'fse-tool-btn' + (_fseMode === mode ? ' active' : '');
        b.innerHTML = svg + '<span>' + label + '</span>';
        b.dataset.mode = mode;
        b.title = label;
        b.onclick = function() { _setMode(mode); };
        return b;
      }
      var SVG_DRAW    = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>';
      var SVG_MOSAIC  = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>';
      var SVG_ERASER  = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 20H7L3 16 13 6l7 7-1.5 1.5"/><path d="M6.5 17.5l5-5"/></svg>';
      var SVG_TEXT    = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 7 4 4 20 4 20 7"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/></svg>';
      var SVG_STICKER = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>';
      var SVG_SHAPE   = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="3"/></svg>';
      var SVG_UNDO    = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.5"/></svg>';

      _fseTb.appendChild(_toolBtn(SVG_DRAW,   'Vẽ',    'draw'));
      _fseTb.appendChild(_toolBtn(SVG_MOSAIC, 'Khảm',  'mosaic'));
      _fseTb.appendChild(_toolBtn(SVG_ERASER, 'Xoá',   'eraser'));
      _fseTb.appendChild(_toolBtn(SVG_TEXT,   'Chữ',   'text'));
      _fseTb.appendChild(_toolBtn(SVG_STICKER,'Sticker','sticker'));
      _fseTb.appendChild(_toolBtn(SVG_SHAPE,  'Hình',  'shape'));

      function _sep() { var s=document.createElement('div'); s.className='fse-sep'; return s; }
      _fseTb.appendChild(_sep());

      var undoBtn = document.createElement('button');
      undoBtn.className = 'fse-tool-btn';
      undoBtn.innerHTML = SVG_UNDO + '<span>Hoàn tác</span>';
      undoBtn.onclick = function() {
        if (!_fseUndoStack.length) return;
        var img2 = new Image();
        img2.onload = function() { _fseCtx.clearRect(0,0,_fseCanvas.width,_fseCanvas.height); _fseCtx.drawImage(img2,0,0); };
        img2.src = _fseUndoStack.pop();
      };
      _fseTb.appendChild(undoBtn);
      _fseTb.appendChild(_sep());

      var zoomOutBtn = document.createElement('button');
      zoomOutBtn.className = 'fse-tool-btn fse-icon-btn';
      zoomOutBtn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/></svg>';
      zoomOutBtn.onclick = function() { _fseScale = Math.max(0.25, _fseScale - 0.25); _applyZoom(); };
      _fseTb.appendChild(zoomOutBtn);

      var zoomLbl = document.createElement('span'); zoomLbl.className = 'fse-zoom-val'; zoomLbl.textContent = '100%';
      _fseTb.appendChild(zoomLbl);

      var zoomInBtn = document.createElement('button');
      zoomInBtn.className = 'fse-tool-btn fse-icon-btn';
      zoomInBtn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>';
      zoomInBtn.onclick = function() { _fseScale = Math.min(4, _fseScale + 0.25); _applyZoom(); };
      _fseTb.appendChild(zoomInBtn);
      _fseTb.appendChild(_sep());

      var saveBtn = document.createElement('button');
      saveBtn.className = 'fse-tool-btn fse-save-btn';
      saveBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg><span>Lưu</span>';
      saveBtn.onclick = function() {
        _commitAllFloating(function() {
          var url = _fseCanvas.toDataURL('image/png');
          _fse.classList.remove('open');
          if (_fseOnSave) _fseOnSave(url);
        });
      };
      _fseTb.appendChild(saveBtn);

      var cancelBtn = document.createElement('button');
      cancelBtn.className = 'fse-tool-btn';
      cancelBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg><span>Huỷ</span>';
      cancelBtn.onclick = function() { _fse.classList.remove('open'); };
      _fseTb.appendChild(cancelBtn);

      _fse.appendChild(_fseTb);

      /* ── CANVAS AREA ── */
      _fseArea = document.createElement('div');
      _fseArea.className = 'fse-canvas-area';
      _fseCanvas = document.createElement('canvas');
      _fseCanvas.id = 'fse-canvas';
      _fseArea.appendChild(_fseCanvas);
      _fseCtx = _fseCanvas.getContext('2d');

      /* ── TEXT MODAL (center overlay) ── */
      var textModal = document.createElement('div');
      textModal.className = 'fse-text-modal';
      textModal.innerHTML =
        '<div class="fse-tm-title">Thêm chữ</div>' +
        '<textarea class="fse-tm-txt" placeholder="Nhập nội dung..." rows="3"></textarea>' +
        '<div class="fse-tm-row">' +
          '<label class="fse-tm-lbl">Màu</label>' +
          '<input type="color" class="fse-tm-color" value="#ffffff">' +
          '<label class="fse-tm-lbl">Cỡ</label>' +
          '<input type="number" class="fse-tm-size" value="36" min="8" max="300">' +
          '<label class="fse-tm-lbl">Font</label>' +
          '<select class="fse-tm-font">' +
            '<option value="sans-serif">Sans</option>' +
            '<option value="serif">Serif</option>' +
            '<option value="monospace">Mono</option>' +
            '<option value="cursive">Cursive</option>' +
            '<option value="fantasy">Fantasy</option>' +
          '</select>' +
          '<label class="fse-tm-lbl">Bold</label>' +
          '<input type="checkbox" class="fse-tm-bold" checked>' +
        '</div>' +
        '<div class="fse-tm-btns">' +
          '<button class="fse-btn-ok">OK</button>' +
          '<button class="fse-btn-cancel">Huỷ</button>' +
        '</div>';
      textModal.querySelector('.fse-btn-cancel').onclick = function() { textModal.classList.remove('open'); };
      textModal.querySelector('.fse-btn-ok').onclick = function() {
        var txt   = textModal.querySelector('.fse-tm-txt').value;
        var color = textModal.querySelector('.fse-tm-color').value;
        var size  = parseInt(textModal.querySelector('.fse-tm-size').value) || 36;
        var font  = textModal.querySelector('.fse-tm-font').value;
        var bold  = textModal.querySelector('.fse-tm-bold').checked;
        var cx    = parseFloat(textModal.dataset.cx) || _fseCanvas.width/2;
        var cy    = parseFloat(textModal.dataset.cy) || _fseCanvas.height/2;
        textModal.classList.remove('open');
        if (!txt.trim()) return;
        _spawnTextObj(txt, color, size, font, bold, cx, cy);
      };
      _fseArea.appendChild(textModal);

      /* ── STICKER PANEL (slides up from bottom) ── */
      var stickerPanel = document.createElement('div');
      stickerPanel.className = 'fse-sticker-panel';
      STICKERS.forEach(function(em) {
        var sb = document.createElement('button');
        sb.className = 'fse-sticker-btn';
        sb.textContent = em;
        sb.title = em;
        sb.onclick = function() { stickerPanel.classList.remove('open'); _spawnEmojiObj(em); };
        stickerPanel.appendChild(sb);
      });
      // Custom image upload
      var imgLabel = document.createElement('label');
      imgLabel.className = 'fse-sticker-upload-label';
      imgLabel.title = 'Chèn ảnh làm sticker';
      imgLabel.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg><span>Ảnh</span>';
      var imgInput = document.createElement('input');
      imgInput.type = 'file'; imgInput.accept = 'image/*'; imgInput.style.display = 'none';
      imgInput.onchange = function() {
        var f = imgInput.files[0]; if (!f) return;
        var r = new FileReader();
        r.onload = function(ev) { stickerPanel.classList.remove('open'); _spawnImgObj(ev.target.result); };
        r.readAsDataURL(f);
        imgInput.value = '';
      };
      imgLabel.appendChild(imgInput);
      stickerPanel.appendChild(imgLabel);
      _fseArea.appendChild(stickerPanel);

      _fse.appendChild(_fseArea);

      /* ── BOTTOM CONTEXTUAL BAR ── */
      _fseBot = document.createElement('div');
      _fseBot.className = 'fse-bottom';
      _fse.appendChild(_fseBot);

      document.body.appendChild(_fse);
      _buildBottomBar('draw');

      /* ── CANVAS EVENTS ── */
      function _pos(e) {
        var rect = _fseCanvas.getBoundingClientRect();
        var src  = e.touches ? e.touches[0] : e;
        return { x: (src.clientX - rect.left) / _fseScale, y: (src.clientY - rect.top) / _fseScale };
      }

      function _mosaicAt(px, py) {
        var sz = _fseMosaicSize;
        var x0 = Math.floor(px / sz) * sz, y0 = Math.floor(py / sz) * sz;
        var w  = Math.min(sz, _fseCanvas.width - x0), h = Math.min(sz, _fseCanvas.height - y0);
        if (w <= 0 || h <= 0) return;
        var d = _fseCtx.getImageData(x0, y0, w, h).data;
        var r=0,g=0,b=0,a=0,n=d.length/4;
        for (var i=0;i<d.length;i+=4){r+=d[i];g+=d[i+1];b+=d[i+2];a+=d[i+3];}
        r=Math.round(r/n);g=Math.round(g/n);b=Math.round(b/n);a=Math.round(a/n);
        _fseCtx.fillStyle='rgba('+r+','+g+','+b+','+(a/255)+')';
        _fseCtx.fillRect(x0,y0,w,h);
      }

      function _drawShapePreview(sx,sy,ex,ey) {
        _fseCtx.globalCompositeOperation = 'source-over';
        _fseCtx.strokeStyle = _fseColor;
        _fseCtx.lineWidth   = _fseBrushSize;
        _fseCtx.lineCap     = 'round';
        _fseCtx.lineJoin    = 'round';
        if (_fseShape === 'rect') {
          _fseCtx.beginPath(); _fseCtx.strokeRect(sx,sy,ex-sx,ey-sy);
        } else if (_fseShape === 'circle') {
          var rx=Math.abs(ex-sx)/2, ry=Math.abs(ey-sy)/2;
          _fseCtx.beginPath();
          _fseCtx.ellipse(sx+(ex-sx)/2,sy+(ey-sy)/2,rx,ry,0,0,Math.PI*2);
          _fseCtx.stroke();
        } else if (_fseShape === 'line') {
          _fseCtx.beginPath(); _fseCtx.moveTo(sx,sy); _fseCtx.lineTo(ex,ey); _fseCtx.stroke();
        } else if (_fseShape === 'arrow') {
          var ang=Math.atan2(ey-sy,ex-sx), hL=16+_fseBrushSize;
          _fseCtx.beginPath(); _fseCtx.moveTo(sx,sy); _fseCtx.lineTo(ex,ey); _fseCtx.stroke();
          _fseCtx.beginPath();
          _fseCtx.moveTo(ex,ey); _fseCtx.lineTo(ex-hL*Math.cos(ang-0.42), ey-hL*Math.sin(ang-0.42));
          _fseCtx.moveTo(ex,ey); _fseCtx.lineTo(ex-hL*Math.cos(ang+0.42), ey-hL*Math.sin(ang+0.42));
          _fseCtx.stroke();
        }
      }

      function _startDraw(e) {
        var p = _pos(e);
        if (_fseMode === 'text') {
          textModal.dataset.cx = p.x; textModal.dataset.cy = p.y;
          textModal.classList.add('open');
          setTimeout(function(){ textModal.querySelector('.fse-tm-txt').focus(); }, 40);
          return;
        }
        if (_fseMode === 'sticker') return;
        _saveUndo();
        _fseDrawing = true;
        _fseSX = p.x; _fseSY = p.y;
        if (_fseMode === 'shape') {
          _fseSnap = _fseCtx.getImageData(0, 0, _fseCanvas.width, _fseCanvas.height);
        } else if (_fseMode === 'draw' || _fseMode === 'eraser') {
          _fseCtx.beginPath(); _fseCtx.moveTo(p.x, p.y);
        } else if (_fseMode === 'mosaic') {
          _mosaicAt(p.x, p.y);
        }
      }

      function _moveDraw(e) {
        if (!_fseDrawing) return;
        var p = _pos(e);
        if (_fseMode === 'draw') {
          _fseCtx.globalCompositeOperation = 'source-over';
          _fseCtx.strokeStyle = _fseColor;
          _fseCtx.lineWidth   = _fseBrushSize;
          _fseCtx.lineCap     = 'round'; _fseCtx.lineJoin = 'round';
          _fseCtx.lineTo(p.x, p.y); _fseCtx.stroke();
          _fseCtx.beginPath(); _fseCtx.moveTo(p.x, p.y);
        } else if (_fseMode === 'eraser') {
          _fseCtx.globalCompositeOperation = 'destination-out';
          _fseCtx.strokeStyle = 'rgba(0,0,0,1)';
          _fseCtx.lineWidth   = _fseBrushSize;
          _fseCtx.lineCap     = 'round'; _fseCtx.lineJoin = 'round';
          _fseCtx.lineTo(p.x, p.y); _fseCtx.stroke();
          _fseCtx.beginPath(); _fseCtx.moveTo(p.x, p.y);
        } else if (_fseMode === 'mosaic') {
          _mosaicAt(p.x, p.y);
        } else if (_fseMode === 'shape' && _fseSnap) {
          _fseCtx.putImageData(_fseSnap, 0, 0);
          _drawShapePreview(_fseSX, _fseSY, p.x, p.y);
        }
      }

      function _endDraw() {
        if (_fseDrawing) {
          _fseCtx.globalCompositeOperation = 'source-over';
          _fseDrawing = false; _fseSnap = null;
        }
      }

      _fseCanvas.addEventListener('mousedown', function(e){ _startDraw(e); });
      _fseCanvas.addEventListener('mousemove', function(e){ _moveDraw(e); });
      document.addEventListener('mouseup', _endDraw);
      _fseCanvas.addEventListener('touchstart', function(e){ e.preventDefault(); _startDraw(e); }, { passive: false });
      _fseCanvas.addEventListener('touchmove',  function(e){ e.preventDefault(); _moveDraw(e);  }, { passive: false });
      _fseCanvas.addEventListener('touchend',   function(){ _endDraw(); });
    } // end _buildFSE

    /* ── CONTEXTUAL BOTTOM BAR ── */
    function _buildBottomBar(mode) {
      _fseBot.innerHTML = '';
      function _lbl(t){ var s=document.createElement('span');s.className='fse-label';s.textContent=t;return s; }
      function _sep(){ var s=document.createElement('div');s.className='fse-sep';return s; }

      if (mode === 'draw' || mode === 'shape') {
        _fseBot.appendChild(_lbl('Màu:'));
        PRESET_COLORS.forEach(function(c) {
          var sw = document.createElement('div');
          sw.className = 'fse-color-swatch' + (c === _fseColor ? ' active' : '');
          sw.style.background = c;
          sw.title = c;
          sw.onclick = function() {
            _fseColor = c;
            _fseBot.querySelectorAll('.fse-color-swatch').forEach(function(s){ s.classList.remove('active'); });
            sw.classList.add('active');
          };
          _fseBot.appendChild(sw);
        });
        // Custom colour picker
        var cust = document.createElement('input');
        cust.type = 'color'; cust.value = _fseColor; cust.className = 'fse-custom-color'; cust.title = 'Màu tùy chỉnh';
        cust.oninput = function() {
          _fseColor = cust.value;
          _fseBot.querySelectorAll('.fse-color-swatch').forEach(function(s){ s.classList.remove('active'); });
        };
        _fseBot.appendChild(cust);
        _fseBot.appendChild(_sep());

        // Brush size
        _fseBot.appendChild(_lbl('Cỡ:'));
        var szSlider = document.createElement('input');
        szSlider.type='range'; szSlider.min=1; szSlider.max=60; szSlider.value=_fseBrushSize; szSlider.className='fse-slider';
        var szVal = document.createElement('span'); szVal.className='fse-label'; szVal.textContent=_fseBrushSize+'px';
        szSlider.oninput = function(){ _fseBrushSize=parseInt(szSlider.value); szVal.textContent=szSlider.value+'px'; };
        _fseBot.appendChild(szSlider); _fseBot.appendChild(szVal);

        if (mode === 'shape') {
          _fseBot.appendChild(_sep());
          _fseBot.appendChild(_lbl('Hình:'));
          [['rect','▭ Chữ nhật'],['circle','○ Tròn'],['line','╱ Thẳng'],['arrow','→ Mũi tên']].forEach(function(sh) {
            var sb = document.createElement('button');
            sb.className = 'fse-shape-sub' + (_fseShape===sh[0]?' active':'');
            sb.textContent = sh[1]; sb.dataset.sh = sh[0];
            sb.onclick = function() {
              _fseShape = sh[0];
              _fseBot.querySelectorAll('.fse-shape-sub').forEach(function(b){ b.classList.remove('active'); });
              sb.classList.add('active');
            };
            _fseBot.appendChild(sb);
          });
        }
      } else if (mode === 'eraser') {
        _fseBot.appendChild(_lbl('Cỡ xoá:'));
        var eSlider = document.createElement('input');
        eSlider.type='range'; eSlider.min=2; eSlider.max=100; eSlider.value=_fseBrushSize; eSlider.className='fse-slider'; eSlider.style.width='150px';
        var eVal = document.createElement('span'); eVal.className='fse-label'; eVal.textContent=_fseBrushSize+'px';
        eSlider.oninput = function(){ _fseBrushSize=parseInt(eSlider.value); eVal.textContent=eSlider.value+'px'; };
        _fseBot.appendChild(eSlider); _fseBot.appendChild(eVal);
      } else if (mode === 'mosaic') {
        _fseBot.appendChild(_lbl('Khối:'));
        var mSlider = document.createElement('input');
        mSlider.type='range'; mSlider.min=4; mSlider.max=50; mSlider.value=_fseMosaicSize; mSlider.className='fse-slider'; mSlider.style.width='130px';
        var mVal = document.createElement('span'); mVal.className='fse-label'; mVal.textContent=_fseMosaicSize+'px';
        mSlider.oninput = function(){ _fseMosaicSize=parseInt(mSlider.value); mVal.textContent=mSlider.value+'px'; };
        _fseBot.appendChild(mSlider); _fseBot.appendChild(mVal);
        _fseBot.appendChild(_sep());
        var mHint = document.createElement('span'); mHint.className='fse-label'; mHint.style.opacity='.5'; mHint.textContent='Kéo lên vùng cần làm mờ';
        _fseBot.appendChild(mHint);
      } else if (mode === 'text') {
        var tHint = document.createElement('span'); tHint.className='fse-label'; tHint.textContent='💡 Nhấp lên ảnh để chèn chữ';
        _fseBot.appendChild(tHint);
      } else if (mode === 'sticker') {
        var stHint = document.createElement('span'); stHint.className='fse-label'; stHint.textContent='💡 Chọn sticker bên dưới hoặc tải ảnh lên';
        _fseBot.appendChild(stHint);
      }
    }

    function _setMode(mode) {
      _fseMode = mode;
      _fseTb.querySelectorAll('.fse-tool-btn[data-mode]').forEach(function(b){ b.classList.toggle('active', b.dataset.mode === mode); });
      _fseCanvas.style.cursor = mode==='text'?'text': mode==='eraser'?'cell':'crosshair';
      _buildBottomBar(mode);
      var sp = _fseArea.querySelector('.fse-sticker-panel');
      if (sp) sp.classList.toggle('open', mode==='sticker');
    }

    /* ── FLOATING OBJECTS (text / emoji sticker / image sticker) ── */
    function _makeDraggable(wrap, handle) {
      var mx,my;
      function _dm(e){ var s=e.touches?e.touches[0]:e; mx=s.clientX; my=s.clientY; }
      function _startDrag(e){
        if(e.target.classList.contains('fse-resize-h')||e.target.classList.contains('fse-obj-btn')) return;
        e.preventDefault(); _dm(e);
        function _onMove(ev){
          ev.preventDefault();
          var s=ev.touches?ev.touches[0]:ev;
          wrap.style.left=(wrap.offsetLeft+(s.clientX-mx))+'px';
          wrap.style.top =(wrap.offsetTop +(s.clientY-my))+'px';
          _dm(ev);
        }
        function _onUp(){ document.removeEventListener('mousemove',_onMove); document.removeEventListener('mouseup',_onUp); document.removeEventListener('touchmove',_onMove); document.removeEventListener('touchend',_onUp); }
        document.addEventListener('mousemove',_onMove); document.addEventListener('mouseup',_onUp);
        document.addEventListener('touchmove',_onMove,{passive:false}); document.addEventListener('touchend',_onUp);
      }
      handle.addEventListener('mousedown',_startDrag);
      handle.addEventListener('touchstart',_startDrag,{passive:false});
    }

    function _makeResizable(handle, onResize) {
      function _start(cx, cy) {
        var sx=cx, sy=cy;
        function _onMove(ev){
          ev.preventDefault();
          var px=ev.touches?ev.touches[0].clientX:ev.clientX;
          var py=ev.touches?ev.touches[0].clientY:ev.clientY;
          onResize(px-sx, py-sy);
          sx=px; sy=py; // incremental delta so each call gets a small step
        }
        function _onUp(){ document.removeEventListener('mousemove',_onMove); document.removeEventListener('mouseup',_onUp); document.removeEventListener('touchmove',_onMove); document.removeEventListener('touchend',_onUp); }
        document.addEventListener('mousemove',_onMove);
        document.addEventListener('mouseup',_onUp);
        document.addEventListener('touchmove',_onMove,{passive:false});
        document.addEventListener('touchend',_onUp);
      }
      handle.addEventListener('mousedown', function(e){ e.preventDefault(); e.stopPropagation(); _start(e.clientX, e.clientY); });
      handle.addEventListener('touchstart', function(e){ e.preventDefault(); e.stopPropagation(); _start(e.touches[0].clientX, e.touches[0].clientY); }, {passive:false});
    }

    function _floatContainer(onConfirm, onDelete) {
      var canvasRect = _fseCanvas.getBoundingClientRect();
      var areaRect   = _fseArea.getBoundingClientRect();
      var wrap = document.createElement('div'); wrap.className='fse-float-obj';
      wrap.style.left = (canvasRect.left - areaRect.left + canvasRect.width/2)  + 'px';
      wrap.style.top  = (canvasRect.top  - areaRect.top  + canvasRect.height/3) + 'px';
      var ctrl = document.createElement('div'); ctrl.className='fse-obj-ctrl';
      var ok = document.createElement('button'); ok.className='fse-obj-btn fse-obj-ok'; ok.textContent='✓'; ok.onclick=onConfirm;
      var del = document.createElement('button'); del.className='fse-obj-btn fse-obj-del'; del.textContent='✕'; del.onclick=onDelete;
      ctrl.appendChild(ok); ctrl.appendChild(del);
      wrap.appendChild(ctrl);
      _fseArea.appendChild(wrap);
      return wrap;
    }

    function _canvasPos(wrap) {
      var cr = _fseCanvas.getBoundingClientRect();
      var ar = _fseArea.getBoundingClientRect();
      var wr = wrap.getBoundingClientRect();
      return { x: (wr.left - cr.left) / _fseScale, y: (wr.top - cr.top) / _fseScale };
    }

    /* -- TEXT OBJECT -- */
    function _spawnTextObj(txt, color, size, font, bold, clickX, clickY) {
      var curSize = size;
      var initW = 0;

      var wrap = document.createElement('div'); wrap.className='fse-float-obj';
      // position near canvas click point
      var cr = _fseCanvas.getBoundingClientRect();
      var ar = _fseArea.getBoundingClientRect();
      wrap.style.left = (cr.left - ar.left + clickX * _fseScale) + 'px';
      wrap.style.top  = (cr.top  - ar.top  + clickY * _fseScale - size * _fseScale / 2) + 'px';

      var ctrl = document.createElement('div'); ctrl.className='fse-obj-ctrl';
      var ok  = document.createElement('button'); ok.className='fse-obj-btn fse-obj-ok'; ok.textContent='✓';
      var del = document.createElement('button'); del.className='fse-obj-btn fse-obj-del'; del.textContent='✕';
      del.onclick = function(){ wrap.remove(); };
      ctrl.appendChild(ok); ctrl.appendChild(del);

      var inner = document.createElement('div'); inner.className='fse-obj-inner';

      var textEl = document.createElement('div'); textEl.className='fse-obj-text';
      textEl.textContent = txt;
      textEl.style.fontSize   = size + 'px';
      textEl.style.color      = color;
      textEl.style.fontFamily = font;
      textEl.style.fontWeight = bold ? '700' : '400';
      textEl.style.whiteSpace = 'pre';
      textEl.style.lineHeight = '1.25';
      textEl.style.textShadow = '0 1px 6px rgba(0,0,0,.85), 0 0 2px rgba(0,0,0,.9)';
      textEl.style.padding    = '2px';
      textEl.style.userSelect = 'none';

      var rh = document.createElement('div'); rh.className='fse-resize-h'; rh.title='Kéo để scale';
      inner.appendChild(textEl); inner.appendChild(rh);

      wrap.appendChild(ctrl); wrap.appendChild(inner);
      _fseArea.appendChild(wrap);

      _makeDraggable(wrap, inner);

      // Resize = scale font
      _makeResizable(rh, function(dx) {
        curSize = Math.max(8, Math.min(300, curSize + Math.round(dx * 0.5)));
        textEl.style.fontSize = curSize + 'px';
      });

      ok.onclick = function() {
        var p = _canvasPos(wrap);
        _saveUndo();
        _fseCtx.save();
        _fseCtx.font        = (bold?'bold ':'')+curSize+'px '+font;
        _fseCtx.fillStyle   = color;
        _fseCtx.shadowColor = 'rgba(0,0,0,.7)';
        _fseCtx.shadowBlur  = 4;
        var ctrlH = 28 / _fseScale; // height of .fse-obj-ctrl above inner
        txt.split('\n').forEach(function(line, i){
          _fseCtx.fillText(line, p.x, p.y + ctrlH + curSize + i * curSize * 1.3);
        });
        _fseCtx.restore();
        wrap.remove();
      };
    }

    /* -- EMOJI STICKER OBJECT -- */
    function _spawnEmojiObj(emoji) {
      var sz = 60;
      var wrap = document.createElement('div'); wrap.className='fse-float-obj';
      var cr = _fseCanvas.getBoundingClientRect(), ar = _fseArea.getBoundingClientRect();
      wrap.style.left = (cr.left-ar.left+cr.width/2-sz/2)+'px';
      wrap.style.top  = (cr.top-ar.top+cr.height/3)+'px';

      var ctrl=document.createElement('div'); ctrl.className='fse-obj-ctrl';
      var ok=document.createElement('button'); ok.className='fse-obj-btn fse-obj-ok'; ok.textContent='✓';
      var del=document.createElement('button'); del.className='fse-obj-btn fse-obj-del'; del.textContent='✕';
      del.onclick=function(){ wrap.remove(); };
      ctrl.appendChild(ok); ctrl.appendChild(del);

      var inner=document.createElement('div'); inner.className='fse-obj-inner';
      var el=document.createElement('span'); el.className='fse-obj-emoji'; el.textContent=emoji; el.style.fontSize=sz+'px'; el.style.lineHeight='1'; el.style.display='block'; el.style.userSelect='none';
      var rh=document.createElement('div'); rh.className='fse-resize-h';
      inner.appendChild(el); inner.appendChild(rh);
      wrap.appendChild(ctrl); wrap.appendChild(inner);
      _fseArea.appendChild(wrap);
      _makeDraggable(wrap,inner);
      _makeResizable(rh,function(dx){
        sz=Math.max(16,Math.min(300,sz+dx*0.6));
        el.style.fontSize=sz+'px';
      });
      ok.onclick=function(){
        var p=_canvasPos(wrap);
        _saveUndo();
        _fseCtx.save();
        _fseCtx.font=sz+'px serif';
        _fseCtx.fillText(emoji, p.x, p.y+sz);
        _fseCtx.restore();
        wrap.remove();
      };
    }

    /* -- IMAGE STICKER OBJECT -- */
    function _spawnImgObj(src) {
      var wrap=document.createElement('div'); wrap.className='fse-float-obj';
      var cr=_fseCanvas.getBoundingClientRect(), ar=_fseArea.getBoundingClientRect();
      wrap.style.left=(cr.left-ar.left+cr.width/2-50)+'px';
      wrap.style.top=(cr.top-ar.top+cr.height/3)+'px';

      var ctrl=document.createElement('div'); ctrl.className='fse-obj-ctrl';
      var ok=document.createElement('button'); ok.className='fse-obj-btn fse-obj-ok'; ok.textContent='✓';
      var del=document.createElement('button'); del.className='fse-obj-btn fse-obj-del'; del.textContent='✕';
      del.onclick=function(){ wrap.remove(); };
      ctrl.appendChild(ok); ctrl.appendChild(del);

      var inner=document.createElement('div'); inner.className='fse-obj-inner';
      var img=document.createElement('img'); img.src=src; img.style.cssText='width:100px;height:100px;object-fit:contain;display:block;user-select:none;pointer-events:none;';
      var rh=document.createElement('div'); rh.className='fse-resize-h';
      inner.appendChild(img); inner.appendChild(rh);
      wrap.appendChild(ctrl); wrap.appendChild(inner);
      _fseArea.appendChild(wrap);
      _makeDraggable(wrap,inner);
      var bw=100,bh=100;
      _makeResizable(rh,function(dx,dy){
        bw=Math.max(20,bw+dx); bh=Math.max(20,bh+dy);
        img.style.width=bw+'px'; img.style.height=bh+'px';
      }); // incremental delta handled inside _makeResizable
      ok.onclick=function(){
        var p=_canvasPos(wrap);
        var sw=img.offsetWidth/_fseScale, sh=img.offsetHeight/_fseScale;
        _saveUndo();
        var i2=new Image();
        i2.onload=function(){ _fseCtx.drawImage(i2,p.x,p.y,sw,sh); };
        i2.src=src;
        wrap.remove();
      };
    }

    function _commitAllFloating(done) {
      if (!_fseArea) { if (done) done(); return; }
      // Collect image sticker objects that need async load before we can proceed
      var imgObjs = _fseArea.querySelectorAll('.fse-float-obj');
      var pending = 0;
      imgObjs.forEach(function(obj) {
        var okBtn = obj.querySelector('.fse-obj-ok');
        if (!okBtn) return;
        var imgEl = obj.querySelector('img');
        if (imgEl) {
          // image sticker — trigger commit which is async
          pending++;
          var cr = _fseCanvas.getBoundingClientRect(), ar = _fseArea.getBoundingClientRect();
          var wr = obj.getBoundingClientRect();
          var cx = (wr.left - cr.left) / _fseScale, cy = (wr.top - cr.top) / _fseScale;
          var sw = imgEl.offsetWidth / _fseScale, sh = imgEl.offsetHeight / _fseScale;
          var src = imgEl.src;
          obj.remove();
          var i2 = new Image();
          i2.onload = function() {
            _fseCtx.drawImage(i2, cx, cy, sw, sh);
            pending--;
            if (pending === 0 && done) done();
          };
          i2.onerror = function() { pending--; if (pending === 0 && done) done(); };
          i2.src = src;
        } else {
          // text or emoji — sync
          okBtn.click();
        }
      });
      if (pending === 0 && done) done();
    }

    function _applyZoom() {
      var lbl = _fseTb && _fseTb.querySelector('.fse-zoom-val');
      if (lbl) lbl.textContent = Math.round(_fseScale*100)+'%';
      if (_fseCanvas) {
        _fseCanvas.style.width  = (_fseCanvas.width  * _fseScale)+'px';
        _fseCanvas.style.height = (_fseCanvas.height * _fseScale)+'px';
      }
    }
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
