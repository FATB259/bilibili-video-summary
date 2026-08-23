# Bilibili Video Summary Skill

一个用于 Codex 的 B 站视频总结 Skill：从直接链接、BV 号、动态或稍后再看入口定位视频，优先提取原生字幕，缺失时使用本地 `faster-whisper base` 转写，并生成可追溯、可验证的中文 Word 总结文档。

## 特性

- 每条视频生成独立 `.docx`，批量任务额外生成总览文档。
- 原生字幕优先；本地转写作为唯一降级路径。
- 不使用 OCR、BibiGPT 或在线转写服务，不自动升级到 `small`。
- 按 AI/科技、键政/社会、知识、教程、评测、访谈等类型采用不同分析结构。
- 将事实、引用、预测、价值判断和作者判断分开；不确定术语在 Word 中用红色下划线标记。
- 保留原始 UTF-8 字幕、整理版字幕和失败记录，便于复核。
- 提供环境预检、原生字幕提取、签名音频下载、断点续跑、Word 生成和严格产物验证脚本。
- 支持通过已登录 B 站客户端后台读取稍后再看清单，不导出 Cookie。
- 验证器检查 DOCX 的 OOXML 完整性，并区分结构通过与视觉验收通过。

## 安装

将 `bilibili-video-summary` 目录复制到 `$CODEX_HOME/skills/`。Windows 默认安装位置：

```text
C:\Users\<用户名>\.codex\skills\bilibili-video-summary
```

安装 Python 依赖并运行预检：

```text
python -m pip install -r requirements.txt
python scripts/check_environment.py --require-docx
```

首次使用本地转写前：

```text
python scripts/check_environment.py --require-docx --require-transcription --load-model --model base
```

模型缓存、音频、字幕、Cookie 和账号会话文件不应放入本仓库。

## 使用

直接发送 B 站视频链接、BV 号、动态链接，或说明“处理稍后再看”，即可触发完整流程。Skill 会在可行时生成 Word 文档，并在失败时单独记录原因，不让单条失败阻塞批量任务。

也可以单独测试提取：

```text
python scripts/extract_bilibili.py BV1xxxxxxxxxx --output-root outputs
```

无原生字幕时下载音频：

```text
python scripts/extract_bilibili.py BV1xxxxxxxxxx --output-root outputs --download-audio
```

Cookie 仅用于用户已授权的受限内容，必须放在仓库外并通过 `--cookie-file` 临时传入。

## 验证

```text
python scripts/validate_outputs.py outputs/BV1xxxxxxxxxx
```

验证成功只证明文件、JSON、字幕和 DOCX 结构有效。只有页面渲染并逐页检查后，`analysis/visual-qa.json` 才能记录为 `passed`；缺少渲染器时必须保持 `unverified`。

## 目录

```text
bilibili-video-summary/
  SKILL.md
  agents/openai.yaml
  references/       # 安装、提取、分类、政治语言和输出规范
  scripts/          # 预检、提取、转写、批量、Word 和验收脚本
  requirements.txt
```

## 许可

MIT，见 [LICENSE](LICENSE)。
