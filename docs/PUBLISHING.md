# 独立公开目录的准备与发布

本流程先准备可审核的本地内容，再由维护者在独立目录创建全新 Git 历史。
准备工具不初始化 Git、不配置远程仓库，也不上传文件。

## 1. 检查并生成归档

在本工具的源码目录运行：

```sh
python -B -m unittest discover -s tests -v
python -B tools/build_release.py --check
python -B tools/build_release.py --output ../event-relation-toolkit-public.zip
```

已有同名 ZIP 时，选择新的输出文件名。发布器不会覆盖现有归档。演示输出
必须放在源码目录之外；`private_data` 或 `local_runs` 出现在源码树任何位置
都会阻止打包，包括空目录、大小写变体和被排除目录内部。

逐项审核全部归档内容，包括源代码、测试、注释、文档、配置、合成示例及
`RELEASE_MANIFEST.json`。确认没有真实数据、真实派生值、身份线索或私人来源
的复制内容。清单中的文件哈希证明内容一致，不证明内容天然安全。

在 Windows PowerShell 中获取已审核 ZIP 的完整 SHA-256：

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath ../event-relation-toolkit-public.zip
```

记录这次审核对应的哈希。后续文件发生变化时必须重新审核，不能沿用旧结论。

## 2. 从归档创建独立目录

选择一个尚不存在的新目录，其父目录必须已经存在，且目标必须位于整个私人
项目工作区之外。不得选用私人工作区内部的 `outputs`、`public` 或其他子目录；
也不得选用任何现有 Git 仓库的内部目录。准备工具还会拒绝已存在的目标目录
以及带有 `.git` 的祖先目录。

以下命令中的四个尖括号内容均为占位符，需要替换为本机实际值。路径只在
本机输入，不要将填写后的命令、终端截图或日志贴到公开页面。

```sh
python -B tools/prepare_public_repo.py --archive "<reviewed-zip>" --destination "<new-independent-directory>" --private-root "<entire-private-workspace>" --sha256 "<reviewed-archive-sha256>"
```

`--private-root` 必填，应填写整个私人项目根目录，而不是仅填写包目录或
输出目录。有多个需要保护的来源目录时，应选择涵盖它们的私人工作区根目录，
并确保公开目录位于其外部。准备工具同时检查目标与自身源码目录的关系，
验证归档总哈希、内部清单和每个文件哈希，并按固定白名单解压。

文件直接放在新目录内；解压内容只应来自这一份经过审核的 ZIP。不要补拷外层
文件，不要复制 `.git`、旧工作树、日志或本机配置。此时仍应由维护者查看独立
目录，确认它与归档内容一致后再创建 Git 仓库。

## 3. 创建全新 Git 历史并精确暂存

先在终端切换到新建的独立目录，确认当前位置。随后运行：

```sh
python -B tools/build_release.py --check
git init
```

在第一次提交前检查准备公开的作者姓名和提交邮箱。全新仓库仍可能继承本机
全局 Git 身份配置；需要按自己的保密要求设置仓库级身份，不能直接沿用私人
作者信息。也要单独核对拟使用账号的公开资料、仓库名称和介绍。

下面的 PowerShell 命令只暂存清单列出的路径及清单本身：

```powershell
$releaseManifest = Get-Content -LiteralPath RELEASE_MANIFEST.json -Raw | ConvertFrom-Json
$releasePaths = @($releaseManifest.files | ForEach-Object { $_.path }) + @('RELEASE_MANIFEST.json')
git add -- $releasePaths
git diff --cached --name-only
git diff --cached
git status --short
```

核对已暂存列表和内容。不要在私人项目或其父目录运行 `git add .`，也不要把
私有工作树整体拖入网页上传区。清单之外的文件需要另行审核，并同步修改
发布白名单、重建归档，再重新准备独立目录。

授权声明尚待维护者决定；见 [LICENSE_NOTICE.md](../LICENSE_NOTICE.md)。确认
许可、公开身份和已暂存内容后，维护者才进行首次提交和后续上传。不要添加
旧项目的远程地址或合并其历史。

## 4. 公开沟通与版本更新

公开贡献和问题反馈遵守 [CONTRIBUTING.md](../CONTRIBUTING.md)。纯展示用途可在
仓库设置中关闭 Issues 与 Discussions，减少上传附件或真实记录的入口。
这些平台设置需要在仓库侧单独配置，本地模板不能替代它们。

PR 模板会提醒提交者核对公开文字、附件、变更和完整提交历史。模板与文本
扫描均不能保证所有人遵守规则，维护者仍需审核提交说明和历史中的每个版本。
禁止公开原始内容、真实派生结果、媒体截图、日志、模型权重和身份元数据。

每次修改 README、授权、源码或示例后，都应重跑测试与发布检查，并审核新归档。
归档固定文件顺序、时间、权限和 LF 换行，相同文本可生成相同归档字节。
`RELEASE_MANIFEST.json` 不记录构建时间，也不包含自身哈希；其完整性由审核时
记录的归档总 SHA-256 覆盖。
