"""Windows 작업 표시줄 트레이 아이콘: 맥의 메뉴바 항목(menubar/spyhop.5s.py)과 같은 일을 한다 (표준 라이브러리 ctypes 만 쓴다).

  아이콘    내 차례인 세션 수. 보드가 꺼져 있으면 회색
  왼쪽 클릭  작은 보드 패널(/panel)을 연다
  오른쪽 클릭 세션 목록. 고르면 그 세션으로 간다
  감시      Claude·Codex 가 떠 있는데 보드가 꺼져 있으면 다시 켠다

  pythonw -X utf8 tray.py                  트레이만 띄운다 (spyhop.cmd 가 부른다)
  pythonw -X utf8 tray.py --start-board    로그인 때: 보드도 바로 켠다
"""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from ctypes import wintypes as W
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board as B  # noqa: E402
import winplat  # noqa: E402

PORT = B.PORT
BOARD_URL = 'http://127.0.0.1:%d/' % PORT
PANEL_URL = BOARD_URL + 'panel'
TICK_MS = 3000           # 아이콘을 다시 그리는 주기
ENSURE_EVERY = 5         # 보드가 꺼졌는지 보는 주기(초)
STALE = 120              # 보드가 이만큼 상태를 안 고쳤으면 꺼진 것으로 본다
MAX_ROWS = 15

u32 = ctypes.WinDLL('user32', use_last_error=True)
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
gdi = ctypes.WinDLL('gdi32')
shell32 = ctypes.WinDLL('shell32')

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

WM_DESTROY, WM_COMMAND, WM_TIMER, WM_NULL = 0x0002, 0x0111, 0x0113, 0x0000
WM_LBUTTONUP, WM_RBUTTONUP, WM_CONTEXTMENU = 0x0202, 0x0205, 0x007B
WM_TRAY = 0x8000 + 1  # WM_APP + 1
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_SHOWTIP = 0x1, 0x2, 0x4, 0x80
MF_STRING, MF_SEPARATOR, MF_GRAYED, MF_POPUP = 0x0, 0x800, 0x1, 0x10
TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_NONOTIFY = 0x2, 0x100, 0x80
ERROR_ALREADY_EXISTS = 183

ID_OPEN_BOARD, ID_OPEN_PANEL, ID_START, ID_QUIT, ID_SESSION = 1, 2, 3, 4, 100


