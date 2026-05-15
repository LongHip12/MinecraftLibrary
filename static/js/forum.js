(function () {
  // ── Reply toggle ──────────────────────────────────────────────
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

  // ── Accumulated file list for chat ───────────────────────────
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
        img.style.cssText = 'width:32px;height:32px;object-fit:cover;border-radius:4px;';
        var reader = new FileReader();
        reader.onload = function (e) { img.src = e.target.result; };
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

  // ── File attachment preview (reply forms / old msg-files) ─────
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

  var postFileInput = document.getElementById('post-files');
  var postPreview = document.getElementById('post-files-preview');
  if (postFileInput && postPreview) initFileInput(postFileInput, postPreview);

  // ── Download warning modal ────────────────────────────────────
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

  // ── Toggle replies ────────────────────────────────────────────
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
        var count = list.querySelectorAll('.reply-card').length;
        var word = count === 1 ? 'reply' : 'replies';
        span.textContent = isOpen ? 'Show ' + count + ' ' + word : 'Hide ' + count + ' ' + word;
      }
    });
  });

  // ── Category active highlight ─────────────────────────────────
  var currentCat = new URLSearchParams(window.location.search).get('category') || '';
  document.querySelectorAll('.forum-cat-item').forEach(function (el) {
    if (el.getAttribute('data-cat') === currentCat) el.classList.add('active');
  });

  // ── Forum nav active ──────────────────────────────────────────
  var nlForum = document.getElementById('nl-forum');
  var ndForum = document.getElementById('nd-forum');
  if (window.location.pathname.startsWith('/forum')) {
    if (nlForum) nlForum.classList.add('active');
    if (ndForum) ndForum.classList.add('active');
  }
})();
