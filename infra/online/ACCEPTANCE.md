# Protocol 2：首次安装与香港隔离 A–H 验收

关联 CHG-20260903-001；VERSION 保持 1.3.6。以下是操作者待执行命令，
不是已经通过的服务器证据。所有 Docker 命令只在人工批准的香港验收窗口执行。
工具不会打开正式模型开关，不会推送、发布或创建标签。

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

把最终报告中的包路径、SHA256、字节数分别输入下列提示（不是 Key）：

```bash
printf '已上传的 tar.gz 绝对路径: '; read -r PACK
printf '可信交付报告的 SHA256: '; read -r EXPECTED_SHA
printf '可信交付报告的字节数: '; read -r EXPECTED_SIZE
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
python3 -I -B "$SOURCE/infra/online/deploy_install.py" install --source "$SOURCE"
BIN=/opt/storylens/bin/storylens-online-deploy-lightweight
LIB=/opt/storylens/lib/storylens-online-deploy/$COMMIT
test "$(readlink -f "$BIN")" = "$LIB/deploy-lightweight.sh"
stat -c '%U:%G %a %n' "$LIB" "$LIB/deploy-lightweight.sh" "$LIB/deploy_cli.py"
"$BIN" version > "$AUDIT/tool-version.json"
python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); assert m["protocol"]==2 and m["tool_version"]==sys.argv[2] and m["commit"]==sys.argv[3]' "$AUDIT/tool-version.json" "$TV" "$COMMIT"
python3 -I -B "$LIB/deploy_install.py" list
printf '%s\n' B_INSTALLED_NO_CONTAINERS_CHANGED
```

安装器验证包内全部源码摘要和工具指纹；所有文件来自最终 Git archive，bootstrap.json
是生成的非秘密元数据。外部 SHA 校验是信任起点，包内摘要不能代替它。
lib 目录 root:root，仅 root 可写；shell=0555，Python 和 installed.json=0444。
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
setup_session sl-accept-webd20260904 web
update_session --dry-run
update_session --fault none
check_public
```

预期依次 DRY_RUN_OK、ACCEPTANCE_BASELINE_READY、DRY_RUN_OK、UPDATE_OK。
工具生成的候选 index.html 包含 storylens-acceptance/candidate-v2 标识；容器内 HTTP
响应必须出现标识。仅 Web 被重建，非目标容器 ID、隔离数据库、生产身份不变。

### E. Web 失败与回滚（独立的新基线）

```bash
setup_session sl-accept-webe20260904 web
expect_rollback health
check_public
```

候选切换后健康检查确定性 exit 1；等待后恢复旧镜像并重建 Web，恢复健康。
成功标志 UPDATE_FAILED_ROLLBACK_OK，exit 1；旧镜像 ID 必须一致，恢复后的容器 ID 可以不同。

### F. App 成功

```bash
setup_session sl-accept-appf20260904 app
update_session --dry-run
update_session --fault none
check_public
```

预期 FAKE_TEST_SECRET_CREATED、DRY_RUN_OK、ACCEPTANCE_BASELINE_READY、DRY_RUN_OK、UPDATE_OK。
候选只在 errors.py 添加无行为注释，以真实业务镜像测试更新，不改业务模型或迁移。
仅 API/Worker 重建；Worker 原入口执行、PID1=10001:10001；原假Key root600，
tmpfs副本400/10001:10001，64KiB/noexec/nosuid/nodev，应用用户不可读原件。
模型开关只在隔离 Worker 开启以测试暂存，白名单为空，internal 网络阻断公网，不会调用模型。
工具比较隔离 schema 和 jobs/uploads/usage 行数摘要；Web/PB/PG/Redis/init 容器不变。

### G. App 失败与成组回滚

```bash
setup_session sl-accept-appg20260904 app
expect_rollback health
check_public
```

预期 UPDATE_FAILED_ROLLBACK_OK；API 和 Worker 一起恢复旧镜像，数据库不变。
如需覆盖 Worker 自身退出，另用新 session：

```bash
setup_session sl-accept-appw20260904 app
expect_rollback worker
check_public
```

## H. 拒绝边界、安全扫描与记录

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
"$AUDIT/test-venv/bin/python" -m pytest "$SOURCE/infra/online/tests" -q -p no:cacheprovider
check_public
```

上述测试仅安装到独立验收 venv（不改 API/Worker 镜像）；缺少 python3-venv、pip或联网安装失败时，
停止并将该项记待验收，不要把它记为通过。生产 fault 参数拒绝、SHA错误、非法路径/commit、
已有release、模式不符、未知版本拒绝和回滚失败阻断均有本地自动化测试。
更新成功/回滚成功会自动捕获隔离 Compose/inspect/history/logs 并扫描假Key实值，
不输出原始内容。状态 JSON 仅记录安全 ID、状态和数据库不变结论；不含 Secret 或用户文本。
原始日志如需人工保留，仅放 root-only AUDIT；不得粘贴 env、完整 inspect 或 Secret到聊天。
四组 evidence 目录中的 UPDATE_OK / UPDATE_FAILED_ROLLBACK_OK 才是本次实际运行证据。
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
printf '要恢复的完整工具 commit: '; read -r PREVIOUS
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
