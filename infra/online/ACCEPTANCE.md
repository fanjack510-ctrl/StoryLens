# Protocol 2：首次安装与香港隔离 A–H 验收

关联 CHG-20260903-001；VERSION 保持 1.3.6。以下是操作者待执行命令，
不是已经通过的服务器证据。所有 Docker 命令只在人工批准的香港验收窗口执行。
工具不会打开正式模型开关，不会推送、发布或创建标签。

## 本次阻断及重验规则

### R6 入口：仅测试夹具纠正，条件式 H-only

R5 `18f8ee3ea28ce5717481972c29ea04e8e0613702` 包已 superseded，不再安装。
用户提供的香港 A/B/C、D–G 实际更新/回滚、H1/H2 均 PASSED；不是 D–G 失败。
H3 在 root umask077 下为13 failed/209 passed/9 skipped；umask022对照为222 passed/9 skipped。
原因是 pytest 的公开源码夹具未显式设置权限，导致本应测试镜像错误的用例提前触发
BUILD_CONTEXT_CONTRACT_FAILED。生产 context_contract 的0755/可读检查正确，R6不放宽它。
Linux权限定向1 passed/20 deselected且未跳过，数据库/stdin18 passed（用户现场证据）。
R5四个项目已停止但完整保留，bin已unlink；生产4ae7f663/HTTP200，模型开关关闭、白名单为空。
R1–R5历史与资源全部保留。CHG仍tested，不能用本地测试代替香港最终H验收。

优先执行 [R6 H-only纠正验收](R6-H-ONLY.md)。该说明含机器等价/留存证据/生产身份门禁，
任一门禁失败不得关联R5 D–G，改用本文件完整A–H并使用全新后缀r6（不得复用下面历史r5项目）。
以下R5 D–G命令保留为历史说明；完整R6重验必须将五处项目后缀明确替换为r6。

`a0f8c1a941365a46c9cf93ab5cfb792e595dacee` bootstrap 已 superseded，禁止继续安装。
用户提供的香港首轮 D 项目 `sl-accept-webd20260904`：prepare 返回
`COMMAND_FAILED_SAFELY`，PG/Redis/PB 正常，schema-init Exited(1)，报
`No module named storylens_online.db.init_schema`。源码 init_schema.py 摘要为
`4bffce5788725ed613c87a0483d40242f26b1b0db165efaa9eebae53cab8771f`；
旧镜像 `sl-accept-webd20260904-app:baseline` ID 为
`sha256:fe599454d7bad5266286e77bdbd7c7bcdd2d05558c99ee0d30d4b20879d1e818`。
生产仍指向 `/opt/storylens/releases/4ae7f663` 且 HTTP 200。