class WNDCLASSW(ctypes.Structure):
    _fields_ = [('style', W.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int),
                ('hInstance', W.HINSTANCE), ('hIcon', W.HICON), ('hCursor', W.HANDLE), ('hbrBackground', W.HBRUSH),
                ('lpszMenuName', W.LPCWSTR), ('lpszClassName', W.LPCWSTR)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [('cbSize', W.DWORD), ('hWnd', W.HWND), ('uID', W.UINT), ('uFlags', W.UINT), ('uCallbackMessage', W.UINT),
                ('hIcon', W.HICON), ('szTip', W.WCHAR * 128), ('dwState', W.DWORD), ('dwStateMask', W.DWORD),
                ('szInfo', W.WCHAR * 256), ('uVersion', W.UINT), ('szInfoTitle', W.WCHAR * 64), ('dwInfoFlags', W.DWORD),
                ('guidItem', ctypes.c_byte * 16), ('hBalloonIcon', W.HICON)]


class ICONINFO(ctypes.Structure):
    _fields_ = [('fIcon', W.BOOL), ('xHotspot', W.DWORD), ('yHotspot', W.DWORD), ('hbmMask', W.HBITMAP), ('hbmColor', W.HBITMAP)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', W.DWORD), ('biWidth', W.LONG), ('biHeight', W.LONG), ('biPlanes', W.WORD), ('biBitCount', W.WORD),
                ('biCompression', W.DWORD), ('biSizeImage', W.DWORD), ('biXPelsPerMeter', W.LONG), ('biYPelsPerMeter', W.LONG),
                ('biClrUsed', W.DWORD), ('biClrImportant', W.DWORD)]


u32.DefWindowProcW.restype = LRESULT
u32.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
u32.CreateWindowExW.restype = W.HWND
u32.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID]
u32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
u32.RegisterWindowMessageW.argtypes = [W.LPCWSTR]
u32.CreatePopupMenu.restype = W.HMENU
u32.AppendMenuW.argtypes = [W.HMENU, W.UINT, ctypes.c_size_t, W.LPCWSTR]
u32.TrackPopupMenu.argtypes = [W.HMENU, W.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.HWND, W.LPVOID]
u32.DestroyMenu.argtypes = [W.HMENU]
u32.SetForegroundWindow.argtypes = [W.HWND]
u32.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
u32.GetCursorPos.argtypes = [ctypes.POINTER(W.POINT)]
u32.SetTimer.argtypes = [W.HWND, ctypes.c_size_t, W.UINT, W.LPVOID]
u32.GetMessageW.argtypes = [ctypes.POINTER(W.MSG), W.HWND, W.UINT, W.UINT]
u32.TranslateMessage.argtypes = [ctypes.POINTER(W.MSG)]
u32.DispatchMessageW.argtypes = [ctypes.POINTER(W.MSG)]
u32.DestroyIcon.argtypes = [W.HICON]
u32.CreateIconIndirect.restype = W.HICON
u32.CreateIconIndirect.argtypes = [ctypes.POINTER(ICONINFO)]
u32.GetDC.restype = W.HDC
u32.GetDC.argtypes = [W.HWND]
u32.ReleaseDC.argtypes = [W.HWND, W.HDC]
u32.FillRect.argtypes = [W.HDC, ctypes.POINTER(W.RECT), W.HBRUSH]
u32.DrawTextW.argtypes = [W.HDC, W.LPCWSTR, ctypes.c_int, ctypes.POINTER(W.RECT), W.UINT]
u32.SystemParametersInfoW.argtypes = [W.UINT, W.UINT, W.LPVOID, W.UINT]
u32.AllowSetForegroundWindow.argtypes = [W.DWORD]
u32.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
u32.GetWindowRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
u32.DestroyWindow.argtypes = [W.HWND]
u32.GetSystemMetrics.argtypes = [ctypes.c_int]
gdi.GetStockObject.argtypes = [ctypes.c_int]
shell32.Shell_NotifyIconW.argtypes = [W.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
k32.CreateMutexW.restype = W.HANDLE
k32.CreateMutexW.argtypes = [W.LPVOID, W.BOOL, W.LPCWSTR]
k32.GetModuleHandleW.restype = W.HMODULE
k32.GetModuleHandleW.argtypes = [W.LPCWSTR]
gdi.CreateCompatibleDC.restype = W.HDC
gdi.CreateCompatibleDC.argtypes = [W.HDC]
gdi.CreateDIBSection.restype = W.HBITMAP
gdi.CreateDIBSection.argtypes = [W.HDC, ctypes.c_void_p, W.UINT, ctypes.POINTER(ctypes.c_void_p), W.HANDLE, W.DWORD]
gdi.CreateBitmap.restype = W.HBITMAP
gdi.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, W.UINT, W.UINT, W.LPVOID]
gdi.SelectObject.restype = W.HGDIOBJ
gdi.SelectObject.argtypes = [W.HDC, W.HGDIOBJ]
gdi.DeleteObject.argtypes = [W.HGDIOBJ]
gdi.DeleteDC.argtypes = [W.HDC]
gdi.CreateSolidBrush.restype = W.HBRUSH
gdi.CreateSolidBrush.argtypes = [W.COLORREF]
gdi.GetStockObject.restype = W.HGDIOBJ
gdi.RoundRect.argtypes = [W.HDC] + [ctypes.c_int] * 6
gdi.SetBkMode.argtypes = [W.HDC, ctypes.c_int]
gdi.SetTextColor.argtypes = [W.HDC, W.COLORREF]
gdi.CreateFontW.restype = W.HFONT
gdi.CreateFontW.argtypes = [ctypes.c_int] * 5 + [W.DWORD] * 8 + [W.LPCWSTR]


def rgb(r, g, b):
    return r | (g << 8) | (b << 16)


