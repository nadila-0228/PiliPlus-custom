# PiliPlus 自定义刷新设置

本仓库保存一个刷新设置补丁，以及跟随 `dev4harmony/PiliPlus` 鸿蒙正式版的自动构建配置。每次构建会下载上游对应版本源码、应用补丁、运行回归测试，再生成未签名 HAP。你的电脑不需要安装 Flutter 或鸿蒙开发环境。

补丁基于 `2.1.6.2-ohos`，上游提交为 `0aba2c6db94ba9b4cf9c076b1d39179ee3d860b4`。这是可部署的源码与配置包；完整 HAP 是否构建成功，需要以你仓库的首次 Actions 运行结果为准。验证范围见 [VALIDATION.md](VALIDATION.md)。

## 1. 新建自己的 GitHub 仓库

1. 登录 GitHub，打开 https://github.com/new 。
2. Repository name 填 `PiliPlus-custom`，推荐选 Public。也可使用私有仓库，其 Actions 用量按你的账号规则计算。
3. 勾选 **Add a README file**，创建仓库。默认分支通常为 `main`。

这里使用独立的补丁仓库，无需 Fork 或手动同步整个应用仓库。构建脚本会自动取上游源码。已有 Fork 也能放入这些文件，但需要禁用原有发布工作流，详见 [AUTOMATION.md](AUTOMATION.md)。

## 2. 上传解压后的文件

1. 解压本工具包，进入能直接看见 `.github`、`patches` 和 `scripts` 的目录。
2. 在自己的 GitHub 仓库点击 **Add file → Upload files**。
3. 把这个目录里的文件和文件夹拖入上传页面，提交到默认分支。

**上传解压后的内容，不要只上传 ZIP，也不要把所有内容再套进一层文件夹。** 正确目录应是：

```text
PiliPlus-custom/
├── .github/
│   └── workflows/
│       └── custom-release.yml
├── patches/
│   └── 0001-independent-refresh-settings.patch
├── scripts/
│   ├── custom_release.py
│   └── test_custom_release.py
├── README.md
├── AUTOMATION.md
├── MAINTENANCE.md
├── VALIDATION.md
└── LICENSE
```

上传后，在仓库文件列表中打开 `.github/workflows/custom-release.yml`，确认它确实位于这一位置。

## 3. 手动构建第一次

1. 打开自己仓库顶部的 **Actions**。如果页面要求启用 Actions，点击启用。
2. 左边选 **Custom PiliPlus HAP**。
3. 点击 **Run workflow**，分支选默认分支。
4. 第一次建议在 `upstream_tag` 填 `2.1.6.2-ohos`，这是补丁制作与本地验证使用的版本。也可留空构建运行时最新正式版。
5. 点击绿色 **Run workflow** 按钮，打开此次运行观察结果。

第一次需要下载鸿蒙工具链和依赖，等待所有构建步骤结束。绿色表示完成；红色时打开失败步骤查看具体原因，不能把“上传工具包成功”当成“安装包构建成功”。

无需填写 PAT、签名证书或 GitHub Secrets。工作流使用 GitHub 自动提供的令牌；签名在你自己的签名工具里完成。

## 4. 下载、签名、安装

1. 构建成功后打开自己仓库的 **Releases**，找到 `Custom 2.1.6.2-ohos` 或对应的新版本。
2. 展开 **Assets**，下载 `PiliPlus_custom_upstream_<数字>_unsigned.hap`。文件名中的数字是上游 Release ID，不是应用版本号。
3. 使用你原来的 HAP 签名工具，继续使用当前安装的签名身份和应用标识，再按原来的方式安装。
4. 首次覆盖前备份应用设置。如果签名工具报告不兼容，先核对签名配置，不要直接卸载丢失数据。工具包不会改变应用的 bundleName。

Release 还附带构建来源清单和修改后的源码压缩包；安装只需要 `.hap`。Actions 运行页面的 **Artifacts** 也有压缩后的产物。

## 5. 使用新设置

打开 **设置 → 其他设置 → 刷新指示器高度**，会出现两个独立的数字输入框：

| 设置 | 范围 | 效果 |
| --- | --- | --- |
| 指示器停留高度 | 0～1000，支持小数 | 刷新指示器相对可见顶边的停留位置 |
| 下拉触发距离 | 1～5000，支持小数 | 达到这个逻辑距离后松手触发刷新 |

例如可以输入“高度 20、触发距离 120”，只增加触发所需的距离。点“确定”同时保存两个值；“恢复默认”填入平台默认值，仍需点“确定”保存；“取消”不保存。

这里的高度不是圆圈直径，距离单位是逻辑像素，实际手指行程还受页面滚动阻尼影响。鸿蒙原生顶栏的既有避让仍保留。

旧版移动端默认高度为 20；旧界面显示滑动距离 103.5，但实际触发阈值约为 69。补丁默认迁移为 69，以保持旧手感，所以更新后显示数字变小不代表变得更容易触发。

## 6. 后续更新

- 默认每 6 小时检查一次上游正式 Release；不自动处理预发布版。
- 第一次成功后，只补齐该起点之后尚未成功构建的版本。失败版本会在后续再次尝试。
- 新版本成功后仍在**你自己的仓库 Releases** 下载 HAP，再用原签名工具安装。
- 应用内原有“检查更新”仍指向作者仓库，建议关闭“其他设置 → 检查更新”的启动检查，避免把原版包当成定制版下载。
- 需要立即检查时，到 Actions 再点 **Run workflow**，`upstream_tag` 留空。
- 需要重建某版时，在 `upstream_tag` 填它的精确 tag。此操作会替换该版本原有的定制产物。

GitHub 定时运行可能延迟。公开仓库长期无活动可能自动停用定时工作流；注意 Actions 的停用提示，必要时重新启用。不能保证作者发布后立刻出包，也不能保证未来每次上游重构都无需适配。

## 出错时看这里

| 失败位置 | 处理办法 |
| --- | --- |
| 找不到 Custom PiliPlus HAP | 检查目录结构、默认分支及 Actions 是否启用 |
| Apply local patch | 可能发生补丁冲突；按 MAINTENANCE.md 在新版本上适配后重跑 |
| Unsupported upstream recipe | 上游改了工具链配置格式；需要更新脚本的适配逻辑 |
| 下载工具链 / flutter pub get | 查看网络或依赖错误，临时错误可 Re-run failed jobs |
| Run patch regression tests | 需要修复代码或测试兼容性，不能跳过此步骤出包 |
| Build unsigned HAP | 查看构建日志中的首个实际错误 |
| Publish completed custom release | 检查仓库 Actions 权限或网络；前一步 Artifact 可能已有构建产物 |

本工具包不会自动创建你的仓库、提交文件或启动 GitHub 构建。完成上述上传和首次运行，才会开始在你的账号下工作。
