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
    #spyhop-update-slot{display:inline-flex;align-items:center;margin-left:auto;gap:8px;font-size:12px}
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
    @media(max-width:600px){#spyhop-update-slot{width:100%;margin:6px 0}.spyhop-update-dialog .update-content{padding:22px}.spyhop-update-dialog footer{padding:14px 22px}}
  `;
  document.head.appendChild(style);

  function render() {
    const bar = document.querySelector('.subbar');
    if (!bar) return;
    let slot = document.getElementById('spyhop-update-slot');
    if (!slot) { slot = document.createElement('div'); slot.id = 'spyhop-update-slot'; slot.setAttribute('aria-live', 'polite'); bar.appendChild(slot); serial = ''; }
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
    if (state.showChanges && !acknowledged && !document.getElementById('spyhop-whats-new')) showChanges();
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
    footer.appendChild(gotIt); dialog.append(content, footer); document.body.appendChild(dialog); dialog.showModal(); gotIt.focus({preventScroll:true});
  }
  window.spyhopUpdates = {receive(next) { state = next; render(); }};
  // 보드의 live()가 칸과 설정을 교체해도 다시 붙인다. 변경한 자식은 관찰하지 않는다.
  const observer = new MutationObserver(() => { if (!document.getElementById('spyhop-update-slot')) render(); });
  observer.observe(document.body, {childList:true, subtree:true});
  post('status'); setInterval(() => { if (!document.hidden) post('status'); }, 2000);
})();
