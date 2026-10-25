# 自动更新构建说明

推荐新建一个普通空 GitHub 仓库（例如 `PiliPlus-custom`），把 `.github/workflows/custom-release.yml`、`scripts/`、`patches/` 放到其**默认分支**，保留原目录结构；已有 Fork 也能使用。`patches/` 必须包含对应功能的 Git 邮件格式补丁及 `test/custom_patch` 回归测试。无需自己电脑安装鸿蒙开发环境；构建发生在 GitHub Actions。

## 第一次运行

1. 在自己的仓库中进入 **Actions**，允许工作流运行。若使用已有 Fork，将原仓库自带的 `release` 等构建工作流逐个 **Disable workflow**，仅启用 **Custom PiliPlus HAP**，避免自己手动打 tag 时产生多套构建；新建空仓库无需此步骤。
2. 确认上述文件位于仓库默认分支。工作流只允许从默认分支运行，不会响应普通提交或上游 tag 推送。
3. 打开 **Custom PiliPlus HAP → Run workflow**，保持 `upstream_tag` 留空。首次只构建最新正式版，不回补整个历史。
4. 成功后在自己仓库的 **Releases** 下载 `PiliPlus_custom_upstream_<数字>_unsigned.hap`，用原来的签名工具签名安装，沿用原有的应用标识及签名身份。Actions 的 Artifacts 中也有同一文件；Release 还附带 `build-provenance.json` 及应用源码压缩包。
5. 每 6 小时（UTC 分钟 23）检查一次新正式版。GitHub 的定时任务可能延迟；长期没有仓库活动时可能被停用，重新启用即可。检查动作并非即时推送订阅。

若希望先测试补丁制作时对应的版本，在 `upstream_tag` 填 `2.1.6.2-ohos`；之后会从它开始补齐未完成的新正式版。填 tag 也可重建已经完成的版本，发布时会替换同名工具生成资产。不会删除无关资产。

## 如何判断成功与失败

- 上游来源固定为 `dev4harmony/PiliPlus`，完整分页读取 Releases，只处理已发布、非预发布版本。
- 只有自己仓库**已发布**的 `custom-upstream-<上游 Release ID>` 且包含非空、上传完成的指定 unsigned HAP，才算成功。临时 artifact、草稿 Release、失败构建都不计成功。
- 首次成功版本之前的历史不自动构建；之后逐个补齐。某一版本失败不阻止其他版本尝试，下次仍会重试遗漏版本。
- 不要删除或手动改名这些 Release、tag、HAP 文件：它们同时是更新记录。上游删除或重建 Release、移动同名 tag，属于需人工核对的异常；已经完成的 Release 不会因为上游偷偷移动 tag 而自动重建。
- 每批最多 200 个版本，超出的下一次继续处理。单个工作流内串行构建，并发运行由同一个队列锁串行化。
- 发布先创建草稿，上传 HAP 和构建来源后才转为正式发布；中途失败保留草稿等待重试。手动重建已成功版本在最后发布阶段会暂时将该 Release 转成草稿，上传失败时也需重试。

## 构建方式与适配边界

每个版本先把上游 tag 解析到具体 Git commit，再拉取该提交的**完整历史**，防止 `build_env.dart` 的提交计数因浅克隆导致版本号错误。补丁通过 `git am --3way` 应用，冲突立即失败，不能悄悄跳过。

脚本读取该版本 `.github/workflows/release.yml` 的 Harmony SDK、Java、Flutter OHOS 分支参数，并交叉校验 `ohos/build-profile.json5` 的目标 SDK。工作流执行本工具明确写出的构建步骤，不直接运行上游 YAML。当前适配的是 `ErBWs/setup-ohos`、Java 17/21、`CPF-Flutter/flutter_flutter` GitCode 仓库及标准 unsigned HAP 输出路径。版本号变化会读取新值；仓库地址、命令格式、SDK 格式或输出约定变化会停止，提示修改适配脚本。上游的可选图片压缩步骤没有复制，因此包大小可能与作者原包不同。

构建前执行补丁回归测试 `flutter test test/custom_patch`。工具链本身的下载、上游依赖、CI 额度、网络以及未来上游代码改动均可能导致失败，首次必须到 Actions 验证真实运行。本机已经验证纯 Python 逻辑、Actions 语法、补丁应用，以及隔离环境中的真实 Flutter 组件测试；这不能替代完整 HAP 构建。具体范围见 VALIDATION.md。

`build-provenance.json` 记录上游 tag、commit、每个补丁 SHA-256、补丁集 SHA-256、工具包 commit、实际 Flutter commit、SDK 参数及 HAP SHA-256。附带的源码包是应用补丁后的 Git HEAD；生成环境元数据、版本计数及包名归一化由公开的工具包脚本完成，这些生成后变动不在 Git archive 中。Flutter 的上游分支及依赖可能变化，这些信息用于追溯，不能保证未来完全逐字节复现。

不需要保存 GitHub PAT：使用工作流自带的 `GITHUB_TOKEN`，只给构建 job `contents: write`。checkout 不保留凭据，token 仅在读取 Releases 和发布步骤传入。由该 token 产生的 tag/Release 不会触发普通的下游工作流运行。

## 补丁冲突时

查看失败版本和 `Apply local patch` 日志。在该上游版本源码上调整改动、执行回归测试，重新生成 `patches/*.patch` 并提交到默认分支，然后用 `upstream_tag` 手动重跑失败版本。没有必要每次同步 Fork 的整个应用分支；源码构建始终从上游对应版本重新取得，默认分支主要保存定制补丁和流水线。

不要为了让构建变绿而跳过补丁、测试或 `flutter build hap` 失败。若出现不兼容工具链提示，更新 `scripts/custom_release.py` 的适配逻辑之后再重试。

纯 Python 自测命令：

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
```
