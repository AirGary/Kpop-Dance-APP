# iOS 工程基线

## 三套环境

- Development：日常 Xcode 开发，Bundle ID 为 `fausyusgarygary.kpop.dev`。
- Staging：连接测试云端并用于个人 TestFlight，Bundle ID 为 `fausyusgarygary.kpop.staging`。
- Production：正式 App Store 环境，Bundle ID 为 `fausyusgarygary.kpop`。

三套环境必须使用不同的云端项目、数据库、Bucket 和密钥。Stage 0 只建立 Xcode 配置，不连接云端。

## 两类测试

- `kpopTests`：不操作真实界面，快速检查模型和业务代码。
- `kpopUITests`：启动模拟器中的 App，检查用户能否看到和操作页面。

UI 测试传入 `--ui-testing`，App 会使用内存数据库，因此每次测试都从空项目开始，也不会删除开发数据。

## 验证命令

在工程根目录运行：

```bash
./scripts/verify-ios.sh
```

只有当命令最终返回退出码 0，并且输出中出现测试成功与三个构建成功结果时，Stage 0 才算通过。

如果本机模拟器名称变化，可以覆盖目标：

```bash
IOS_DESTINATION='platform=iOS Simulator,name=iPhone 17 Pro' ./scripts/verify-ios.sh
```

## 阅读顺序

1. `kpop/kpopApp.swift`：查看 App 如何启动。
2. `kpop/App/AppLaunchOptions.swift`：查看测试如何改变启动方式。
3. `kpop/App/ModelContainerFactory.swift`：查看本地数据库如何创建。
4. `kpopTests`：查看模型必须保证的行为。
5. `kpopUITests`：查看用户启动 App 后必须看到什么。
6. `scripts/verify-ios.sh`：查看交付前会执行哪些验证。
