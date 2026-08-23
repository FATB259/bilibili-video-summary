# Windows 本地环境

## Python 依赖

使用 Python 3.10 或更高版本，在 Skill 目录执行：

```text
python -m pip install -r requirements.txt
python scripts/check_environment.py --require-docx
```

需要本地转写时执行：

```text
python scripts/check_environment.py --require-docx --require-transcription --load-model --model base
```

`--load-model` 会实际加载模型，可能需要读取本地缓存或首次下载。默认只在首次配置、Python 环境变化或 CUDA 故障时使用。

处理稍后再看时需要支持全局 `WebSocket` 的现代 Node.js。先运行：

```text
python scripts/check_environment.py --require-client
node scripts/read_watch_later.js --help
```

Codex 桌面环境中如果 `node` 不在系统 PATH，先通过工作区依赖定位 Codex 自带 Node，再用其完整路径执行脚本。

## GPU 与 CPU

检测到 `nvidia-smi` 时默认尝试 CUDA FP16。仅在错误明确与 CUDA、cuBLAS、cuDNN、驱动或 GPU 有关时自动降级 CPU INT8；模型、音频、权限和磁盘错误必须原样失败，不能伪装成 GPU 问题。

系统 `ffmpeg` 不是所有转写路径的硬性前提，但建议安装，便于音频检查和格式转换。以 `check_environment.py` 的实际输出为准。

## Cookie 与账号

只有公开视频接口无法读取、但用户账号已获授权时才使用 Cookie。脚本接受 Netscape 格式 Cookie 文件：

```text
python scripts/extract_bilibili.py <链接> --cookie-file <仓库外路径>
```

Cookie、SESSDATA、验证码、访问令牌、浏览器配置和客户端会话文件不得进入 Skill 目录、输出文档或 Git。

## Word 视觉验收

Word 生成脚本会把视觉状态初始化为 `unverified`。使用可用的 DOCX 渲染工具生成页面 PNG，逐页检查分页、溢出、字体和红色下划线后，再运行：

```text
python scripts/record_visual_qa.py outputs/<BV号> --status passed --renderer libreoffice --page-count <页数>
```

缺少渲染器时保留 `unverified` 并在交付说明中明确报告，不能写成视觉通过。
