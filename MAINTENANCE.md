# 补丁维护

平时只需要下载自动构建的 HAP。只有上游修改相邻代码、测试失败或更换构建方式时，才需要维护本工具包。

当前补丁顺序为 `0001-independent-refresh-settings.patch`（刷新高度与距离）→ `0002-quick-scroll-start.patch`（鸿蒙快速起步开关）。第二个补丁在第一个补丁之后制作，维护与重放时应保留这个顺序。

## 在新版本上修复冲突

以下是有 Git / Flutter 开发环境时的处理流程。示例中 `TARGET_TAG`、`YOUR_REPOSITORY_URL` 需要替换为真实值；不要把占位符照抄执行。建议在独立的临时目录操作，保留原补丁。

```powershell
git clone YOUR_REPOSITORY_URL kit
git clone https://github.com/dev4harmony/PiliPlus.git source
cd source
git switch --detach TARGET_TAG
git switch -c custom-refresh
git am --3way ../kit/patches/0001-independent-refresh-settings.patch
git am --3way ../kit/patches/0002-quick-scroll-start.patch
```

按顺序执行；某个 `git am` 有冲突时，先处理完当前补丁，再继续下一条。先用 `git status` 查看，根据上游新实现保留两个刷新设置独立保存、实际触发阈值、顶栏偏移，以及快速起步开关的行为，手动处理冲突标记，再执行：

```powershell
git add <已解决冲突的文件>
git am --continue
```

如果想放弃这一轮应用，执行 `git am --abort`。不要直接用旧文件整体覆盖新文件，也不要用 `git am --skip` 伪装成功。

使用对应版本的鸿蒙 Flutter 环境运行 `flutter test test/custom_patch` 与完整 HAP 构建。当前自动化还会进行包名小写归一化，手动复现时以 `scripts/custom_release.py` 的 `configure` 为准。生成未签名 HAP 的命令必须保留 `--no-codesign`：

```powershell
flutter build hap --release --no-codesign --dart-define-from-file=.vscode/env.json
```

修复完成后，保留两个按功能划分的提交；如果修复产生了额外提交，在本次独立修复分支上用交互式 rebase 把修复合并进对应功能提交，然后导出补丁。保留旧文件的备份，但不要把备份放进会自动应用全部 `*.patch` 的 `patches/` 目录。

```powershell
# 仅在本次独立修复分支上整理提交，保留刷新设置与快速起步两个提交。
git rebase -i TARGET_TAG
git log --oneline TARGET_TAG..HEAD
git format-patch --full-index --no-signature -o ../replacement-patch TARGET_TAG..HEAD
```

按提交顺序把生成文件分别改名为 `0001-independent-refresh-settings.patch` 和 `0002-quick-scroll-start.patch`，替换工具包里的同名补丁。先在另一个干净检出中重放两份补丁、运行全部回归测试，再上传到默认分支，手动填目标 `upstream_tag` 重建。同一上游版本已构建成功时，定时检查不会仅因为补丁更新就重建。测试目录被上游 `.gitignore` 中的 `test*` 忽略，新增测试时要明确 `git add -f test/custom_patch`。

## 核对行为

1. 固定触发距离，分别设置很低和很高的指示器高度，确认触发阈值不跟随高度变化。
2. 固定高度，改变触发距离，确认停留位置不变。
3. 低于阈值松手不刷新，达到阈值松手刷新，拉过阈值再拉回应取消。
4. 修改高度后立即返回已保活页面，确认位置生效；重启后两个数值仍保留。
5. 检查鸿蒙原生顶栏启用、收起、横屏情况下的位置。
6. 检查“恢复默认”和“取消”行为。
7. 鸿蒙端未保存开关时，“快速响应滑动起步”默认开启；关闭后下一次拖动恢复原版起步门槛，再开启下一次拖动恢复快速起步，重启后选择仍保留。
8. 检查列表、横向滑动和播放器的方向判断；确认原有 8/12 方向识别阈值未被修改。快速起步只改变 Bouncing 滚动物理的二级起步门槛（3.5 → 1），其他平台及原有刷新参数应保持原有行为。

部分 `NestedScrollView` 协调器不读取这个二级起步门槛。遇到某个页面手感没有变化时，先核对它的拖动控制器路径，不要为了覆盖该页面而顺带降低方向识别阈值或扩大补丁范围。

## 当前源码改动位置

- `lib/models/common/refresh_settings.dart`：数值范围、无效存储值兜底、旧触发阈值迁移。
- `lib/pages/setting/widgets/refresh_settings_dialog.dart`：双数值输入。
- `lib/pages/setting/models/extra_settings.dart`：设置入口、同时保存两个值、即时更新。
- `lib/utils/storage_key.dart`、`storage_pref.dart`：新增距离配置。
- `lib/common/widgets/flutter/refresh_indicator.dart`：独立距离、显式阈值判断。
- `lib/common/widgets/refresh_layout.dart`：高度变化后重新布局，保留 edgeOffset。
- `lib/common/widgets/scroll_physics.dart`：鸿蒙快速起步开关与 Bouncing 二级起步门槛；`applyTo` 需保留自定义类型，关闭时返回上游门槛。
- `lib/pages/setting/models/extra_settings.dart`、`lib/utils/storage_key.dart`、`storage_pref.dart`：快速起步开关入口、持久化及默认开启。
- `test/custom_patch/`：功能回归测试。

## 自动化配置变化

`scripts/custom_release.py` 的 `extract_toolchain` 读取每个目标版本的工具链参数。如果上游换仓库地址、SDK 配置格式、构建命令或 HAP 输出位置，应核对新版本工作流后修改对应适配逻辑，并补充 `scripts/test_custom_release.py` 的回归用例。

保留已经过真实构建验证的工作流：本工具的 HAP 构建使用 `--no-codesign`，而解析器检查的是上游原始构建命令，两者不必逐字相同。不要用缺少该参数的早期工具包或本地旧快照覆盖当前工作流；也不要用 `continue-on-error` 跳过构建失败。

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
```

发布记录是自己仓库的 `custom-upstream-<ID>` Release。保留它们及对应 HAP，自动化才能知道哪些版本已经成功。构建来源记录在每个 Release 的 `build-provenance.json` 中。