代码根因是 root CLI 的 umask 077 与源码复制 mkdir 未显式 chmod 的组合：嵌套目录
成为 0700，COPY 保留目录权限，而镜像最终用户为 10001。非 root 的 Python 会看见 db
目录却无法读取其 initializer/子模块，呈 namespace/模块不存在；不能据此断言镜像层
物理丢失字节。本地清单包含全部 db 文件且上述摘要一致，没有 dockerignore 文件。
Docker 对 COPY 目录保留权限的规则见
[Dockerfile reference](https://docs.docker.com/reference/dockerfile/#copy)。
旧工具没有检查目录模式、镜像内导入和字节摘要，COPY history 也不能证明用户可读。

旧 session.json、compose.json、镜像、容器、卷均只保留审计，**不能复用旧项目**。
旧失败发生在 ready=false 时；它留下部分初始化资源是失败关闭设计，不是成功基线。
本轮不自动 down、不删卷、不清理旧证据。以下所有 D–G 使用第五组 r5 项目；若新项目已存在，
停止并另选合法唯一后缀，不能删旧资源后冒充首次验收。

修复后目录权限只在复制的公开构建源码内部显式设为 0755；state/evidence/Secret
父目录仍 root-only。完整清单与文件树匹配，空目录/缺 initializer/漏文件/任何 dockerignore
均拒绝。App 使用 --no-cache，并拒绝已存在构建标签，构建后按不可变 image ID 检查与运行。
Web D/E 也先检查基线 App；App 候选在任何切换前检查。探针无网络/Secret/业务卷，
以 10001:10001 运行，导入 main、worker、db.init_schema、db.models、db.phase2b1_migration，
并比较整个 API 包及 Worker entrypoint 的 SHA256，entrypoint 必须可执行。
探针的 --rm 仅移除该一次性无数据容器；不是清理失败验收 session。

prepare 的 `IMAGE_RUNTIME_CONTRACT_OK` 必须出现在启动任何隔离服务之前；随后才可出现
`ACCEPTANCE_BASELINE_READY`。失败标志为 `BUILD_CONTEXT_CONTRACT_FAILED` 或
`IMAGE_RUNTIME_CONTRACT_FAILED`，不得出现 READY，也不执行 compose up。
App update 的镜像检查结果写入 evidence/image-contract-*.json，控制台仍只输出更新或回滚结果。
检查失败保留 root-only 固定错误证据和未就绪 session；不打印 import 错误正文或环境变量。
本地没有 Docker Linux Engine，以下是真实香港待验收步骤，不能以 Fake 测试代替。

### 第二轮 B 安装失败（保留现场，deb0a0d6 也已 superseded）

用户报告 deb0a0d650ce5c40e2eac025646ce36edebb1a26 安装/稳定入口 version 成功，
工具指纹 978fa8b96acbd83ef2ed2ccdd3837a51f798a18321d664c5476a8c2854d877c7，
随后 list 返回 TOOL_INSTALL_FAILED_SAFELY/exit1。仓库有两个合法版本目录及
root:root 0600 普通旧锁 sl-accept-webd20260904.lock；生产 current=4ae7f663、HTTP200。

代码审计纠正归因：旧 list 用 is_dir() 过滤普通文件，故不能证明这个普通锁直接导致报错。
可确定复现的缺陷是新版 installed() 用当前11文件布局验证旧版9文件目录，缺少新增镜像
探针模块即报错；旧 list 又静默忽略未知普通文件，install/list 校验范围不同且无切换自检。
本轮同时修复版本布局兼容、严格 registry 分类和锁目录混用，不伪造远端异常栈。
两个失败包 a0f8c1a9、deb0a0d6 禁止继续安装，旧版本和旧锁只保留审计/已验证入口恢复。

新版 registry 仅接受40位小写hex真实版本目录，分别按已知9或11文件布局和原指纹核验，
不执行旧工具Python代码。legacy lock 必须严格匹配 sl-accept-[a-z0-9]{8,24}.lock，
lstat证明普通文件/root:root/0600/nlink=1；不跟随链接、不打开内容、不修改旧锁。
其他文件、未知目录、symlink/FIFO/device、错误权限或owner均失败关闭。
install/list/activate/unlink共用registry，切换前后自检；后检失败原子恢复先前入口，
之前无入口则撤销本次入口。恢复系统调用也失败时明确要求人工恢复，不谎报恢复成功。

新验收锁为 /run/lock/storylens-online-deploy/<project>.lock，目录root:root0700、文件0600，
安装器操作使用同目录registry.lock串行化。生产旧部署互斥锁仍留在shared，不改变生产边界。
DryRun不创建锁；新锁不写lib，不截断既有锁文件。/run锁随系统生命周期存在，旧lib锁永久保留审计。

### 第三轮 R3 D：root-only tmpfs 的不存在检查失败

用户提供现场：f0fab627b8d4eab9950b03c4d9565b6979719763，项目
sl-accept-webd20260904r3 已通过 IMAGE_RUNTIME_CONTRACT_OK；schema-init、pocketbase-init
均 Exited(0)，API/Web/PocketBase/PG/Redis健康、Worker正常。人工audit_containers/network
复验通过，均为internal网络、无宿主端口；Worker PID1=10001:10001。
Web无staged Secret，但tmpfs父目录root:root0700使UID10001调用Path.exists抛PermissionError；
prepare输出COMMAND_FAILED_SAFELY、session.ready=false。生产current=4ae7f663、HTTP200。
这是验收探针的权限错误，不是Worker启动或Secret暂存故障。f0fab627包已superseded，禁止继续安装。
前三轮失败session、容器、镜像、卷、锁全部保留；不能删资源复用项目。

新版Web非root探针只验证自身及PID1的UID/GID；root探针先验证tmpfs目录root:root0700，
再用lstat确认staged路径完全不存在，文件/悬空symlink/目录/FIFO等任何条目都拒绝。
同时Worker不得有任何bind mount，因此无原始Provider Secret挂载；不读取Secret内容。
App保持原入口暂存行为：目录10001:10001/0700，原件root600，副本10001:10001/0400；
非root实际open副本成功、open原件必须PermissionError，root用NOFOLLOW和fstat验证普通文件、
权限与owner后做有界字节一致性比较，无内容或摘要输出。tmpfs始终64KiB/noexec/nosuid/nodev。
Web关闭模式不chown、不chmod目录；安装器和业务Worker入口也不改。

实际边界检查写入evidence/secret-boundary-*.json，状态SECRET_BOUNDARY_OK；任一失败写
SECRET_BOUNDARY_FAILED并失败关闭，prepare不得标记ready。证据存储自身失败时固定报
SECRET_BOUNDARY_EVIDENCE_FAILED。不记录异常正文、环境或Secret。DryRun保持只读，不落盘，
失败只返回同一固定错误；实际prepare/update/rollback的证据不得只有IMAGE_RUNTIME_CONTRACT_OK。

### 第四轮 R4 D：指纹表名错误与流式 shell stdin

用户提供：45af8559d128eb277e848353feab4eeb4b61caf6，sl-accept-webd20260904r4，
IMAGE_RUNTIME_CONTRACT_OK、ACCEPTANCE_BASELINE_READY及SECRET_BOUNDARY_OK已通过；
Update DryRun返回COMMAND_FAILED_SAFELY。源码SQL误用了online_uploads，实际表为
online_book_uploads。原Fake仅返回固定计数而未执行SQL，未捕获这个表名错误。
全仓核查其余原有online_uploads均是正确Docker卷名/卷说明，不得改生产Compose或抹改历史。
R4容器已由现场操作者停止但全部保留，稳定入口已unlink；生产仍4ae7f663、HTTP200。
45af8559包已superseded，R1–R4的任何资源均不删除、不复用。

另一个现场复现缺陷是Docker/Compose子进程继承SSH脚本stdin，吞掉后续bash -s命令。
工具统一命令执行器及Git打包入口现均显式stdin=DEVNULL，数据库检查和构建也经过该入口。
无需操作者拆分脚本或为工具调用逐条追加重定向；stdout/stderr仍捕获、超时与固定错误保持。
本地真实流式bash测试有旧行为对照：旧子进程读走尾部命令，新子进程只读到EOF且尾部标记执行。
本地数据库测试使用模型声明表名建立内存夹具并执行真实计数SQL，验证Web/App DryRun和
schema/各业务表行数漂移拒绝；这不是香港真实PostgreSQL或Docker验收。

R5必须从A开始：重新安装稳定bin，创建全新基线镜像和session，不能借用R4的ready记录。
完整操作命令如下，仍只由香港操作者人工执行。

## A. 安装前检查与生产身份留存

先人工安全查看生产开关：Phase2B1=false、白名单为空，只记录判断，不打印 env。
在服务器 root shell 执行，关闭 shell trace（不得使用 set -x）：

```bash
set -eu
umask 077
test "$(id -u)" = 0
test "$(readlink -f /opt/storylens/current)" = /opt/storylens/releases/4ae7f663
test "$(curl --silent --show-error --max-time 20 -o /dev/null -w '%{http_code}' https://app.dstorylens.com/)" = 200
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
AUDIT=/opt/storylens/acceptance-evidence-$STAMP
test ! -e "$AUDIT"
install -d -m 0700 "$AUDIT"
docker --host unix:///var/run/docker.sock ps -a --filter label=com.docker.compose.project=storylens-online --format '{{.ID}} {{.Names}} {{.Status}}' > "$AUDIT/production-before.txt"
for id in $(docker --host unix:///var/run/docker.sock ps -aq --filter label=com.docker.compose.project=storylens-online); do
  docker --host unix:///var/run/docker.sock inspect --format '{{.Id}} {{.Image}} {{.RestartCount}}' "$id"
done > "$AUDIT/images-before.txt"
docker --host unix:///var/run/docker.sock volume ls --filter label=com.docker.compose.project=storylens-online --format '{{.Name}}' > "$AUDIT/volumes-before.txt"
printf '%s\n' A_PREFLIGHT_OK
```

人工确认 API/Web/PocketBase/PostgreSQL/Redis healthy、Worker running、
pocketbase-init Exited(0)，否则停止。工具也会在实际验收操作前后比较正式容器镜像/重启数、
卷身份和 current/current-web/current-app/override 的身份；不读取正式数据库或 Secret。

## B. 校验包、完整安装到版本化 lib、切换稳定 bin

先把最终报告中的服务器包绝对路径、SHA256、字节数设置为 PACK、EXPECTED_SHA、EXPECTED_SIZE
三个变量（不是Key）。通过ssh bash -s传输时将它们设置在脚本开头；不使用read消费脚本stdin。

```bash
: "${PACK:?请先设置已上传包的绝对路径}"
: "${EXPECTED_SHA:?请先设置可信报告中的SHA256}"
: "${EXPECTED_SIZE:?请先设置可信报告中的字节数}"
test -f "$PACK" && test ! -L "$PACK"
test "$(stat -c %s "$PACK")" = "$EXPECTED_SIZE"
test "$(sha256sum "$PACK" | cut -d ' ' -f1)" = "$EXPECTED_SHA"
SOURCE=/opt/storylens/bootstrap-$STAMP
test ! -e "$SOURCE"
install -d -m 0755 "$SOURCE"
# 先只列出条目供审计；包必须与上面可信摘要一致，无绝对路径、..、链接或特殊文件。
tar -tvzf "$PACK" > "$AUDIT/archive-list.txt"
tar --no-same-owner --no-same-permissions -xzf "$PACK" -C "$SOURCE"
COMMIT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit"])' "$SOURCE/bootstrap.json")
TV=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tool_version"])' "$SOURCE/bootstrap.json")
sh -n "$SOURCE/infra/online/deploy-lightweight.sh"
BIN=/opt/storylens/bin/storylens-online-deploy-lightweight
LEGACY_LOCK=/opt/storylens/lib/storylens-online-deploy/sl-accept-webd20260904.lock
python3 - "$LEGACY_LOCK" > "$AUDIT/legacy-lock-before.json" <<'PY'
import json, os, stat, sys
s=os.lstat(sys.argv[1])
assert stat.S_ISREG(s.st_mode) and stat.S_IMODE(s.st_mode)==0o600
assert s.st_uid==s.st_gid==0 and s.st_nlink==1
print(json.dumps([s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns]))
PY
PREVIOUS_ENTRY=$(readlink "$BIN" || true)
set +e
python3 -I -B "$SOURCE/infra/online/deploy_install.py" install --source "$SOURCE"
INSTALL_RC=$?
set -e
if [ "$INSTALL_RC" -ne 0 ]; then
  test "$(readlink "$BIN" || true)" = "$PREVIOUS_ENTRY"
  printf '%s\n' B_INSTALL_FAILED_ENTRY_RESTORED
  exit 1
fi
LIB=/opt/storylens/lib/storylens-online-deploy/$COMMIT
test "$(readlink -f "$BIN")" = "$LIB/deploy-lightweight.sh"
stat -c '%U:%G %a %n' "$LIB" "$LIB/deploy-lightweight.sh" "$LIB/deploy_cli.py"
test "$(stat -c '%u:%g:%a' "$LIB")" = 0:0:700
test "$(stat -c '%u:%g:%a' "$LIB/deploy-lightweight.sh")" = 0:0:555
test "$(stat -c '%u:%g:%a' "$LIB/deploy_cli.py")" = 0:0:444
"$BIN" version > "$AUDIT/tool-version.json"
python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); assert m["protocol"]==2 and m["tool_version"]==sys.argv[2] and m["commit"]==sys.argv[3]' "$AUDIT/tool-version.json" "$TV" "$COMMIT"
python3 -I -B "$LIB/deploy_install.py" list > "$AUDIT/registry-after.json"
python3 - "$LEGACY_LOCK" "$AUDIT/legacy-lock-before.json" "$AUDIT/registry-after.json" <<'PY'
import json, os, sys
s=os.lstat(sys.argv[1])
assert [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns]==json.load(open(sys.argv[2]))
r=json.load(open(sys.argv[3]))
assert 'sl-accept-webd20260904.lock' in r['legacy_locks'] and len(r['versions'])>=2
print('REGISTRY_LIST_OK_LEGACY_LOCK_UNCHANGED')
PY
test "$(stat -c '%u:%g:%a' /run/lock/storylens-online-deploy)" = 0:0:700
printf '%s\n' B_INSTALLED_NO_CONTAINERS_CHANGED
```

安装器验证包内全部源码摘要和工具指纹；所有文件来自最终 Git archive，bootstrap.json
是生成的非秘密元数据。外部 SHA 校验是信任起点，包内摘要不能代替它。
版本实现目录 root:root **0700**，不是0755（mkdir的0755请求受安装器umask077约束）；
shell=0555，Python 和 installed.json=0444。不要为迎合旧说明放宽目录权限。
包中保留的是公开占位 `.env.example`（仅供离线 Compose 测试）；没有真实 `.env`、online.env
或 Secret 文件。隔离运行不加载这个例子，不使用其中的生产 Secret 路径。
bin 是 root 创建、位于 root 专属目录的绝对软链接，shell 使用 readlink -f 定位版本化依赖。
安装不会执行 Docker。原有已识别版本会生成 0400 previous-tool-*.json；未知入口或版本拒绝覆盖。
若遗留普通文件入口，先停止人工审查和只读备份，不得 rm/覆盖后强行安装。
安装后重复 A 的身份采集并 diff，正式容器及 current 必须完全未变。

## C. Windows 离线 DryRun 与拒绝用例

在包含最终提交的本地干净 Git 仓库执行：

```powershell
.\.venv\Scripts\python.exe -m pytest infra/online/tests/test_deploy_lightweight.py -q -k "powershell_offline_preflight or classifier or protocol" -p no:cacheprovider
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy_online.ps1 -Mode web -Server operator@example.invalid -IdentityFile C:\unused-no-key -BaselineCommit d6416111a6fc5cc8de0c036caa4f0989cfb74f2c -DryRun
```

第一条在独立临时 Git 夹具中测试纯 Web 成功、dirty/mode/full/docs 拒绝；分类器覆盖
DB、Compose、Secret、认证、计费和未知路径。第二条对本轮真实工具修改应输出
FULL_DEPLOYMENT_REQUIRED（exit 1），不能误判为 Web。不得为了得到成功篡改真实基线。
DryRun 检查本地工具协议/指纹、参数、版本及分类；不连接服务器、不读取私钥、不打包上传。
离线模式不能证明远端版本；实际执行及以下服务端 DryRun 都会比较已安装工具指纹。

## D–G 共用命令函数

继续同一个 root shell，使用 B 中的 BIN、TV、SOURCE。需要 Python 3.10+、本机 Docker
Engine/Compose v2 及构建镜像所需外网；运行容器只有 internal 网络，没有公网出口。
四个 session 独立，不发布宿主端口，不复用正式或其他 session 卷。
prepare 只在全新 project 下初始化隔离空数据库；update/rollback 不运行 schema-init。

```bash
setup_session() {
  P=$1; MODE=$2
  S=/opt/storylens/acceptance/$P/state
  E=/opt/storylens/acceptance/$P/evidence
  C=/opt/storylens/acceptance/$P/candidates/$MODE
  if [ "$MODE" = app ]; then
    "$BIN" acceptance-key --protocol 2 --tool-version "$TV" --project "$P" --state-dir "$S" --evidence-dir "$E" --target app --probe container-http
    KEY=/opt/storylens/acceptance-input/$P/deepseek-test-key
    "$BIN" acceptance-prepare --protocol 2 --tool-version "$TV" --project "$P" --state-dir "$S" --evidence-dir "$E" --target "$MODE" --probe container-http --source "$SOURCE" --test-secret "$KEY" --dry-run
    "$BIN" acceptance-prepare --protocol 2 --tool-version "$TV" --project "$P" --state-dir "$S" --evidence-dir "$E" --target "$MODE" --probe container-http --source "$SOURCE" --test-secret "$KEY"
  else
    "$BIN" acceptance-prepare --protocol 2 --tool-version "$TV" --project "$P" --state-dir "$S" --evidence-dir "$E" --target "$MODE" --probe container-http --source "$SOURCE" --dry-run
    "$BIN" acceptance-prepare --protocol 2 --tool-version "$TV" --project "$P" --state-dir "$S" --evidence-dir "$E" --target "$MODE" --probe container-http --source "$SOURCE"
  fi
}
update_session() {
  "$BIN" acceptance-update --protocol 2 --tool-version "$TV" --project "$P" --state-dir "$S" --evidence-dir "$E" --target "$MODE" --probe container-http --candidate-source "$C" "$@"
}
expect_rollback() {
  set +e
  RESULT=$(update_session --fault "$1")
  CODE=$?
  set -e
  test "$CODE" = 1
  test "$RESULT" = UPDATE_FAILED_ROLLBACK_OK
  printf '%s\n' "$RESULT"
}
check_public() {
  test "$(curl --silent --show-error --max-time 20 -o /dev/null -w '%{http_code}' https://app.dstorylens.com/)" = 200
  test "$(readlink -f /opt/storylens/current)" = /opt/storylens/releases/4ae7f663
}
```

不替换环境变量来伪装 project。不允许 production project、自由路径、任意 HTTP 地址、
任意 Compose 输入、80/443、外部卷或宿主 bind。项目名限定 sl-accept- 加 8–24 位小写字母/数字。
App 的 KEY 必须显式传入且为工具生成的固定假值；真实 Key、生产路径、多行等全部拒绝。
Web prepare 没有 Provider Secret，即使 Worker 仍运行也不会读取它。
重跑请换全新的 project 后缀；既有 project/卷/网络/状态不能静默复用或重置。

### D. Web 成功

```bash
setup_session sl-accept-webd20260904r5 web
update_session --dry-run
update_session --fault none
check_public
```

预期依次 DRY_RUN_OK、IMAGE_RUNTIME_CONTRACT_OK、ACCEPTANCE_BASELINE_READY、DRY_RUN_OK、UPDATE_OK。
工具生成的候选 index.html 包含 storylens-acceptance/candidate-v2 标识；容器内 HTTP
响应必须出现标识。仅 Web 被重建，非目标容器 ID、隔离数据库、生产身份不变。

### E. Web 失败与回滚（独立的新基线）

```bash
setup_session sl-accept-webe20260904r5 web
expect_rollback health
check_public
```

候选切换后健康检查确定性 exit 1；等待后恢复旧镜像并重建 Web，恢复健康。
成功标志 UPDATE_FAILED_ROLLBACK_OK，exit 1；旧镜像 ID 必须一致，恢复后的容器 ID 可以不同。

### F. App 成功

```bash
setup_session sl-accept-appf20260904r5 app
update_session --dry-run
update_session --fault none
check_public
```

预期 FAKE_TEST_SECRET_CREATED、DRY_RUN_OK、IMAGE_RUNTIME_CONTRACT_OK、ACCEPTANCE_BASELINE_READY、DRY_RUN_OK、UPDATE_OK。
候选只在 errors.py 添加无行为注释，以真实业务镜像测试更新，不改业务模型或迁移。
仅 API/Worker 重建；Worker 原入口执行、PID1=10001:10001；原假Key root600，
tmpfs副本400/10001:10001，64KiB/noexec/nosuid/nodev，应用用户不可读原件。
模型开关只在隔离 Worker 开启以测试暂存，白名单为空，internal 网络阻断公网，不会调用模型。
工具比较隔离 schema 和 jobs/uploads/usage 行数摘要；Web/PB/PG/Redis/init 容器不变。

### G. App 失败与成组回滚

```bash
setup_session sl-accept-appg20260904r5 app
expect_rollback health
check_public
```

预期 UPDATE_FAILED_ROLLBACK_OK；API 和 Worker 一起恢复旧镜像，数据库不变。
如需覆盖 Worker 自身退出，另用新 session：

```bash
setup_session sl-accept-appw20260904r5 app
expect_rollback worker
check_public
```

## H. 拒绝边界、安全扫描与记录

每个新session完成后确认锁不在版本仓库（不删除或重置任何旧锁）：

```bash
test ! -e "/opt/storylens/lib/storylens-online-deploy/$P.lock"
test "$(stat -c '%u:%g:%a:%h' "/run/lock/storylens-online-deploy/$P.lock")" = 0:0:600:1
python3 -I -B "$LIB/deploy_install.py" list > "$AUDIT/registry-after-acceptance.json"
printf '%s\n' LOCK_STORAGE_SEPARATED_OK
```

以下只做拒绝验证，不运行更新：

```bash
set +e
"$BIN" acceptance-update --protocol 999 --tool-version "$TV" --project "$P" --state-dir "$S" --evidence-dir "$E" --target "$MODE" --probe container-http --candidate-source "$C" --dry-run
test $? -ne 0 || exit 1
"$BIN" acceptance-update --protocol 2 --tool-version "$TV" --project storylens-online --state-dir "$S" --evidence-dir "$E" --target "$MODE" --probe container-http --candidate-source "$C" --dry-run
test $? -ne 0 || exit 1
set -e
python3 -m venv "$AUDIT/test-venv"
"$AUDIT/test-venv/bin/python" -m pip install pytest
(umask 022; "$AUDIT/test-venv/bin/python" -m pytest "$SOURCE/infra/online/tests" -q -p no:cacheprovider) > "$AUDIT/tests-full.log" 2>&1
(umask 022; "$AUDIT/test-venv/bin/python" -m pytest "$SOURCE/infra/online/tests/test_deploy_secret_boundary.py" -q -k real_linux -p no:cacheprovider) > "$AUDIT/tests-real-linux.log" 2>&1
(umask 022; "$AUDIT/test-venv/bin/python" -m pytest "$SOURCE/infra/online/tests/test_deploy_database_stdin.py" -q -p no:cacheprovider) > "$AUDIT/tests-database-stdin.log" 2>&1
test "$(umask)" = 0077
test "$(stat -c '%u:%g:%a' "$AUDIT")" = 0:0:700
for name in full real-linux database-stdin; do
  test "$(stat -c '%u:%g:%a' "$AUDIT/tests-$name.log")" = 0:0:600
done
grep -Eq '1 passed' "$AUDIT/tests-real-linux.log"
if grep -Eq '[0-9]+ skipped' "$AUDIT/tests-real-linux.log"; then exit 1; fi
check_public
```

上述测试仅安装到独立验收 venv（不改 API/Worker 镜像）；缺少 python3-venv、pip或联网安装失败时，
停止并将该项记待验收，不要把它记为通过。生产 fault 参数拒绝、SHA错误、非法路径/commit、
已有release、模式不符、未知版本拒绝和回滚失败阻断均有本地自动化测试。
更新成功/回滚成功会自动捕获隔离 Compose/inspect/history/logs 并扫描假Key实值，
不输出原始内容。状态 JSON 仅记录安全 ID、状态和数据库不变结论；不含 Secret 或用户文本。
原始日志如需人工保留，仅放 root-only AUDIT；不得粘贴 env、完整 inspect 或 Secret到聊天。
四组 evidence 目录中的 UPDATE_OK / UPDATE_FAILED_ROLLBACK_OK 才是本次实际运行证据。
对每个 session 补查镜像契约证据（继续使用该 session 的 E 变量）：

```bash
python3 - "$E" <<'PY'
import json, pathlib, sys
records = [json.loads(p.read_text()) for p in pathlib.Path(sys.argv[1]).glob('image-contract-*.json')]
assert records and all(r['status'] == 'IMAGE_RUNTIME_CONTRACT_OK' for r in records)
for r in records:
    assert all(n in r['files'] for n in ('db/init_schema.py','db/models.py','db/phase2b1_migration.py'))
    assert r['image'].startswith('sha256:') and len(r['entrypoint']) == 64
print('IMAGE_CONTRACT_EVIDENCE_OK')
boundaries = [json.loads(p.read_text()) for p in pathlib.Path(sys.argv[1]).glob('secret-boundary-*.json')]
assert boundaries and all(r['status'] == 'SECRET_BOUNDARY_OK' for r in boundaries)
print('SECRET_BOUNDARY_EVIDENCE_OK')
PY
```

Linux定向权限测试必须实际passed（不能skipped）：它在独立/tmp夹具中构造root0700目录，
以UID/GID10001复现旧Path.exists的PermissionError，再执行新版Web及App探针；仅使用固定假值。
该内核测试以/proc/self/status验证子进程身份；真实容器的PID1仍由D–G的/proc/1/status检查。
失败session若出现SECRET_BOUNDARY_FAILED，保留证据并停止，不删除证据后继续标记成功。

重新采集 A 的生产身份并 diff；任何变化都必须解释并停止验收，不能被“网站仍200”掩盖。

### 回滚失败的停止门禁及恢复

在额外独立 session 用 --fault rollback 可验证 ROLLBACK_FAILED_MANUAL_RECOVERY_REQUIRED。
它会保留 state/pending.json，并拒绝所有后续更新。不要删除 marker 强行重试。
中断后的人工恢复：先审计 pending.json 的 rollback_spec，只能是该 project 的隔离 Compose，
确认 API/Worker command 没有 init_schema，卷/网络均为该project，不得对生产执行。
将经核验的 rollback_spec 恢复为该 session 的 compose.json，再仅对目标服务执行：

```bash
# 只在人工审核并恢复了隔离 compose.json 后执行，不使用正式 Compose：
if [ "$MODE" = web ]; then
  docker --host unix:///var/run/docker.sock compose -p "$P" -f "$S/compose.json" up -d --no-build --no-deps online-web
else
  docker --host unix:///var/run/docker.sock compose -p "$P" -f "$S/compose.json" up -d --no-build --no-deps online-api online-worker
fi
```

验证镜像/健康/数据/非目标ID后保存证据；该 session 保留 marker 供审计，使用新 session
继续验收。本工具不声称具有跨 Docker 与文件系统的断电原子性。

## 恢复上一工具版本或卸载入口（不动业务服务）

```bash
python3 -I -B "$LIB/deploy_install.py" list
# 从 bin/previous-tool-*.json 取得已经安装、核验过的完整 commit：
: "${PREVIOUS:?请先设置已核验的上一工具完整commit}"
python3 -I -B "$LIB/deploy_install.py" activate --commit "$PREVIOUS"
"$BIN" version
```

若无上一版，只撤销当前稳定入口（所有版本和业务数据保留）：

```bash
python3 -I -B "$LIB/deploy_install.py" unlink --commit "$COMMIT"
```

不自动删除验收卷、网络、镜像、日志、工具目录；不执行 compose down/down -v。
验收后另列精确的 sl-accept-* 资源清单申请清理，不可使用宽泛删除命令。

## 生产使用与状态

通过隔离验收后，仍需操作者批准生产使用。Windows 正式调用稳定 bin，并传协议/指纹。
生产候选归档来自 Git HEAD，基线为实际部署组件源码；d6416111或本轮工具代码变更本身
不能伪装为Web/App更新。旧生产4ae7f663保持不变，不需把新工具塞进旧release。
只有部署工具代码来自独立 lib；业务基础 Compose 和业务基线仍来自原生产current。
本阶段无数据库迁移，无分析功能修改，无正式版本发布。CHG 保持 tested，香港真实结果待补。
