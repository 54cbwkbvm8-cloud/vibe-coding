"""Windows 专用实现包。

本包中的模块必须允许在非 Windows 系统上被导入。Win32 API 的导入和调用
应放在函数内部，并先调用 platform_support.require_windows()。
"""
