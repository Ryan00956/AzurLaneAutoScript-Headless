# 运行时支持矩阵与探索状态

本文记录 AzurLaneAutoScript Headless 在不同宿主架构、Android 运行方式和
物理设备上的当前证据边界。状态快照日期为 **2026-08-13**。

这里的“通过”只对表格中写明的范围有效。Android 能启动、ANGLE NULL 合同
通过、游戏到达登录前，以及完整 ALAS 长期运行是四个不同结论。目前没有任一
平台通过完整、无人值守、长期 ALAS 工作负载资格测试。

## 状态定义

| 标记 | 含义 |
| --- | --- |
| 主线可执行 | qualify_runtime.py 的 execute 模式有主线后端实现，并具有真实环境生命周期证据。 |
| 真实探索 | 真实宿主或设备通过了写明的平台、合同或游戏边界，但主线后端尚未产品化。 |
| 部分通过 | 只通过前置门，或者在进入下一门前遇到明确阻塞。 |
| 未验证 | 有设计、构件或相邻平台经验，但该矩阵格本身没有真实资格证据。 |
| 不支持 | 当前权限或系统合同明确阻止目标路径。 |

所有运行时选择必须由 runtime lock 明确固定。运行开始后禁止在 KVM、Redroid、
TCG 或外部设备之间静默切换。ANGLE NULL 消除的是游戏对硬件 GPU 的依赖，
并不消除 Android 图形栈、虚拟化、Binder、guest ABI 或持久化存储要求。

## 服务器矩阵

| Android 运行方式 | x86_64 Linux 服务器 | ARM64 Linux 服务器 |
| --- | --- | --- |
| KVM / Android Emulator | **主线可执行；当前最成熟。** API 32 x86_64、KVM 探测、ANGLE NULL、Unity、observer、游戏登录前、game/Android recovery 均有证据。仍缺当前 ALAS 全任务、长期 soak 与多实例资格。 | **未验证。** 已有 ARM64 ANGLE、Unity 和 runtime-lock 构件，但没有真实 ARM KVM 宿主、guest 生命周期、游戏或恢复证据。 |
| Redroid | **真实探索。** 原生 x86 云宿主在无 /dev/kvm 条件下完成 Binder/容器路径、完整游戏资源、重启持久化并到达登录界面；未输入账号。主线 redroid 后端仍为 fail-closed plan-only，当前镜像线也缺 x86 OCI 真实回退。 | **平台与更新探索较完整。** 真实 ARM 宿主上的 digest-pinned Redroid 通过 G1/G2/G3、APK/资源更新、三轮 restart、持久化 /data 和真实 OCI 回退。尚无真实游戏或 ALAS 证据；原生 FBE 仍阻塞，主线后端仍为 plan-only。 |
| QEMU TCG | **部分通过，仅作为 fallback。** Q1/Q2/Q3、Unity 长运行和 observer freshness 通过，游戏到达隐私协议边界；WebView 黑屏/System UI ANR 阻止更深 Q4。单线程 portable PGO 候选保留，MTTCG 已因超时或退化被否决。 | **服务器格未验证。** 没有真实 ARM 服务器资格结果。相邻证据来自非 root ARM64 平板托管同架构 QEMU/Cuttlefish：Unity 通过且游戏到达无输入登录前，但极慢，不能替代服务器证据。ARM64 API 32 的另一实验还受 keystore2 崩溃阻塞。 |

### x86_64 KVM

这是第一条正式支持候选，也是目前唯一同时具备主线可执行后端和真实
Android、游戏、observer、recovery 证据的服务器路径。

当前已验证范围包括：

- Linux /dev/kvm 权限与 KVM API version 12；
- 固定 AVD、ADB serial 所有权和进程 cleanup；
- API 32 x86_64 guest 的 ANGLE NULL、Unity 和 typed observer；
- 固定游戏在无账号输入条件下到达登录前；
- 游戏恢复要求新 PID、同一完整指纹和新鲜 observer；
- Android 恢复要求观察到 ADB offline，再重新通过 framework、游戏和 observer 门；
- 镜像实验线上的 21/21 平台能力、更新/回滚实验和约 23 秒冷启动中位数。

