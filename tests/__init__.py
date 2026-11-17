"""测试环境加固：Windows 上偶发 Tk 初始化读不到 tk8.6 里的 .tcl 文件
（文件其实在，是瞬时的读取失败），测试里反复建销窗口时每十几次会撞上一次。
只对这一种错误重试，其他 TclError 照常抛出。"""
import time
import tkinter

_orig_init = tkinter.Tk.__init__


def _retrying_init(self, *args, **kwargs):
    for _ in range(4):
        try:
            return _orig_init(self, *args, **kwargs)
        except tkinter.TclError as exc:
            if ".tcl" not in str(exc):
                raise
            time.sleep(0.3)
    return _orig_init(self, *args, **kwargs)


tkinter.Tk.__init__ = _retrying_init
