# Event Relation Toolkit

一个离线运行、便于核查的双实体通用事件关系示例工具。

[English](README.md) · [方法说明](docs/METHODS.md) · [隐私边界](docs/PRIVACY.md) · [发布步骤](docs/PUBLISHING.md) · [贡献规则](CONTRIBUTING.md)

本项目独立编写，只包含通用程序和程序化合成示例。不包含私人记录、真实数据
派生值、拟合参数、训练权重或旧 Git 历史。名称、字段和示例均不指定应用领域。

## 功能与边界

- 校验实体标签、时间、事件类型和信号与回复的显式对应关系。
- 统计信号、回复，以及单一、多个或未知发起者的区间事件。
- 同时报告区间时长之和、重叠去重后的占用时间、事件频率和时间比例。
- 使用显式配置演示连续关联回复的候选序列。
- 在本机输出确定性的 JSON，不联网，不使用外部服务。
- 通过文件白名单生成文本发布包，并在独立目录准备前重新验证归档。

输入必须是使用者已经提供的事件记录。程序不从媒体推断事件，不训练模型，
不将真实数据匿名化，也不验证现实含义。候选仅表示软件规则匹配，没有预测
能力或准确率声明。使用中性名称可以减少应用领域的直接披露，但公开算法、
账号资料和发布活动仍可能透露关联信息。

## 直接运行

需要 Python 3.11 或更新版本。进入本项目目录后运行。演示、测试和发布工具
只使用 Python 标准库，不需要安装第三方依赖或联网。

```sh
python -B -m event_relations validate examples/synthetic_events.json
mkdir ../event-demo-output
python -B -m event_relations demo --output ../event-demo-output/demo.json
python -B -m event_relations analyze ../event-demo-output/demo.json --policy settings.demo.json --output ../event-demo-output/summary.json
python -B -m unittest discover -s tests -v
```

输出目录已存在时跳过 `mkdir`。再次运行请换新文件名；程序不会覆盖已有输出。
输出应放在发布源码目录之外。发布源码树内任何位置都禁止出现 `private_data`
或 `local_runs`，包括空目录及大小写变体。`-B` 用于避免产生 Python 字节码缓存。
部分系统需要把 `python` 改为 `python3`。

示例由 `event_relations/demo.py` 的固定模板和简单运算生成，不读取私人数据，
也不拟合真实数据分布。虚构场景覆盖方向改变、区间中断、重叠、发起者分类
和候选之后的区间事件。

`examples/expected_summary.json` 是合成示例的预期软件输出。
`settings.demo.json` 中的常数仅用于演示，不能作为现实应用的已验证阈值。
完整输入约定见[方法说明](docs/METHODS.md)。

## 环境与发布

运行时没有第三方依赖；`.python-version` 和 `pyproject.toml` 说明环境。
可以使用 `python -m venv .venv` 创建隔离环境。可选的
`python -m pip install .` 安装会提供 `event-relations` 命令，但可能需要下载
构建工具；上面的源码运行方式完全离线。

```sh
python -B tools/build_release.py --check
python -B tools/build_release.py --output ../event-relation-toolkit-public.zip
```

发布器发现禁止的本地数据名称时立即停止，包括被排除目录内的同名条目。
白名单外且不属于明确排除目录的文件也会阻止打包。它核对合成示例和预期结果，
为每个公开文件记录哈希，并统一压缩包内的文件时间和权限。

发布应从已审核 ZIP 开始，用 `tools/prepare_public_repo.py` 验证后解压到
整个私人工作区之外的新目录，再在那里建立全新的 Git 历史。只暂存清单列出的
文件和清单本身。完整命令及约束见[发布步骤](docs/PUBLISHING.md)；准备工具
本身不初始化 Git，也不上传文件。

公开提问和贡献均须遵守[贡献规则](CONTRIBUTING.md)：仅使用完全虚构的最小
示例，公开文字和附件中都禁止真实数据及其派生内容。

## 授权

尚未选择公开使用许可证，见 [LICENSE_NOTICE.md](LICENSE_NOTICE.md)。
