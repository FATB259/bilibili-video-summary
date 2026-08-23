# 输出结构与文档要求

每条视频使用唯一结构：

```text
outputs/BV号/
  metadata.json
  subtitles/
    raw.txt
    cleaned.md
    native.json         # 仅原生字幕时保留接口原文
    transcription.json  # 仅本地转写时生成
  analysis/
    analysis.md
    notes.docx
    visual-qa.json     # passed / unverified
    uncertain-terms.json # 有不确定术语时生成
    claims.json        # 需要断言核验时生成
  failures.json        # 失败时生成
```

成功任务必须包含 `metadata.json`、非空的 `subtitles/raw.txt`、`subtitles/cleaned.md`、`analysis/analysis.md`、有效的 `analysis/notes.docx` 和 `analysis/visual-qa.json`。`metadata.json` 至少记录 `bvid`、`title`、`status`、字幕来源和相对输出路径，不写绝对本地路径。原生字幕任务保留 `native.json`，不生成 `transcription.json`；本地转写任务必须生成 `transcription.json`，且其中 `status` 为 `success`、时间轴覆盖率达到脚本阈值。

失败任务生成 `failures.json`，至少包含 `stage`、`reason`、`attempted_methods` 和 `suggested_action`，并使用 `scripts/build_failure_docx.py` 生成 `analysis/notes.docx` 失败报告。使用 `scripts/validate_outputs.py <目录> --expect failure` 单独验证，不能把失败报告写成内容总结成功。

批量任务在 `outputs/batch-index.json` 记录顺序和状态，并额外生成总览文档。每条视频都必须有 Word：成功项是内容总结，失败项是明确标注的失败报告。

Word 主体按视频类型选择章节，公共部分只有视频信息、核心结论、类型/置信度、对用户最重要的内容、简短来源边界。完整整理阅读版字幕放在后半部分或附录；原始逐行文本单独保存。广告段落从整理版正文排除。

成功后运行：

```text
python scripts/validate_outputs.py outputs/BV号
```

结构校验通过不等于 Word 视觉验收通过。能使用文档渲染工具时必须渲染页面并检查分页、溢出、字体和红色下划线；不能渲染时明确写“结构通过，视觉未验证”。
