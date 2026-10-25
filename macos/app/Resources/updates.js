// 앱 보드에만 업데이트 UI를 붙인다. 브라우저판과 메뉴바 패널에는 설치 기능을 노출하지 않는다.
(function () {
  'use strict';
  if (location.origin !== 'http://127.0.0.1:47613' || location.pathname !== '/') return;
  const bridge = window.webkit && window.webkit.messageHandlers.spyhopUpdates;
  if (!bridge || window.spyhopUpdates) return;
  const post = action => bridge.postMessage(action);
  let state = {}, previousFocus, acknowledged = false, serial = '';
  const style = document.createElement('style');
  style.textContent = `
    #spyhop-update-slot{display:inline-flex;align-items:center;gap:8px;font-size:12px}
    #spyhop-update-slot:empty{display:none}
    .spyhop-update-dialog button{font:inherit;cursor:pointer;border-radius:8px;padding:8px 13px;border:1px solid var(--line);color:var(--ink);background:var(--card)}
    .spyhop-update-dialog .update-primary{background:#65b4ef;color:#111820;border:0;font-weight:650}
    #spyhop-update-slot .update-error{max-width:260px;color:var(--ink3);font-size:11px}
    .spyhop-update-dialog{width:min(540px,calc(100vw - 44px));box-sizing:border-box;padding:0;border:1px solid var(--line);border-top:3px solid #65b4ef;border-radius:16px;background:var(--card);color:var(--ink);box-shadow:0 24px 90px #0006;max-height:85vh}
    .spyhop-update-dialog::backdrop{background:#0006;backdrop-filter:blur(4px)}
    .spyhop-update-dialog .update-content{padding:28px 30px;overflow:auto;max-height:calc(85vh - 90px);box-sizing:border-box}
    .spyhop-update-dialog .update-eyebrow{color:#65b4ef;font-size:12px;font-weight:650;margin:0 0 12px}
    .spyhop-update-dialog h2{font-size:24px;margin:0 0 8px;letter-spacing:-.02em}
    .spyhop-update-dialog .update-version{color:var(--ink3);font-size:13px;margin:0 0 25px}
    .spyhop-update-dialog .update-feature{padding:15px 0;border-top:1px solid var(--line)}
    .spyhop-update-dialog h3{margin:0 0 6px;font-size:14px}
    .spyhop-update-dialog .update-category{font-size:11px;letter-spacing:.08em;text-transform:uppercase;margin:22px 0 10px;color:var(--ink3)}
    .spyhop-update-dialog .update-detail{margin:0;color:var(--ink3);font-size:13px;line-height:1.6}
    .spyhop-update-dialog footer{display:flex;align-items:center;justify-content:flex-end;padding:16px 30px;border-top:1px solid var(--line)}
    .spyhop-update-dialog .update-close{position:absolute;right:14px;top:12px;background:transparent;border:0;font-size:20px;color:var(--ink3);padding:2px 8px}
    .spyhop-update-dialog .update-restart{font-size:11px;color:var(--ink3);line-height:1.5;margin:0 auto 0 0;padding-right:18px}
    .spyhop-update-dialog .update-markdown{font-size:13px;line-height:1.65;overflow-wrap:anywhere}
    .spyhop-update-dialog .update-markdown h3{margin:24px 0 10px;font-size:13px;color:var(--ink)}
    .spyhop-update-dialog .update-markdown p{margin:0 0 12px;color:var(--ink3);white-space:pre-wrap}
    .spyhop-update-dialog .update-markdown ul{padding-left:20px;margin:0 0 16px;color:var(--ink3)}
    .spyhop-update-dialog .update-markdown li{margin:6px 0}
    .spyhop-update-dialog .update-markdown pre{overflow:auto;padding:12px;background:var(--col);border-radius:8px;white-space:pre;font-size:11px}
    .spyhop-update-dialog .update-markdown code{font-family:ui-monospace,Menlo,monospace;font-size:.92em}
    .spyhop-update-dialog .update-markdown a{color:var(--busy)}
    @media(max-width:600px){#spyhop-update-slot{width:100%;margin:6px 0}.spyhop-update-dialog .update-content{padding:22px}.spyhop-update-dialog footer{padding:14px 22px}}
  `;
  document.head.appendChild(style);

  function render() {
    const bar = document.querySelector('.subbar');
    if (!bar) return;
    let slot = document.getElementById('spyhop-update-slot');
    if (!slot) { slot = document.createElement('div'); slot.id = 'spyhop-update-slot'; slot.setAttribute('aria-live', 'polite'); bar.insertBefore(slot, bar.querySelector('.legend') || bar.querySelector('small')); serial = ''; }
    const key = JSON.stringify([state.phase, state.latest, state.error]);
    if (key !== serial) {
      serial = key; slot.replaceChildren();
      if (state.phase === 'available' || state.phase === 'installing' || (state.phase === 'error' && state.latest)) {
        const text = document.createElement('span');
        text.textContent = state.phase === 'installing' ? 'Updating… Spyhop will restart automatically.' : 'Update available';
        text.title = 'Choose Spyhop > Check for Updates… to install.';
        slot.appendChild(text);
      }
      if (state.phase === 'checking') { const t = document.createElement('span'); t.textContent = 'Checking for updates…'; slot.appendChild(t); }
      if (state.error) {
        const error = document.createElement('span'); error.className = 'update-error'; error.textContent = state.error; slot.appendChild(error);
      }
    }
    let offer = document.getElementById('spyhop-update-offer');
    if (offer && state.showAvailable && offer.dataset.version !== state.latest) { offer.close(); offer.remove(); offer = null; }
    if (!state.showAvailable && offer) { offer.close(); offer.remove(); }
    if (state.showAvailable && !offer) {
      const changes = document.getElementById('spyhop-whats-new');
      if (changes) { changes.close(); changes.remove(); }
      showAvailable();
    } else if (!state.showAvailable && state.showChanges && !acknowledged && !document.getElementById('spyhop-whats-new')) showChanges();
  }

  // 릴리즈 본문은 HTML로 삽입하지 않는다. 모든 문장을 보존하며 기본 Markdown만 DOM으로 그린다.
  function releaseNotes(markdown) {
    const root = document.createElement('div'); root.className = 'update-markdown';
    function inline(parent, text) {
      const tokens = /(\[[^\]]+\]\(https?:\/\/[^\s)]+\)|`[^`]+`|\*\*[^*]+\*\*)/g;
      let start = 0;
      for (const match of text.matchAll(tokens)) {
        parent.appendChild(document.createTextNode(text.slice(start, match.index)));
        const value = match[0]; let node;
        if (value.startsWith('[')) {
          const link = value.match(/^\[([^\]]+)\]\((.+)\)$/);
          node = document.createElement('a'); node.textContent = link[1]; node.href = link[2]; node.target = '_blank'; node.rel = 'noopener';
        } else {
          node = document.createElement(value.startsWith('`') ? 'code' : 'strong');
          node.textContent = value.startsWith('`') ? value.slice(1, -1) : value.slice(2, -2);
        }
        parent.appendChild(node); start = match.index + value.length;
      }
      parent.appendChild(document.createTextNode(text.slice(start)));
    }
    let paragraph = [], list = null, code = null;
    function flush() { if (paragraph.length) { const p = document.createElement('p'); inline(p, paragraph.join('\n')); root.appendChild(p); paragraph = []; } }
    for (const line of String(markdown || 'No release notes are available for this version.').replace(/\r\n/g, '\n').split('\n')) {
      if (/^\s*```/.test(line)) {
        flush(); list = null;
        if (code) { code = null; } else { const pre = document.createElement('pre'); code = document.createElement('code'); pre.appendChild(code); root.appendChild(pre); }
        continue;
      }
      if (code) { code.textContent += line + '\n'; continue; }
      const heading = line.match(/^#{1,6}[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$/) || line.match(/^\*\*(.+)\*\*\s*$/);
      if (heading) { flush(); list = null; const h = document.createElement('h3'); inline(h, heading[1]); root.appendChild(h); continue; }
      const item = line.match(/^\s*[-*+]\s+(.+)$/);
      if (item) { flush(); if (!list) { list = document.createElement('ul'); root.appendChild(list); } const li = document.createElement('li'); inline(li, item[1]); list.appendChild(li); continue; }
      list = null;
      if (!line.trim()) flush(); else paragraph.push(line);
    }
    flush(); return root;
  }

  // 보드의 다른 창처럼 바깥(어두운 배경)을 누르면 닫는다. busy() 가 참이면(업데이트 준비 중) 닫지 않는다
  function closeOnOutside(dialog, close, busy) {
    dialog.addEventListener('mousedown', e => {
      if (e.target !== dialog || (busy && busy())) return;
      const r = dialog.getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) { e.preventDefault(); close(); }
    });
  }

  function showAvailable() {
    const previous = document.activeElement;
    const dialog = document.createElement('dialog'); dialog.id = 'spyhop-update-offer'; dialog.className = 'spyhop-update-dialog'; dialog.setAttribute('aria-labelledby', 'spyhop-offer-title');
    dialog.dataset.version = state.latest;
    const content = document.createElement('div'); content.className = 'update-content';
    const eyebrow = document.createElement('p'); eyebrow.className = 'update-eyebrow'; eyebrow.textContent = 'Update available';
    const title = document.createElement('h2'); title.id = 'spyhop-offer-title'; title.textContent = 'A new version of Spyhop';
    const version = document.createElement('p'); version.className = 'update-version'; version.textContent = state.version + ' → ' + state.latest;
    content.append(eyebrow, title, version, releaseNotes(state.availableNotes));
    const close = () => { dialog.close(); dialog.remove(); state.showAvailable = false; post('dismiss-available'); if (previous && previous.isConnected) previous.focus({preventScroll:true}); };
    const dismiss = document.createElement('button'); dismiss.type = 'button'; dismiss.className = 'update-close'; dismiss.setAttribute('aria-label', 'Close release notes'); dismiss.textContent = '×'; dismiss.addEventListener('click', close);
    dialog.addEventListener('cancel', e => { e.preventDefault(); close(); });
    const footer = document.createElement('footer');
    const hint = document.createElement('p'); hint.className = 'update-restart'; hint.textContent = 'Spyhop will restart automatically after installation.';
    const install = document.createElement('button'); install.type = 'button'; install.className = 'update-primary'; install.textContent = 'Update and restart';
    install.addEventListener('click', () => { install.disabled = true; install.textContent = 'Preparing update…'; post('install'); });
    closeOnOutside(dialog, close, () => install.disabled);
    footer.append(hint, install); dialog.append(dismiss, content, footer); document.body.appendChild(dialog); dialog.showModal(); install.focus({preventScroll:true});
  }
  function showChanges() {
    previousFocus = document.activeElement;
    const dialog = document.createElement('dialog'); dialog.id = 'spyhop-whats-new'; dialog.className = 'spyhop-update-dialog'; dialog.setAttribute('aria-labelledby', 'spyhop-whats-new-title');
    const content = document.createElement('div'); content.className = 'update-content';
    const eyebrow = document.createElement('p'); eyebrow.className = 'update-eyebrow'; eyebrow.textContent = 'Updated successfully';
    const title = document.createElement('h2'); title.id = 'spyhop-whats-new-title'; title.textContent = "What's new in Spyhop";
    const version = document.createElement('p'); version.className = 'update-version'; version.textContent = 'Spyhop ' + state.version;
    content.append(eyebrow, title, version);
    [['New Features', state.newFeatures || []], ['Fixes', state.fixes || []]].forEach(([label, rows]) => {
      if (!rows.length) return;
      const category = document.createElement('h3'); category.className = 'update-category'; category.textContent = label; content.appendChild(category);
      rows.forEach(row => {
        const feature = document.createElement('section'); feature.className = 'update-feature';
        const h = document.createElement('h3'); h.textContent = row.title;
        const p = document.createElement('p'); p.className = 'update-detail'; p.textContent = row.detail;
        feature.append(h, p); content.appendChild(feature);
      });
    });
    const footer = document.createElement('footer'), gotIt = document.createElement('button');
    gotIt.type = 'button'; gotIt.className = 'update-primary'; gotIt.textContent = 'Got it';
    const close = () => { acknowledged = true; dialog.close(); dialog.remove(); post('dismiss'); if (previousFocus && previousFocus.isConnected) previousFocus.focus({preventScroll:true}); };
    gotIt.addEventListener('click', close); dialog.addEventListener('cancel', e => { e.preventDefault(); close(); });
    closeOnOutside(dialog, close);
    footer.appendChild(gotIt); dialog.append(content, footer); document.body.appendChild(dialog); dialog.showModal(); gotIt.focus({preventScroll:true});
    post('dismiss');  // 화면에 한 번 띄웠으면 본 것으로 친다. 닫지 않고 앱을 꺼도 다음 실행에 다시 뜨지 않는다 (지금 창은 Got it 까지 남는다)
  }
  window.spyhopUpdates = {receive(next) { state = next; render(); }};
  // 보드의 live()가 칸과 설정을 교체해도 다시 붙인다. 변경한 자식은 관찰하지 않는다.
  const observer = new MutationObserver(() => { if (!document.getElementById('spyhop-update-slot')) render(); });
  observer.observe(document.body, {childList:true, subtree:true});
  post('status'); setInterval(() => { if (!document.hidden) post('status'); }, 2000);
})();
