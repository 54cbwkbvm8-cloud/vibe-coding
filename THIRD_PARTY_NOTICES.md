# 第三方声明与许可信息

本文件随「奶蛙的荣光」1.0.0 发布包提供。版本以发布时的
`requirements.lock`、`requirements-build.txt` 和实际构建产物为准。许可证
名称来自各项目随发行包提供的元数据或官方项目页面；完整许可证文本以各
项目发行包和官方仓库为准。

## 运行时依赖

| 组件 | 版本 | 许可证 | 来源 |
| --- | --- | --- | --- |
| Python | 3.11.9 | PSF-2.0 | https://www.python.org/ |
| PySide6-Essentials | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | https://pypi.org/project/PySide6-Essentials/ |
| PySide6-WebEngine（可选组件） | 6.12.0.140 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | https://pypi.org/project/PySide6-WebEngine/ |
| shiboken6 | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | https://pypi.org/project/shiboken6/ |
| Qt 6 | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | https://www.qt.io/ |
| Chromium（QtWebEngine 内置） | 140.0.7339.225 | 多重开源许可证 | https://www.chromium.org/ |
| sherpa-onnx | 2.0.1 | Apache-2.0 | https://github.com/k2-fsa/sherpa-onnx |
| sherpa-onnx-core | 2.0.1 | Apache-2.0 | https://github.com/k2-fsa/sherpa-onnx |
| onnxruntime | 1.28.2 | MIT | https://github.com/microsoft/onnxruntime |
| PortAudio | sounddevice 0.5.6 wheel 内置 DLL | MIT | https://www.portaudio.com/ |
| sounddevice | 0.5.6 | MIT | https://python-sounddevice.readthedocs.io/ |
| webrtcvad-wheels | 2.0.14.post1 | MIT | https://github.com/daanzu/webrtcvad-wheels |
| cffi | 2.1.1 | MIT-0 | https://github.com/python-cffi/cffi |
| pycparser | 3.12 | BSD-3-Clause | https://github.com/eliben/pycparser |
| httpx | 0.28.1 | BSD-3-Clause | https://www.python-httpx.org/ |
| httpcore | 1.0.9 | BSD-3-Clause | https://github.com/encode/httpcore |
| h11 | 0.16.0 | MIT | https://github.com/python-hyper/h11 |
| anyio | 4.16.0 | MIT | https://github.com/agronholm/anyio |
| certifi | 2026.10.23 | MPL-2.0 | https://github.com/certifi/python-certifi |
| idna | 3.20 | BSD-3-Clause | https://github.com/kjd/idna |
| typing_extensions | 4.16.0 | PSF-2.0 | https://github.com/python/typing_extensions |

## 构建工具

| 组件 | 版本 | 许可证或说明 |
| --- | --- | --- |
| PyInstaller | 6.22.3 | GPL-2.0-or-later with bootloader exception |
| altgraph | 0.17.5 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pefile | 2024.8.26 | MIT |
| pyinstaller-hooks-contrib | 2026.9 | Apache-2.0 |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause |
| Pillow（仅素材准备） | 12.3.0 | MIT-CMU |

## 可选官网组件

官网浏览器组件不进入主发布包，需要用户在本机构建并手动导入。组件构建时
使用 PySide6-WebEngine 和 QtWebEngine，组件及其中的 Chromium、Qt 第三方
组件继续适用各自的许可证。完整许可证文本以实际组件构建目录和 Qt、
Chromium 随附文件为准。

DeepSeek 网站内容、登录服务及第三方登录服务由第三方提供，不由本项目重新
许可。相关内容和商标归各自所有者。

## 模型文件

本地语音模型 SenseVoiceSmall int8 不随发布包提供。用户下载或手动导入后，
文件保存到：

```text
%APPDATA%\AIQuizOverlay\models\sensevoice-small-int8
```

固定 revision、文件大小、SHA-256、来源和许可证信息由程序内模型安装模块
及 [docs/BUILDING.md](docs/BUILDING.md) 说明。模型不是本项目重新许可的
资产；再分发模型前应自行复核上游许可证和适用条款。
