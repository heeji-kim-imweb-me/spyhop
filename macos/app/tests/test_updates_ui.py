"""실제 보드 HTML에서 앱 업데이트 UI를 브라우저로 실행한다."""
import json
import os
import subprocess
import sys
import time
import unittest
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

BOARD_TESTS = Path(__file__).resolve().parents[2] / 'board/tests'
sys.path.insert(0, str(BOARD_TESTS))
import test_board_ui as board_tests


class UpdatesUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Path(board_tests.CHROME).is_file():
            raise unittest.SkipTest('Brave/Chromium required')
        board_tests.BoardUITest.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        board_tests.BoardUITest.tearDownClass.__func__(cls)

    def browser(self, initial, script, width=1280):
        port = os.environ.get('SPYHOP_UI_CDP_PORT')
        if not port:
            return board_tests.BoardUITest.browser(self, initial, script, width)
        # Brave가 이미 열린 로컬 환경에서는 CDP로 같은 픽스처를 실행한다.
        import websocket
        def execute(args, **kwargs):
            url = args[-1]
            endpoint = 'http://127.0.0.1:' + port
            request = urllib.request.Request(endpoint + '/json/new?' + urllib.parse.quote(url, safe=''), method='PUT')
            tab = json.load(urllib.request.urlopen(request, timeout=5))
            ws = websocket.create_connection(tab['webSocketDebuggerUrl'], timeout=10, suppress_origin=True)
            seq = 0
            def call(method, params):
                nonlocal seq
                seq += 1
                ws.send(json.dumps({'id': seq, 'method': method, 'params': params}))
                while True:
                    value = json.loads(ws.recv())
                    if value.get('id') == seq:
                        return value.get('result', {})
            try:
                for _ in range(100):
                    reply = call('Runtime.evaluate', {'expression': 'document.querySelector("#qa-result")?.textContent', 'returnByValue': True})
                    if reply.get('result', {}).get('value'):
                        dom = call('Runtime.evaluate', {'expression': 'document.documentElement.outerHTML', 'returnByValue': True})
                        return subprocess.CompletedProcess(args, 0, stdout=dom['result']['value'], stderr='')
                    time.sleep(.05)
                raise AssertionError('Browser fixture did not complete')
            finally:
                ws.close()
                urllib.request.urlopen(endpoint + '/json/close/' + tab['id'], timeout=5).close()
        with patch.object(board_tests.subprocess, 'run', side_effect=execute):
            return board_tests.BoardUITest.browser(self, initial, script, width)

    def update_browser(self, script, width=1280):
        js = (Path(__file__).resolve().parents[1] / 'Resources/updates.js').read_text()
        # file:// 픽스처에서만 origin 검사를 대체한다. 앱 브리지는 기록만 남긴다.
        js = js.replace("location.origin !== 'http://127.0.0.1:47613' || location.pathname !== '/'", 'false')
        setup = ('window.__actions=[];window.webkit={messageHandlers:{spyhopUpdates:{postMessage:a=>__actions.push(a)}}};'
                 + js + ';const receive=window.spyhopUpdates.receive;const available={phase:"available",version:"2.1.0",latest:"2.2.0",newFeatures:[],fixes:[],showChanges:false};')
        return self.browser('assigned', setup + script, width=width)

    def test_update_action_and_busy_state(self):
        result = self.update_browser('receive(available);var notice=document.getElementById("spyhop-update-slot").textContent;'
                                     'receive({...available,phase:"installing"});'
                                     'var result={notice,buttons:document.querySelectorAll("#spyhop-update-slot button").length,text:document.getElementById("spyhop-update-slot").textContent};')
        self.assertEqual(result['notice'], 'Update available')
        self.assertEqual(result['buttons'], 0)
        self.assertIn('restart automatically', result['text'])
        self.assertNotIn('Later', result['text'])

    def test_update_notice_keeps_legend_and_time_at_the_right_edge(self):
        result = self.update_browser('var positions=[];for(const phase of ["idle","available","checking"]){'
                                     'receive({...available,phase});var bar=document.querySelector(".subbar"),time=bar.querySelector("small"),legend=bar.querySelector(".legend");'
                                     'positions.push({phase,gap:bar.getBoundingClientRect().right-time.getBoundingClientRect().right,ordered:legend.getBoundingClientRect().right<=time.getBoundingClientRect().left});}'
                                     'var gear=document.querySelector(".gear"),header=document.querySelector("header");'
                                     'var result={positions,gearGap:header.getBoundingClientRect().right-gear.getBoundingClientRect().right};')
        for position in result['positions']:
            self.assertLessEqual(abs(position['gap']), 2, position)
            self.assertTrue(position['ordered'], position)
        self.assertLessEqual(result['gearGap'], 14)

    def test_features_popup_dismiss_and_no_repeat(self):
        result = self.update_browser('const next={...available,showChanges:true,newFeatures:Array.from({length:5},(_,i)=>({title:"New feature "+i,detail:"How it works"})),fixes:[{title:"A fix",detail:"Full fix description"}]};'
                                     'receive(next);var d=document.getElementById("spyhop-whats-new");'
                                     'var text=d.textContent,modal=d.open;d.querySelector("button").click();receive(next);'
                                     'var result={text,modal,closed:!document.getElementById("spyhop-whats-new"),actions:__actions};')
        self.assertTrue(result['modal'])
        self.assertIn('New feature', result['text'])
        self.assertIn('How it works', result['text'])
        self.assertIn('New feature 4', result['text'])
        self.assertIn('New Features', result['text'])
        self.assertIn('Fixes', result['text'])
        self.assertIn('Full fix description', result['text'])
        self.assertTrue(result['closed'])
        self.assertIn('dismiss', result['actions'])

    def test_refresh_restores_notice_without_settings_controls(self):
        result = self.update_browser('receive(available);document.getElementById("spyhop-update-slot").remove();'
                                     'await tick();'
                                     'var result={notice:!!document.getElementById("spyhop-update-slot"),settings:document.getElementById("settings").textContent};')
        self.assertTrue(result['notice'])
        self.assertNotIn('Release notes', result['settings'])
        self.assertNotIn('Check for updates', result['settings'])

    def test_narrow_popup_and_escape(self):
        result = self.update_browser('receive({...available,showChanges:true,newFeatures:[{title:"A feature",detail:"Description"}]});'
                                     'var d=document.getElementById("spyhop-whats-new"),r=d.getBoundingClientRect();'
                                     'd.dispatchEvent(new Event("cancel",{cancelable:true}));'
                                     'var result={fits:r.left>=0&&r.right<=innerWidth,closed:!document.getElementById("spyhop-whats-new"),actions:__actions};', width=420)
        self.assertTrue(result['fits'])
        self.assertTrue(result['closed'])
        self.assertIn('dismiss', result['actions'])

    def test_error_is_text_without_a_second_update_control(self):
        result = self.update_browser('receive({...available,phase:"error",error:"<img src=x onerror=alert(1)>"});'
                                     'var slot=document.getElementById("spyhop-update-slot");'
                                     'var result={images:slot.querySelectorAll("img").length,buttons:slot.querySelectorAll("button").length,text:slot.textContent};')
        self.assertEqual(result['images'], 0)
        self.assertEqual(result['buttons'], 0)
        self.assertIn('<img', result['text'])

    def test_available_release_notes_and_install_share_one_dialog(self):
        notes = '## New Features\n- **Session search:** Find any session.\n\n## Fixes\n- More reliable switching.\n- Final fix, preserved.'
        result = self.update_browser('receive({...available,showAvailable:true,availableNotes:' + json.dumps(notes) + '});'
                                     'var d=document.getElementById("spyhop-update-offer"),text=d.textContent;'
                                     'd.querySelector(".update-primary").click();'
                                     'var busy=d.querySelector(".update-primary").disabled;'
                                     'receive({...available,showAvailable:false,phase:"installing"});'
                                     'var result={text,busy,actions:__actions,closed:!document.getElementById("spyhop-update-offer")};')
        self.assertIn('2.1.0 → 2.2.0', result['text'])
        self.assertIn('New Features', result['text'])
        self.assertIn('Fixes', result['text'])
        self.assertIn('Final fix, preserved.', result['text'])
        self.assertIn('Update and restart', result['text'])
        self.assertNotIn('Later', result['text'])
        self.assertTrue(result['busy'])
        self.assertTrue(result['closed'])
        self.assertIn('install', result['actions'])

    def test_available_notes_are_safe_and_not_truncated(self):
        notes = '## New Features\n' + '\n'.join('- Feature %d' % i for i in range(40))
        notes += '\n## Fixes\n<img src=x onerror=alert(1)>\n[Unsafe](javascript:alert(1))\n```sh\nbrew upgrade --cask spyhop\n```'
        result = self.update_browser('receive({...available,showAvailable:true,availableNotes:' + json.dumps(notes) + '});'
                                     'var d=document.getElementById("spyhop-update-offer"),content=d.querySelector(".update-content");'
                                     'var r=d.getBoundingClientRect();'
                                     'var result={text:d.textContent,images:d.querySelectorAll("img").length,unsafe:d.querySelectorAll("a[href^=javascript]").length,scroll:content.scrollHeight>content.clientHeight,fits:r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight};', width=420)
        self.assertIn('Feature 39', result['text'])
        self.assertIn('brew upgrade --cask spyhop', result['text'])
        self.assertEqual(result['images'], 0)
        self.assertEqual(result['unsafe'], 0)
        self.assertTrue(result['scroll'])
        self.assertTrue(result['fits'])

    def test_close_available_notes_does_not_install(self):
        result = self.update_browser('receive({...available,showAvailable:true,availableNotes:"## Fixes\\n- A fix"});'
                                     'document.querySelector("#spyhop-update-offer .update-close").click();'
                                     'var result={closed:!document.getElementById("spyhop-update-offer"),actions:__actions};')
        self.assertTrue(result['closed'])
        self.assertIn('dismiss-available', result['actions'])
        self.assertNotIn('install', result['actions'])


if __name__ == '__main__':
    import unittest
    unittest.main()