尚未验证当前 ALAS top-down 分支的完整任务、24 小时以上 soak、容量和多实例密度。

### x86_64 Redroid

历史真实探索已经证明普通 Linux 云主机在没有嵌套虚拟化时可以使用 Redroid：
Binder/BinderFS、MemFD、privileged 容器、ANGLE NULL、observer、约 27.8 GB
资源下载、容器重启后的 /data 持久化和游戏登录界面均有证据。ADB 只允许绑定
loopback，测试没有输入账号。

这条路径当前缺的是产品化后端和当前制品闭环，而不是最初可行性证明：

- RedroidBackend 尚未实现，主线仍明确拒绝执行；
- 缺少当前 OCI digest、runtime lock、恢复和 cleanup 的统一 manifest；
- x86_64 原生宿主上的真实 OCI 回退尚未完成；
- 尚未绑定当前 ALAS 工作负载。

### ARM64 Redroid

分支 codex/android-image-foundation 已在真实 ARM64 服务器上获得：

- digest-pinned Android 12/API 31 与 Android 14/API 34 Redroid 基线；
- ARM64 G1 GLES NULL、G2 Unity、G3 observer；
- 单 APK、ARM64 split APK、资源中断续传、restart 和指针回滚；
- 三轮 Redroid restart 约为 18 秒，OCI digest 不变且 /data sentinel 保留；
- Android 12 到候选镜像再恢复 Android 12 的真实 OCI 回退；
- ADB loopback、独立 /data 挂载和 registry/index digest 身份；
- 双 ABI 确定性 OCI 打包器、源码锁、SBOM/NOTICE 和 provenance 门的代码实现。

当前不能 promotion 的原因：

- stock Redroid 14 的受保护能力为 20/21，原生 FBE 未通过；
- 当前 /data 是宿主 ext4 bind mount，不能冒充 Android FBE 或 Direct Boot；
- stock 基线安全补丁不足以作为长期发布基线；
- 自维护 AOSP/Redroid 双构建尚未在满足 400 GiB 空间和 64 GiB RAM 的构建机完成；
- 没有真实游戏、资源全集或 ALAS 工作负载证据；
- 主线 Redroid 后端仍为 plan-only。

### QEMU TCG

TCG 定位为无法使用 KVM 且没有可用 Binder 容器环境时的兼容或 CI fallback，
不作为首选生产运行时。

x86_64 的同架构 TCG 已通过平台合同，但游戏 Q4 被协议 WebView 与 System UI
稳定性阻塞。冷启动明显慢于 KVM。MTTCG 虽能看到多 vCPU 线程，但 2 vCPU 和
4 vCPU 对照均退化或超时，因此不得把并行线程等同于性能提升。

ARM64 平板上的同架构 QEMU/Cuttlefish 实验说明该方向功能上可行，但首次
framework 启动和大 APK 安装以十几至二十分钟计，且没有 observer、ALAS 或恢复
闭环。该结果不能写入 ARM 服务器格，也不能作为手机产品路径。

## 物理设备附加矩阵

