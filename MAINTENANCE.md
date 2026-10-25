# 补丁维护

平时只需要下载自动构建的 HAP。只有上游修改相邻代码、测试失败或更换构建方式时，才需要维护本工具包。

## 在新版本上修复冲突

以下是有 Git / Flutter 开发环境时的处理流程。示例中 `TARGET_TAG`、`YOUR_REPOSITORY_URL` 需要替换为真实值；不要把占位符照抄执行。建议在独立的临时目录操作，保留原补丁。

```powershell
git clone YOUR_REPOSITORY_URL kit
git clone https://github.com/dev4harmony/PiliPlus.git source
cd source
git switch --detach TARGET_TAG
git switch -c custom-refresh
git am --3way ../kit/patches/0001-independent-refresh-settings.patch
```

有冲突时先用 `git status` 查看。根据上游新实现保留两个设置独立保存、实际触发阈值和顶栏偏移，手动处理冲突标记，再执行：

```powershell
git add <已解决冲突的文件>
git am --continue
```

如果想放弃这一轮应用，执行 `git am --abort`。不要直接用旧文件整体覆盖新文件，也不要用 `git am --skip` 伪装成功。

使用对应版本的鸿蒙 Flutter 环境运行回归测试与构建。当前自动化还会进行包名小写归一化，手动复现时以 `scripts/custom_release.py` 的 `configure` 为准。

修复完成后，把本轮相对 `TARGET_TAG` 的全部功能变化压成一个提交，再导出一个替代补丁；保留旧文件的备份，仓库 `patches/` 中仅留需要应用的补丁，不要同时保留同一功能的多个替代版本。

```powershell
# 仅在本次独立修复分支上使用，保留所有文件改动。
git reset --soft TARGET_TAG
git commit -m "Allow independent refresh height and trigger distance"
git format-patch -1 --full-index --no-signature -o ../replacement-patch
```

把生成文件改名为 `0001-independent-refresh-settings.patch`，替换工具包里的同名补丁，上传到默认分支，然后手动填失败的 `upstream_tag` 重建。测试目录被上游 `.gitignore` 中的 `test*` 忽略，新增测试时要明确 `git add -f test/custom_patch`。

## 核对行为

1. 固定触发距离，分别设置很低和很高的指示器高度，确认触发阈值不跟随高度变化。
2. 固定高度，改变触发距离，确认停留位置不变。
3. 低于阈值松手不刷新，达到阈值松手刷新，拉过阈值再拉回应取消。
4. 修改高度后立即返回已保活页面，确认位置生效；重启后两个数值仍保留。
5. 检查鸿蒙原生顶栏启用、收起、横屏情况下的位置。
6. 检查“恢复默认”和“取消”行为。

## 当前源码改动位置

- `lib/models/common/refresh_settings.dart`：数值范围、无效存储值兜底、旧触发阈值迁移。
- `lib/pages/setting/widgets/refresh_settings_dialog.dart`：双数值输入。
- `lib/pages/setting/models/extra_settings.dart`：设置入口、同时保存两个值、即时更新。
- `lib/utils/storage_key.dart`、`storage_pref.dart`：新增距离配置。
- `lib/common/widgets/flutter/refresh_indicator.dart`：独立距离、显式阈值判断。
- `lib/common/widgets/refresh_layout.dart`：高度变化后重新布局，保留 edgeOffset。
- `test/custom_patch/`：功能回归测试。

## 自动化配置变化

`scripts/custom_release.py` 的 `extract_toolchain` 读取每个目标版本的工具链参数。如果上游换仓库地址、SDK 配置格式、构建命令或 HAP 输出位置，应核对新版本工作流后修改对应适配逻辑，并补充 `scripts/test_custom_release.py` 的回归用例。

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
```

发布记录是自己仓库的 `custom-upstream-<ID>` Release。保留它们及对应 HAP，自动化才能知道哪些版本已经成功。构建来源记录在每个 Release 的 `build-provenance.json` 中。
