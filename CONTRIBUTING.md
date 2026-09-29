# Public contribution rules / 公开贡献规则

## Synthetic examples only

These rules apply to Issues, pull requests, Discussions, commit messages and
history, release notes, review comments, profiles used to describe this project,
and every attachment. Public surfaces must contain only reviewed generic code,
documentation, and minimal examples invented independently of private sources.

Do not submit any of the following, even to explain a bug:

- Real source records, extracts, labels, measurements, or their derived summaries,
  aggregates, distributions, embeddings, caches, fitted parameters, or model weights.
- Screenshots, screen recordings, images, audio, or other media from private work.
- Raw logs, tracebacks, command history, environment dumps, database files, or
  configuration exports from a private environment.
- Real entity or session IDs, filenames, dates, personal or institutional details,
  absolute local paths, account names, credentials, or identifying file metadata.
- Private source material preserved in an earlier commit, a diff, a deleted file,
  an archive, a branch, or an attachment.

Renaming, cropping, sampling, rounding, adding noise, or removing a few fields does
not turn private-derived material into an independent synthetic example. A
`synthetic: true` label is not evidence of a safe source.

## Reporting and changes

Describe the general software problem in your own words. Recreate a minimal case
using only the bundled synthetic generator or new invented constants and neutral
labels. Provide the generic expected result and the synthetic actual result in
plain text. Write a short generic error description yourself; do not paste a
private log and try to redact it afterward. If the issue cannot be reproduced
without private content, do not post the private content to this repository.

Review the entire contribution and every commit, not only the final file state.
Run the tests and `python -B tools/build_release.py --check` when changing the
release source. Keep test outputs outside it. Any new public file needs explicit
allowlist review. `private_data` and `local_runs`, including empty or nested case
variants, must not exist anywhere in a release source tree.

Maintainers should request an independently invented replacement when a report
depends on private content. Do not request private samples, raw logs, screenshots,
or weights in a public follow-up. If sensitive content was already posted, do not
quote or attach it again; restrict its exposure through the relevant platform
controls. Deleting a visible file does not remove copies or prior history.

## 中文规则

这些要求适用于 Issues、PR、Discussions、提交说明与历史、发布说明、评审评论、
用于介绍本项目的页面文字，以及全部附件。公开内容只允许经过审核的通用代码、
说明和独立虚构的最小示例。

禁止提供真实记录及其摘录、标注、测量值、摘要、聚合统计、分布、嵌入、缓存、
拟合参数和模型权重；禁止私人工作的截图、录屏、图片、音频和其他媒体；禁止
原始日志、调用栈、命令历史、环境导出和数据库；禁止真实编号、文件名、日期、
机构信息、个人路径、账号、凭据和可识别元数据。删除文件后的历史版本、差异、
分支和附件同样属于审核范围。

改名、裁剪、抽样、取整、加噪或删除部分字段不能把真实来源内容变成独立合成。
问题反馈应重新构造完全虚构的最小复现，用中性标签和自行编写的简短说明描述
预期与实际结果。无法独立复现时，不要为说明问题而公开私人内容。

贡献者和维护者需检查全部变更及每一个提交，测试输出放在源码目录之外。
新增公开文件必须审核并纳入固定白名单。发现已公开的敏感内容时，不要引用、
转贴或再上传原文，应使用相应平台控制减少暴露；删除当前文件不等于清除副本
或历史记录。
