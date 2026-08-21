# Bilibili Video Summary Skill

一个用于 Codex 的 B 站视频总结 Skill：从直接链接、BV 号、动态或稍后再看入口定位视频，优先提取原生字幕，缺失时使用本地 `faster-whisper base` 转写，并生成可追溯的中文 Word 总结文档。

## 特性

- 每条视频生成独立 `.docx`，批量任务额外生成总览文档。
- 原生字幕优先；本地转写作为唯一降级路径。
- 不使用 OCR、BibiGPT 或在线转写服务，不自动升级到 `small`。
- 按 AI/科技、键政/社会、知识、教程、评测、访谈等类型采用不同分析结构。
- 将事实、引用、预测、价值判断和作者判断分开；不确定术语在 Word 中用红色下划线标记。
- 保留原始 UTF-8 字幕、整理版字幕和失败记录，便于复核。

## 安装

将 `bilibili-video-summary` 目录复制到 `$CODEX_HOME/skills/`（Windows 默认是 `C:\Users\\<用户名>\\.codex\\skills\\`），重启或刷新 Codex 后即可使用。

首次使用本地转写前，确认 Python 能导入 `faster_whisper`，并准备好 `base` 模型。模型缓存、音频、字幕和账号会话文件不应放入本仓库。

## 使用

直接发送 B 站视频链接、BV 号、动态链接，或说明“处理稍后再看”，即可触发完整流程。Skill 会在可行时生成 Word 文档，并在失败时单独记录原因，不让单条失败阻塞批量任务。

## 目录

```text
bilibili-video-summary/
  SKILL.md
  agents/openai.yaml
  references/       # 提取、分类、政治语言和输出规范
  scripts/          # 本地转写和输出验收脚本
```

## 许可

MIT，见 [LICENSE](LICENSE)。