BLUE, GRAY, WHITE = rgb(0x31, 0x82, 0xf6), rgb(0x8a, 0x93, 0xa3), rgb(0xff, 0xff, 0xff)


def make_icon(text, color):
    """둥근 사각형 위에 숫자 하나. 32비트 색 그림의 투명도는 0 이라, 모서리 투명은 흑백 마스크로 낸다."""
    size = max(16, u32.GetSystemMetrics(49))  # SM_CXSMICON (DPI 를 따른다)
    screen = u32.GetDC(None)
    dc = gdi.CreateCompatibleDC(screen)
    bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), size, -size, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    color_bmp = gdi.CreateDIBSection(dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    mask_bmp = gdi.CreateBitmap(size, size, 1, 1, None)
    radius = max(4, size // 4)
    try:
        # 마스크: 흰색(1) = 투명, 검은 둥근 사각형(0) = 보임
        old = gdi.SelectObject(dc, mask_bmp)
        full = W.RECT(0, 0, size, size)
        u32.FillRect(dc, ctypes.byref(full), gdi.GetStockObject(0))  # WHITE_BRUSH
        gdi.SelectObject(dc, gdi.GetStockObject(4))  # BLACK_BRUSH
        gdi.RoundRect(dc, 0, 0, size, size, radius, radius)
        # 색: 둥근 사각형 + 흰 숫자
        gdi.SelectObject(dc, color_bmp)
        u32.FillRect(dc, ctypes.byref(full), gdi.GetStockObject(4))
        brush = gdi.CreateSolidBrush(color)
        gdi.SelectObject(dc, brush)
        gdi.SelectObject(dc, gdi.GetStockObject(8))  # NULL_PEN
        gdi.RoundRect(dc, 0, 0, size + 1, size + 1, radius, radius)
        font = gdi.CreateFontW(-int(size * (0.72 if len(text) < 2 else 0.58)), 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 5, 0, 'Segoe UI')
        gdi.SelectObject(dc, font)
        gdi.SetBkMode(dc, 1)  # TRANSPARENT
        gdi.SetTextColor(dc, WHITE)
        u32.DrawTextW(dc, text, -1, ctypes.byref(full), 0x1 | 0x4 | 0x20)  # CENTER | VCENTER | SINGLELINE
        gdi.SelectObject(dc, old)
        info = ICONINFO(True, 0, 0, mask_bmp, color_bmp)
        icon = u32.CreateIconIndirect(ctypes.byref(info))
        gdi.DeleteObject(font)
        gdi.DeleteObject(brush)
        return icon
    finally:
        gdi.DeleteObject(color_bmp)
        gdi.DeleteObject(mask_bmp)
        gdi.DeleteDC(dc)
        u32.ReleaseDC(None, screen)


def read_state():
    """(보드가 살아 있나, 세션 목록). 보드가 STALE 초 넘게 상태를 안 고쳤으면 꺼진 것."""
    try:
        with open(B.STATE, encoding='utf-8') as f:
            state = json.load(f)
    except (OSError, ValueError):
        return False, []
    if time.time() - state.get('at', 0) > STALE:
        return False, []
    return True, state.get('sessions') or []


def waited(sec):
    sec = max(0, int(time.time() - (sec or time.time())))
    return 'now' if sec < 60 else '%dm' % (sec // 60) if sec < 3600 else '%dh' % (sec // 3600) if sec < 86400 else '%dd' % (sec // 86400)


def ensure_board():
    """Claude·Codex 가 떠 있는데 보드가 꺼져 있으면 다시 켠다 (맥 메뉴바 플러그인과 같은 일)."""
    try:
        if not B.watching() and B.agent_pids():
            winplat.spawn_detached(winplat.python_cmd() + [os.path.join(HERE, 'board.py'), '--ensure'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:  # 트레이는 계속 떠 있어야 한다
        sys.stderr.write('tray ensure: %s\n' % e)


def start_board():
    winplat.spawn_detached(winplat.python_cmd() + [os.path.join(HERE, 'board.py'), '--ensure'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def edge():
    for p in (shutil.which('msedge'),
              os.path.join(os.environ.get('ProgramFiles(x86)', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
              os.path.join(os.environ.get('ProgramFiles', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe')):
        if p and os.path.exists(p):
            return p
    return None


def open_panel():
    """작은 보드 패널을 오른쪽 아래(트레이 옆)에 연다. 이미 열려 있으면 앞으로."""
    for pid, hwnd in winplat._top_windows().items():
        if os.path.basename(winplat.exe_path(pid)).lower() == 'msedge.exe':
            title = ctypes.create_unicode_buffer(256)
            u32.GetWindowTextW(hwnd, title, 256)
            r = W.RECT()
            u32.GetWindowRect(hwnd, ctypes.byref(r))
            if title.value == 'Spyhop' and r.right - r.left < 600:  # 패널 창 (전체 보드보다 좁다)
                u32.SetForegroundWindow(hwnd)
                return
    exe = edge()
    if not exe:
        os.startfile(PANEL_URL)
        return
    work = W.RECT()
    u32.SystemParametersInfoW(0x30, 0, ctypes.byref(work), 0)  # SPI_GETWORKAREA
    w, h = 380, 560
    subprocess.Popen([exe, '--app=' + PANEL_URL, '--window-size=%d,%d' % (w, h),
                      '--window-position=%d,%d' % (max(0, work.right - w - 12), max(0, work.bottom - h - 12))],
                     creationflags=winplat.CREATE_NO_WINDOW)


def go(handle):
    """보드에게 그 세션으로 가 달라고 한다. 방금 사용자가 누른 트레이가 앞으로 가져오기 권한을 보드에 넘겨준다."""
    u32.AllowSetForegroundWindow(0xFFFFFFFF)  # ASFW_ANY
    try:
        urllib.request.urlopen(BOARD_URL + 'switch?h=' + quote(handle, safe=''), timeout=8).read()
    except OSError:
        pass


class Tray:
    def __init__(self):
        self.nid = None  # 창을 만드는 동안 오는 메시지가 아래 값들을 찾지 않게 먼저 둔다
        self.hinst = k32.GetModuleHandleW(None)
        self.proc = WNDPROC(self.wndproc)  # 참조를 붙들어 둔다 (안 그러면 콜백이 사라진다)
        wc = WNDCLASSW(0, self.proc, 0, 0, self.hinst, None, None, None, None, 'SpyhopTray')
        u32.RegisterClassW(ctypes.byref(wc))
        self.taskbar_created = u32.RegisterWindowMessageW('TaskbarCreated')  # 탐색기가 다시 뜨면 아이콘을 다시 단다
        self.hwnd = u32.CreateWindowExW(0, 'SpyhopTray', 'Spyhop', 0, 0, 0, 0, 0, None, None, self.hinst, None)
        self.icon = None
        self.key = None
        self.sessions = []
        self.ensured = 0
        self.nid = NOTIFYICONDATAW()
        self.nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self.nid.hWnd = self.hwnd
        self.nid.uID = 1
        self.nid.uCallbackMessage = WM_TRAY
        self.refresh(add=True)
        u32.SetTimer(self.hwnd, 1, TICK_MS, None)

    def refresh(self, add=False):
        if time.time() - self.ensured > ENSURE_EVERY:
            self.ensured = time.time()
            ensure_board()
        up, ss = read_state()
        self.sessions = ss
        wait = sum(1 for s in ss if s.get('status') == 'wait')
        busy = sum(1 for s in ss if s.get('status') == 'busy')
        text = (str(wait) if wait < 100 else '99') if wait else '·'
        color = BLUE if up else GRAY
        tip = ('Spyhop · My turn %d · Working %d' % (wait, busy)) if up else 'Spyhop · board is off'
        key = (text, color, tip)
        if key == self.key and not add:
            return
        old, self.icon, self.key = self.icon, make_icon(text, color), key
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP
        self.nid.hIcon = self.icon
        self.nid.szTip = tip[:127]
        if not shell32.Shell_NotifyIconW(NIM_ADD if add else NIM_MODIFY, ctypes.byref(self.nid)):
            sys.stderr.write('tray: could not %s the icon\n' % ('add' if add else 'update'))
        if old:
            u32.DestroyIcon(old)

    def menu(self):
        up, ss = read_state()
        m = u32.CreatePopupMenu()
        if up:
            wait = [s for s in ss if s.get('status') == 'wait']
            u32.AppendMenuW(m, MF_STRING | MF_GRAYED, 0, 'My turn %d · Working %d' % (len(wait), len(ss) - len(wait)))
            u32.AppendMenuW(m, MF_SEPARATOR, 0, None)
            for i, s in enumerate(ss[:MAX_ROWS]):
                title = (s.get('title') or 'Session').replace('&', '&&').replace('\n', ' ')
                if len(title) > 40:
                    title = title[:39] + '…'
                mark = '●' if s.get('status') == 'wait' else '○'
                prog = '%d/%d' % (s['done'], s['total']) if s.get('total') else '—'
                u32.AppendMenuW(m, MF_STRING, ID_SESSION + i, '%s  %s\t%s · %s' % (mark, title, prog, waited(s.get('since'))))
            if len(ss) > MAX_ROWS:
                u32.AppendMenuW(m, MF_STRING | MF_GRAYED, 0, '… %d more on the board' % (len(ss) - MAX_ROWS))
            if not ss:
                u32.AppendMenuW(m, MF_STRING | MF_GRAYED, 0, 'No AI sessions open')
            u32.AppendMenuW(m, MF_SEPARATOR, 0, None)
            u32.AppendMenuW(m, MF_STRING, ID_OPEN_PANEL, 'Open panel')
            u32.AppendMenuW(m, MF_STRING, ID_OPEN_BOARD, 'Open full board')
        else:
            u32.AppendMenuW(m, MF_STRING | MF_GRAYED, 0, 'Board is off · starts when Claude or Codex runs')
            u32.AppendMenuW(m, MF_STRING, ID_START, 'Start the board now')
        u32.AppendMenuW(m, MF_SEPARATOR, 0, None)
        u32.AppendMenuW(m, MF_STRING, ID_QUIT, 'Hide tray icon')
        pt = W.POINT()
        u32.GetCursorPos(ctypes.byref(pt))
        u32.SetForegroundWindow(self.hwnd)  # 이렇게 해야 바깥을 누르면 메뉴가 닫힌다
        cmd = u32.TrackPopupMenu(m, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY, pt.x, pt.y, 0, self.hwnd, None)
        u32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        u32.DestroyMenu(m)
        if cmd >= ID_SESSION and cmd - ID_SESSION < len(ss):
            go(ss[cmd - ID_SESSION]['handle'])
        elif cmd == ID_OPEN_PANEL:
            open_panel()
        elif cmd == ID_OPEN_BOARD:
            os.startfile(BOARD_URL)
        elif cmd == ID_START:
            start_board()
        elif cmd == ID_QUIT:
            u32.DestroyWindow(self.hwnd)

    def wndproc(self, hwnd, msg, wp, lp):
        try:
            if msg == WM_TRAY:
                if lp == WM_LBUTTONUP:
                    if read_state()[0]:
                        open_panel()
                    else:
                        self.menu()
                elif lp in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self.menu()
                return 0
            if msg == WM_TIMER:
                self.refresh()
                return 0
            if msg == self.taskbar_created:
                self.refresh(add=True)
                return 0
            if msg == WM_DESTROY:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
                u32.PostQuitMessage(0)
                return 0
        except Exception as e:  # 콜백에서 예외가 새면 트레이가 멈춘다
            sys.stderr.write('tray: %s\n' % e)
            return 0
        return u32.DefWindowProcW(hwnd, msg, wp, lp)

    def run(self):
        msg = W.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))


def main():
    # 트레이는 하나만 (spyhop.cmd 를 여러 번 눌러도)
    k32.CreateMutexW(None, False, 'Local\\SpyhopTray')
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return
    try:
        u32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2: 아이콘이 흐리지 않게
    except (AttributeError, OSError):
        pass
    if '--start-board' in sys.argv and not B.watching():
        start_board()
    Tray().run()


if __name__ == '__main__':
    main()
