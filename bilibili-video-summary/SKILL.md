---
name: bilibili-video-summary
description: "处理 B 站视频、动态和稍后再看内容：提取原生字幕或本地转写，并按视频类型生成可追溯的中文 Word 总结文档。"
---

# B站视频总结

当用户发送 B 站视频链接、BV号、动态链接，或要求处理稍后再看、收藏、历史视频时使用。用户只发链接也视为要求：定位视频、读取字幕、总结内容并生成 Word 文档。

## 固定交付

- 每条视频必须生成一个中文 `.docx`；批量任务再生成一个总览文档。
- Word 主体放核心分析，完整“整理阅读版字幕”放在后半部分或附录。
- 原始逐行字幕单独保存为 UTF-8 文本；不要用整理版覆盖原始文本。
- 聊天回复只给简短结论、处理状态和文件路径。

## 主流程

1. **预检环境**：首次运行、切换 Python 或转写异常时，先执行 `scripts/check_environment.py --require-docx`；需要本地转写时再加 `--require-transcription --load-model`。缺少依赖时读取 [references/setup.md](references/setup.md)。
2. **识别入口与清单**：直接链接/BV号、短链和动态交给 `scripts/extract_bilibili.py`。稍后再看使用 `scripts/read_watch_later.js` 从已登录客户端后台读取；收藏/历史使用同一客户端边界，但未提供稳定脚本时要明确说明。浏览器仅使用独立配置，不打断用户当前页面。批量任务用 `scripts/batch_index.py init` 去重并记录顺序。
3. **获取原生字幕**：运行提取脚本，优先已登录 WBI 接口，未登录时允许公开播放器接口降级，但必须下载并验证字幕正文。浏览器字幕插件和 SubBatch 只作为已有字幕的兼容入口，不机械重复。
4. **无字幕转写**：提取结果为 `needs_transcription` 时，用 `--download-audio` 获取签名音频，再运行 `scripts/transcribe_local.py`。默认 `base`、中文、GPU 优先；外语或混合语言改用 `--language auto`。失败退出码非零，不能继续汇报成功，也不自动升级 `small`。
5. **质量门控**：检查开头、中段、结尾、语言、时间轴覆盖率、乱码/重复和关键术语。少量不确定词句继续处理并写入术语清单；整段无法可靠识别则生成失败记录。
6. **分类与分析**：判断主类型与次类型并标注置信度。按需读取 [references/content-types.md](references/content-types.md)；键政内容额外读取 [references/political-language.md](references/political-language.md)。区分事实、引用、解释、预测、价值判断和 Codex 判断，只核验对结论重要且可核验的断言。
7. **生成 Word**：保存 `analysis/analysis.md` 和整理字幕，使用 `scripts/build_notes_docx.py` 生成固定结构的 Word。不确定术语通过参数传入，统一显示为红色下划线。
8. **验收并续跑**：能渲染时检查每一页并用 `scripts/record_visual_qa.py` 记录 `passed`；不能渲染时记录 `unverified` 和原因。最后运行 `scripts/validate_outputs.py`。成功后更新批量清单为 `completed`；失败项使用 `scripts/build_failure_docx.py` 生成明确的失败报告 Word，再更新为 `failed` 并继续其他视频。

## 不确定性与广告

- 不把转写、视频引用或推断写成已核验事实。
- 不确定的人名、术语和关键句只做轻度校正；在 Word 中使用红色下划线，不大面积标注。
- 明显广告段落从整理正文和主体分析中排除；不额外展开广告利益关系分析。
- 不记录或输出 Cookie、密码、验证码、访问令牌或本地账号信息。

## 本地工具

- 环境预检：`scripts/check_environment.py`
- 原生字幕/音频提取：`scripts/extract_bilibili.py`
- 客户端稍后再看：`scripts/read_watch_later.js`
- 批量断点续跑：`scripts/batch_index.py`
- 本地转写脚本：`scripts/transcribe_local.py`
- Word 生成：`scripts/build_notes_docx.py`
- 失败报告 Word：`scripts/build_failure_docx.py`
- 视觉状态记录：`scripts/record_visual_qa.py`
- 输出验收脚本：`scripts/validate_outputs.py`
- 详细提取顺序和客户端/浏览器边界：`references/extraction.md`

不要把模型缓存、音频、字幕、Cookie、账号会话或生成文档复制进 Skill 目录或提交到 Git。脚本生成的 JSON 只保存文件名或相对路径，不保存绝对本地路径和临时签名 URL。
