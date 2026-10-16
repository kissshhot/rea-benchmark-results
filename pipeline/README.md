# 公开构建 pipeline

[工作流程与验收标准](../docs/pipeline.md) · [20 个种子目录](../seeds/README.md) · [主结果](../results/v5/README.md)

此目录包含可执行的构建、扰动、哈希核对、私有验收接入、冻结与白名单导出。它从 v5 脚本提取并改成可移植接口，业务实现和测试仍私有。**不能只 clone 本仓库就重新生成 20 个应用或复现模型分数。** 种子策划与业务实现仍需人工/模型参与；本入口不会调用模型、下载工具或发布文件。

## 直接可运行

Python 3.9+，仅标准库：

```sh
python3 pipeline/run.py catalog
python3 pipeline/run.py diversity
```

第二条应输出 20 个种子、五轨各四题、六个功能家族、80 个公开输入、940 个隐藏输入及 N/S/D 三类扰动。

## 构建自备源码包

源码包是本地受审查的输入；仅含所选应用的正常业务实现及许可证，不应含参考实现、隐藏测试、凭据或故障注入。以下是配置结构示例，路径由使用者填写：

```json
{
  "seed_id": "native_example",
  "track": "native",
  "source": "/path/to/local-source-bundle",
  "resources": ["LICENSE.txt"],
  "tools": {"clang": "clang", "strip": "strip"}
}
```

```sh
python3 pipeline/run.py build --config /path/to/build-config.json --out /path/to/new-build
python3 pipeline/run.py verify --build /path/to/new-build
```

输出目录必须不存在且与源码目录分离。一次构建生成 `clean/` 和 `mixed/`，另保存 `build.json` 及 `local-work/` 中的中间文件与日志。构建配置和日志可能包含本地路径，应留在私有工作目录。`resources` 是显式文本资源清单，默认只复制 `LICENSE.txt`；相应第三方许可全文和 notices 应由源码包提供。

| track | 源码包约定 | 工具配置键/环境 |
|---|---|---|
| native | `host.c`、`common.h`、`kernel.c`；可选 `catalog.tsv` | macOS arm64；`clang`、`strip` |
| dotnet | `Engine.cs`、`Rules.cs`、`policy.json` | .NET 8 SDK：`dotnet`；可在 `build_environment` 指定 `DOTNET_ROOT`、缓存/CLI 目录 |
| wasm | `kernel.ts`、`host.mjs`；配置增加 `kind` | Node、AssemblyScript、WABT：`node`、`asc`（编译器 JS 路径）、`wasm2wat`、`wat2wasm`、`wasm-validate` |
| plugin | `engine.js`、`entry.js`、`package.json`、`LICENSE`、`README.md` | `node`、`esbuild`、`vsce`（CLI JS 路径） |
| apk | 根目录下 Java 源码、`AndroidManifest.xml` | JDK、Android SDK 34：`javac`、`android_jar`、`d8`、`aapt`、`zipalign`、`apksigner`；`build_environment.JAVA_HOME` |

这些是 v5 的具体适配器约定，不是任意项目的通用编译器：

- native 约定 `common.h` 中有 `ENTRY run_job`、`jobfn` 类型和 `process(in,aux,out,o)`；宿主通过 `dlsym("run_job")` 加载入口。
- .NET 约定 `Core.Engine.Execute(JsonElement)` 和 `Policy.Rules`，策略资源名为 `policy.json`。生成 Gateway→Core→Policy 三程序集结构；mixed 增加反射路由。
- WASM 约定 `run`、`health` 导出，宿主按 `manifest.json` 的模块/入口/路由字段加载。源码中旧函数的移除仅适用于 v5 命名约定；扩展新任务需另审查其依赖。
- 插件约定 CommonJS `engine.js` 导出 `execute`，入口调用该引擎。逐模块压缩并打包为 VSIX；需在真实 VS Code 宿主另做执行验收。
- APK 约定 `Kernel.run(Context, JSONObject, Intent)`、`Dispatch`、`WorkerService`，mixed 以反射分派。包名从 manifest 读取，拒绝可调试应用。构建配置需增加 `signing: {"keystore": "/path/to/local-keystore", "password_env": "LOCAL_APK_KEY_PASSWORD"}`；密码只从本地环境读取，密钥和密码不放进仓库。

`tools` 中未设置的键按命令名查找；JS 编译器/打包器入口与 Android SDK 路径通常必须显式配置。没有自动下载安装或自动运行安装脚本。构建并不启动目标程序或私有测试。

## 私有验收器接口

本地验收器配置为 JSON 参数数组，不经过 shell；必须由维护者审核该命令：

```json
{
  "argv": ["python3", "/path/to/private-validator.py", "--build", "{build}", "--receipt", "{receipt}"],
  "timeout_seconds": 3600
}
```

```sh
python3 pipeline/run.py validate --build /path/to/new-build --validator-config /path/to/private-validator-config.json
python3 pipeline/run.py freeze --build /path/to/new-build
python3 pipeline/run.py export --build /path/to/new-build --condition mixed --out /path/to/new-handout
```

`validate` 只负责调用维护者提供的私有验收器并检查回执。示例中的验收器不在公共仓库；这是明确的外部接口，不是已公开的隐藏测试。验收器应在当前 build 上真实执行隐藏测试、独立参考、依赖干预和恢复等检查，并写入 `acceptance.json`：

- `seed_id`、`build_sha256`：与当前 `build.json` 一致。
- `checks`：`real_execution`、`independent_reference`、`clean_mixed_equivalence`、`reset_repeatability`、`dependency_intervention`、`dependency_restoration`、`decoy_noninterference`、`rea_solvability`、`no_leakage`、`provenance_checked`、`deduplicated` 均为 JSON `true`。
- `public_inputs >= 4`、`hidden_inputs >= 36`、`test_families >= 4`、`semantic_mutants >= 3`，`mutants_killed == semantic_mutants`。
- `evidence_sha256`：私有完整验收记录的 SHA-256。

缺失、失败或与当前构建不匹配的回执会阻止冻结。既有回执/冻结不覆盖。**回执是受信验收器的声明，不能防止维护者伪造结果，也不替代独立审计。** 公共代码没有隐藏测试逻辑，不会仅靠填入 `true` 就证明任务质量。

`export` 要求冻结仍有效，仅复制选定 clean/mixed 工件白名单；源文件、中间文件、日志和验收回执不会进入 handout。它拒绝源文件/调试文件扩展名、私有目录名、路径逃逸、符号链接和未经单独审查的嵌套包，并核对 ZIP/APK/VSIX 成员。此检查是防误混入措施，不是完整恶意内容扫描或操作系统沙箱。导出的发布物仍需配套经审查的任务简报/公开例子，且不会自动上传 GitHub。

## 与冻结结果的关系

`portable-v5-export-1` 是此次公开整理的构建器版本，不等同于冻结的私有 v5 原始脚本；规范化输入、路径、打包细节和工具版本可能改变工件字节。`results/v5/` 保留原冻结成绩。本次仅做公开代码的本地构建/接口验证，不重新调用 DeepSeek，也不替换旧结果。完整验收、模型执行和评分仍依赖私有组件。

[本次代码验证范围](VERIFICATION.md)。此目录代码使用 [MIT License](LICENSE)；该授权不覆盖未发布任务素材或第三方工具。