| 设备类型 | 当前状态 | 已验证 | 未验证或阻塞 |
| --- | --- | --- | --- |
| 已 root ARM64 手机 | **真实探索：部署工具可用。** | 已 root、Android API 29+、Magisk-compatible 模块目录；systemless ANGLE provider 的 install/verify/remove/reboot/rollback；G1 NULL renderer、surface、零 readback 和 GLES error 门。 | 不负责解锁或获取 root；未验证当前游戏 G4、完整 observer、ALAS、长期运行、温控与性能；未覆盖任意 KernelSU 布局。 |
| 无 root、locked ARM64 手机/平板：直接运行 | **当前不支持 release 游戏路由。** | debug/queryable GLES probe 可加载调试 ANGLE。 | locked user build 上的 release 游戏不能直接加载 side-loaded debug ANGLE；除非 OEM/userdebug 提供系统级路由能力，否则不能产品化。 |
| 无 root、locked ARM64 手机/平板：作为 QEMU 宿主 | **实验性部分通过。** | 普通应用权限下托管 ARM64 QEMU/Cuttlefish、ANGLE NULL、ARM64 Unity，并让游戏到达无输入登录前。 | 无硬件加速、速度很慢；没有游戏 G4、observer、资源更新、ALAS、恢复或长期资格。 |

主线 external-adb 后端只负责附着到一个明确指定的设备并执行身份/生命周期合同，
不会声称拥有设备 provisioning、root、bootloader、持久化或系统升级。

## 镜像制造能力与运行支持的区别

Android 镜像线已经实现或验证双 ABI ANGLE/Unity 制品、更新实验、内容哈希、
source lock、确定性 OCI、SBOM/NOTICE、userdata、restart 和 rollback 门。它仍然
不能单独把一个矩阵格提升为“ALAS 支持”。提升至少需要：

1. 对应架构和运行方式的真实宿主；
2. 内容 digest 固定的 Android、ANGLE、游戏和资源身份；
3. 可执行 backend 的完整 probe、resolve、provision、start、ready、recover、stop；
4. G1/G2/G3，以及按目标声明的真实游戏边界；
5. cleanup、restart、rollback 和 userdata 隔离证据；
6. 当前 ALAS 工作负载、长时间 soak 和容量证据。

游戏 APK、游戏资源、账号 userdata 和含账号信息的原始证据不得进入公开镜像或 Git。

## 当前代码和开发分支

快照时的代码状态：

| 分支 | 快照提交 | 状态与范围 |
| --- | --- | --- |
| main | a580b2d | 可执行后端只有 kvm 和 external-adb。redroid、tcg、arm64-qemu 为 fail-closed plan-only。 |
| codex/android-image-foundation | 0421d69 | 27 个主线外提交，工作树干净；当前全量测试 506/506。包含双 ABI 镜像、Redroid OCI、userdata/FBE、更新、重启、回退和 reproducibility 门。尚未合并主线。 |
| codex/alas-topdown | 52968f9 | 43 个主线外提交并继续开发 G36/主线战斗适配；快照时仍有未提交修改。尚未合并主线。 |

旧的 platform-qualification、redroid-qualification、tcg-optimization、
arm64-qemu-qualification 和 arm64-venus-qualification 分支是证据与实现参考，
不是可以直接恢复为新开发基线的当前主线。

## 推荐推进顺序

1. 将当前 ALAS top-down 工作负载绑定到 x86_64 KVM，形成第一条端到端支持线。
2. 实现独立 RedroidBackend，先接入已有 ARM64 平台/更新证据，再复验真实游戏。
3. 在原生 x86_64 Binder 宿主补齐当前 Redroid OCI、restart 和 rollback。
4. 将已 root 手机部署工具与 external-adb runtime lock 接通，并重新执行当前游戏 G4。
5. 获得真实 ARM64 KVM 服务器后，从 host Q0 开始建立独立 ARM KVM 证据。
6. TCG 保持 fallback；在有可重复 ALAS trace 前不继续 MTTCG、密度或主机特化调优。
7. 无 root 设备直接路由 release 游戏不作为当前主产品方向。

## 状态更新规则

更新本矩阵时必须同时写明宿主架构、backend、Android API/ABI、镜像或 OCI digest、
ANGLE revision/APK hash、游戏版本和 ABI、observer schema、runtime-lock hash、输入
边界以及最高通过门。不同 backend、ABI、镜像、游戏或未提交工作树的证据不得互相
覆盖，也不得以代码存在、容器存活或 sys.boot_completed=1 单独宣称支持。
