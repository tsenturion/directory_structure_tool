import os
import subprocess


def copy_text_to_clipboard(text):
    """Копирует текст в буфер обмена. Возвращает True при успехе."""
    if not isinstance(text, str):
        text = str(text)
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            GMEM_MOVEABLE = 0x0002
            CF_UNICODETEXT = 13

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            user32.OpenClipboard.argtypes = [wintypes.HWND]
            user32.OpenClipboard.restype = wintypes.BOOL
            user32.EmptyClipboard.argtypes = []
            user32.EmptyClipboard.restype = wintypes.BOOL
            user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
            user32.SetClipboardData.restype = wintypes.HANDLE
            user32.CloseClipboard.argtypes = []
            user32.CloseClipboard.restype = wintypes.BOOL

            kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
            kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
            kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
            kernel32.GlobalLock.restype = ctypes.c_void_p
            kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
            kernel32.GlobalUnlock.restype = wintypes.BOOL
            kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
            kernel32.GlobalFree.restype = wintypes.HGLOBAL

            # Для CF_UNICODETEXT Windows ожидает CRLF.
            normalized_text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
            data = ctypes.create_unicode_buffer(normalized_text)
            data_size = ctypes.sizeof(data)

            if not user32.OpenClipboard(None):
                return False
            try:
                if not user32.EmptyClipboard():
                    return False

                handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, data_size)
                if not handle:
                    return False

                locked = kernel32.GlobalLock(handle)
                if not locked:
                    kernel32.GlobalFree(handle)
                    return False

                ctypes.memmove(locked, data, data_size)
                kernel32.GlobalUnlock(handle)

                if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                    kernel32.GlobalFree(handle)
                    return False

                # После успешного SetClipboardData памятью владеет Windows.
                return True
            finally:
                user32.CloseClipboard()
    except Exception:
        pass

    try:
        subprocess.run(
            "clip",
            input=text,
            text=True,
            shell=True,
            encoding="utf-8",
            errors="replace",
            check=True
        )
        return True
    except Exception:
        return False
