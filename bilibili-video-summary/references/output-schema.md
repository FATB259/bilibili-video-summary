# 输出结构与文档要求

推荐结构：

```text
outputs/BV号/
  metadata.json
  subtitles/
    raw.txt
    cleaned.md
    transcription.json
  analysis/
    notes.docx
    claims.json        # 需要断言核验时生成
  failures.json        # 失败时生成
```

每条视频必须有 Word 文档。批量任务额外生成总览文档，列出处理顺序、成功/失败项和文件路径。

Word 主体按视频类型选择章节，公共部分只有视频信息、核心结论、类型/置信度、对用户最重要的内容、简短来源边界。完整整理阅读版字幕放在后半部分或附录；原始逐行文本单独保存。广告段落从整理版正文排除。

失败记录至少包含：视频信息、失败阶段、已尝试方法、失败原因、是否有部分文件和建议动作。
