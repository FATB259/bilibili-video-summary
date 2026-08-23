# 字幕提取与入口边界

## 入口

- 直接视频链接、BV号或短链接：解析视频详情。
- 动态链接：读取动态的挂载视频对象，再补齐视频详情。
- 稍后再看：使用已登录的 B 站客户端，优先后台连接现有调试接口；需要启动客户端时尽量最小化，不打开可见浏览器抢占用户当前会话。浏览器扩展不能注入客户端。
- 收藏、历史：沿用客户端授权边界，但在没有经过真实验证的稳定脚本时，不宣称已经自动支持。

稍后再看读取命令：

```text
node scripts/read_watch_later.js --limit 20 --output outputs/watch-later.json --sources-output outputs/watch-later-sources.txt
python scripts/batch_index.py init outputs/batch-index.json --source-file outputs/watch-later-sources.txt
```

客户端调试端口默认 `9223`，实际配置不同则使用 `--debug-port`。脚本只通过客户端页面执行带登录状态的 API 请求，不读取或输出 Cookie 内容。

统一视频记录：`source_type`、`source_url`、`order`、`bvid`、`aid`、`cid`、`title`、`owner`、`duration_seconds`。

## 原生字幕阶段

单条视频默认运行：

```text
python scripts/extract_bilibili.py <BV号或链接> --output-root outputs
```

脚本先读取视频详情和分页，再优先调用 WBI 播放器字幕接口。未登录返回 `-101` 时允许使用公开播放器接口降级，但后者只有在字幕正文实际非空时才算成功。浏览器中的字幕下载器、字幕提取器和 SubBatch 都主要读取 B 站已有字幕，不能把它们当成三种独立转写引擎。

- 直接字幕接口：默认路径。
- 浏览器插件：仅在视频通过浏览器打开且插件能访问页面时使用。
- SubBatch：用于批量、合集、收藏或接口兼容备用，不对单条视频机械重复。

## 本地转写阶段

原生字幕为空时：

```text
python scripts/extract_bilibili.py <BV号或链接> --output-root outputs --download-audio
python scripts/transcribe_local.py outputs/<BV号>/audio.m4s --output outputs/<BV号>/subtitles/raw.txt --metadata-output outputs/<BV号>/subtitles/transcription.json
```

受限视频可通过 `--cookie-file <Netscape格式文件>` 使用用户已授权的登录状态。Cookie 文件必须位于仓库外，不复制、不提交、不在日志中显示内容。提取脚本不保存临时签名音频 URL。

出现 `HTTP 412`、`403` 或签名失效时，不重复轰炸接口；刷新已授权页面环境或 Cookie 后最多重试一次。仍失败就生成 `failures.json`。不要调用在线转写服务，不使用 OCR，不自动升级 `small`。

成功条件：输出非空、语言合理、覆盖主要时长、开头/中段/结尾可读。失败时生成失败记录并停止该视频；批量任务继续其他视频。

## 批量与续跑

```text
python scripts/batch_index.py init outputs/batch-index.json <链接1> <链接2>
python scripts/batch_index.py pending outputs/batch-index.json --include-failed
python scripts/batch_index.py update outputs/batch-index.json <BV号> --status extracting
```

状态依次为 `pending`、`extracting`、`transcribing`、`analyzing`、`completed` 或 `failed`。恢复任务时只处理 `pending` 和中断状态；只有用户要求重试时才包含 `failed`。
