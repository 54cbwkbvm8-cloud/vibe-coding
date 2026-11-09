# 配置说明

## 配置文件位置

普通设置：

```text
%APPDATA%\AIQuizOverlay\config.json
```

API Key 密文：

```text
%APPDATA%\AIQuizOverlay\api_key.bin
```

配置目录内部的英文包名保持不变，改名和个性化不会迁移或删除现有配置与
API Key。旧配置升级到 schema 2 时会增量补默认值，并递归保留程序不认识的
字段。

## 常用默认值

| 设置 | 默认值 |
| --- | --- |
| 接入方式 | `API 接入` |
| 工作模式 | `搜题模式` |
| 问答热键 | `Ctrl+Alt+Q` |
| 区域截图热键 | `Ctrl+Alt+A` |
| 助手唤出热键 | `Ctrl+Alt+Space` |
| 悬浮球显隐热键 | `Ctrl+Alt+B` |
| 整屏识别热键 | `Ctrl+Alt+S` |
| API Base URL | `https://api.deepseek.com` |
| 模型 | `deepseek-flash` |
| 请求超时 | 60 秒 |
| 区域截图图片长边 | 1600 px |
| 整屏识别图片长边 | 2048 px |
| 玻璃透明度 | 100% |
| 背景显示方式 | 填充 |
| 背景模糊 | 8 px |
| 背景暗化 | 55% |
| 悬浮球大小 | 64 px |
| 悬浮球位置 | 首次出现在鼠标所在屏幕右侧，之后保存 |
| 语音 | 关闭 |
| 自动开始聆听 | 关闭 |
| 识别后自动发送 | 关闭 |
| 静音判定 | 1.2 秒 |
| 最长录音 | 30 秒 |
| 聆听开始提示音 | 开启 |

快捷键必须至少包含 Ctrl、Alt、Shift 或 Win 中的一项。不同功能不能使用
相同组合。热键保存采用事务注册：任意新组合被占用时，全部临时注册都会
回滚，旧组合继续有效。

## 模型目录

语音模型不进入主发布包：

```text
%APPDATA%\AIQuizOverlay\models\sensevoice-small-int8
```

下载只允许在用户点击“开始下载”后发起。程序固定 revision、文件大小和
SHA-256，限制 HTTPS 域名与重定向，不自动切换来源，失败后允许手动重试。

## 官网组件目录

官网浏览器组件不进入主发布包：

```text
%APPDATA%\AIQuizOverlay\components
```

设置页只接受本机构建或手动导入的组件 ZIP/文件夹。导入时校验清单、文件
SHA-256、组件版本和主程序版本，通过后执行自检。

## 浏览器会话目录

```text
%APPDATA%\AIQuizOverlay\web_session
```

浏览器组件只会在用户选择浏览器模式并通过风险告知后创建。切回 API 接入、
撤销同意或退出程序时会结束辅助进程；用户可以在设置中清除全部登录数据。

## 日志

```text
%APPDATA%\AIQuizOverlay\logs
```

日志只记录事件名、状态码和状态变化，不记录 Key、Token、Cookie、完整网址、
问题、回答、图片、音频或转写文本。
