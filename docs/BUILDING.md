# 构建与打包

## 系统要求

- Windows 10/11 x64
- Python 3.11 x64
- 主程序依赖见 `requirements.lock`
- 构建依赖见 `requirements-build.txt`
- 可选官网组件依赖见 `requirements-official-web.txt`

确认解释器和 Python 架构：

```powershell
py -3.11 -c "import platform, struct, sysconfig; print(platform.machine()); print(sysconfig.get_platform()); print(struct.calcsize('P') * 8)"
```

应看到 64 位和 `win-amd64`。在 ARM64 Windows 中使用 x64 Python 模拟可以
构建 x64 包，但性能不代表物理 x64 真机。

## 创建环境

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install --only-binary=:all: -r requirements.lock
python -m pip install -r requirements-build.txt
```

不要把 `.venv` 放在 Parallels 共享目录。

## 运行测试

```powershell
python -m unittest discover -s tests -v
```

自动测试使用本地模拟 API、本地模拟网页、合成截图和合成音频，不需要真实
账号、真实 Key 或真实屏幕内容。

## 构建主程序

```powershell
powershell -ExecutionPolicy Bypass -File .\build\build.ps1
```

主要产物：

```text
dist\奶蛙的荣光\奶蛙的荣光.exe
dist\奶蛙的荣光\_internal\
```

检查架构和发布目录：

```powershell
powershell -ExecutionPolicy Bypass -File .\build\check_pe_arch.ps1 `
  -ExePath .\dist\奶蛙的荣光\奶蛙的荣光.exe
powershell -ExecutionPolicy Bypass -File .\build\check_bundle.ps1 `
  -BundlePath .\dist\奶蛙的荣光 `
  -WorkPath .\build\pyinstaller
```

## 生成 ZIP

```powershell
powershell -ExecutionPolicy Bypass -File .\build\package.ps1
```

包脚本会生成 ZIP 和 `.sha256` 文件，并拒绝把配置、Key 密文、模型、日志、
个人化资产、诊断模块和 WebEngine 组件混入主包。

## 构建可选官网组件

先安装可选依赖：

```powershell
python -m pip install -r requirements-official-web.txt
```

在 Windows x64 Python 环境中构建：

```powershell
python .\build\build_official_web_component.py `
  --output-dir .\outputs\official-web-component
```

构建脚本生成：

```text
official-web-component.zip
official-web-manifest.json
official_web_component_expected.py
```

组件 ZIP 和清单不进入主发布包，也不上传到 GitHub Release。构建完成后，
在软件设置页选择“导入组件”，选择本地 ZIP 或已解压文件夹。导入流程会检查：

1. 清单版本与主程序版本匹配；
2. 文件列表完整且没有多余路径；
3. 每个文件 SHA-256 与清单一致；
4. ZIP 不包含 `..`、绝对路径、链接、设备文件或超限内容；
5. 安装后辅助程序自检通过。

期望清单哈希由构建脚本生成并写入
`src/ai_quiz_overlay/services/official_web_component_expected.py`。这个固定
哈希可检测损坏和版本错配，但不能证明组件来源可信；只应导入自己构建或
完全信任的组件。

## 语音模型

模型不随 exe 打包。用户应在设置页选择来源并点击“开始下载”，或手动导入
合法模型文件夹。程序固定 revision、文件大小和 SHA-256，哈希不一致时
删除临时文件并拒绝使用。

模型目录：

```text
%APPDATA%\AIQuizOverlay\models\sensevoice-small-int8
```

固定元数据定义在 `src/ai_quiz_overlay/services/voice_models.py`。详细来源
和许可证见 `THIRD_PARTY_NOTICES.md`。

## 无 Python 环境验收

建议使用新建的干净 Windows 虚拟机或快照，而不是只新建一个 Windows 用户。
在目标环境中确认：

```text
where python  -> 找不到命令
where py      -> 找不到命令
```

然后解压 ZIP，双击 exe，检查主窗口、托盘、快捷键、基础问答、设置保存和
退出。真实 Key、真实麦克风、模型下载、真实屏幕和官网账号操作仍需单独
手动验收。

## SmartScreen 与误报

当前发布包没有代码签名。未签名 exe 可能触发 SmartScreen 或杀毒软件启发式
误报。请先从官方仓库和固定 SHA-256 确认文件，再决定是否运行。正式分发
建议使用代码签名证书，不要通过关闭安全软件解决。
