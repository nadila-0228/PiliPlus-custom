# 验证记录

日期：2026-10-25（Asia/Shanghai）。

基线：`dev4harmony/PiliPlus` 的 `2.1.6.2-ohos`，SHA `0aba2c6db94ba9b4cf9c076b1d39179ee3d860b4`。

## 已通过

- 从 GitHub 重新获取原始发布版后，`git am --3way` 完整应用补丁成功；得到的 Git tree 与已实现版本完全相同（`9bb39f38355e0d89a250d3aa1c16ad71f71f4235`），且包含全部 3 个回归测试文件。
- Dart 3.12.2 解析并格式化新增源码及测试；保持上游既有文件无关部分的格式不变。
- Flutter 3.44.9 / Dart 3.12.2 的隔离测试工程中，**24 项回归测试全部通过**：刷新组件 11 项、设置对话框 7 项、设置模型 6 项。
- 同一隔离工程 `flutter analyze --no-pub lib test` 返回 `No issues found`。
- 测试工程使用的 11 个实际源码与测试文件，和交付补丁中的对应文件逐字节校验一致。
- 自动构建脚本 **21 项 Python 测试通过**，覆盖分页、版本筛选、重试、工具链提取、上传失败及最后才发布成功标记等。
- 使用真实基线的 `release.yml` 与 `build-profile.json5`，成功提取 Harmony SDK `26.0.0.821`、Java `17`、Flutter OHOS `oh-3.44.9-dev`。
- `actionlint 1.7.12` 的工作流语法与 GitHub 表达式检查通过；未启用本机未安装的 ShellCheck/Pyflakes 附加检查。

## Flutter 隔离工程范围

使用真实的刷新组件、布局、滚动物理、手势、设置模型、设置对话框和测试源码；真实 Hive Box、os_type 包，以及上游的 material_ui shim 和 extended_nested_scroll_view/refresh.dart。

为了避免加载整套应用与鸿蒙插件，替代了 3 个应用入口：

- `platform_utils.dart`：固定为 Windows / 非 Darwin。
- `storage_pref.dart`：提供初始设置及无关物理参数；测试在挂载前设置刷新高度和距离。
- `storage.dart`：仅声明 `GStorage.setting`，数据仍使用真实临时 Hive Box。

因此，测试确认的是刷新组件和设置对话框的行为，包括精确阈值、取消、透明色、回弹通知、顶栏偏移与动态高度；不等同于整套鸿蒙应用已完成实机验证。

## 尚需首次 GitHub 构建与设备验证

- 完整上游依赖解析与主项目编译；设置页到实际持久化存储的整条接线。
- 鸿蒙原生顶栏、实际触摸阻尼、设备尺寸与系统版本差异。
- 完整 HAP 生成、用户签名、覆盖安装及重启后设置保留。
- GitHub Actions 在用户仓库中的真实端到端运行，以及未来上游版本的兼容性。

本工具包不包含预编译 HAP，也没有在用户账号上创建仓库、提交文件或启动工作流。第一次上传后，应手动运行工作流，确认绿色结果，再签名安装验证。
