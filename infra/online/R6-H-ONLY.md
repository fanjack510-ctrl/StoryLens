# R6：有条件关联 R5 D–G，补齐 H（CHG 仍 tested）

本文件是**待香港操作者执行**的说明。本地从未连接服务器；不能预先标记verified。
Protocol=2；工具指纹必须仍为
`32799f5ea99f29821eb799dc03f439d09d5a58028f94e227e5b24190f0756dda`。
11个版本化工具、Windows入口及归档内所有运行文件/构建输入（含API/Worker/Web、依赖、
Dockerfile、Compose、entrypoint及PB migration）必须与R5逐文件内容和模式一致。
`tests/r6_gate.py`只作为验收附件，不安装到lib，不属于TOOL_FILES，不改变工具指纹。
唯一允许不同：infra/online/tests、ACCEPTANCE.md、本说明及CHG登记。
未知新文件/删除/内容或模式变化全部拒绝，不因“看起来无害”豁免。

## 前置条件及停止边界

操作者须提供原始R5包、R6包和最终报告的可信SHA/大小，以及**原有**R5 A审计目录。
不能重新生成R5历史快照，不能复制后用新mtime冒充原始快照。
门禁比较R5 A的容器完整ID/镜像ID/RestartCount、卷名及current=4ae7f663；R5原命令没有
持久记录卷CreatedAt，因此还检查所有卷的CreatedAt早于原始R5卷快照mtime，以拒绝同名新卷。
这依赖原始root审计文件和可信Docker时钟；若原文件/时间可信性无法证明或发生过时钟回拨，
**禁止H-only，必须完整R6 A–H**，不得用“名字相同”声称卷身份已证明。

R5四个session必须ready、无pending，四组更新状态正确、非目标ID不变、database_unchanged=true，
镜像文件摘要必须对应已验证的R5基线/确定性候选；Secret证据全部OK，无失败证据。
四个root600单链接锁和停止后保留的所有容器必须仍存在，归属project/service必须匹配。
工具只读身份字段，不读取env、Secret、业务行或完整inspect。历史schema/行数不变结论由
原始R5证据关联，不把一次新数据库查询冒充当时证据。资源缺失/不完整即要求完整重验。

## A. 重新采集身份；B. 安装 R6（不改容器）

先人工在安全终端确认Phase2B1关闭、白名单为空；只记录判断，不打印env。
设置PACK、EXPECTED_SHA、EXPECTED_SIZE为已上传R6包和本轮报告值；R5_PACK为保留的R5包；
R5_AUDIT为原始R5 A审计目录（包含images-before.txt和volumes-before.txt）。不用read或set -x。

```bash
set -eu
umask 077
test "$(id -u)" = 0
: "${PACK:?R6包绝对路径}"
: "${EXPECTED_SHA:?R6可信SHA256}"
: "${EXPECTED_SIZE:?R6可信字节数}"
: "${R5_PACK:?保留的R5包绝对路径}"
: "${R5_AUDIT:?原始R5 A审计目录}"
test "$(readlink -f /opt/storylens/current)" = /opt/storylens/releases/4ae7f663
test "$(curl -sS --max-time 20 -o /dev/null -w '%{http_code}' https://app.dstorylens.com/)" = 200
test -f "$PACK" && test ! -L "$PACK"
test "$(stat -c %s "$PACK")" = "$EXPECTED_SIZE"
test "$(sha256sum "$PACK" | cut -d ' ' -f1)" = "$EXPECTED_SHA"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
AUDIT=/opt/storylens/r6-corrective-$STAMP
SOURCE=/opt/storylens/bootstrap-r6-$STAMP
test ! -e "$AUDIT" && test ! -e "$SOURCE"
install -d -m 0700 "$AUDIT"
install -d -m 0755 "$SOURCE"
tar --no-same-owner --no-same-permissions -xzf "$PACK" -C "$SOURCE"
GATE=$SOURCE/infra/online/tests/r6_gate.py
python3 -I -B "$GATE" --r5-package "$R5_PACK" --r6-package "$PACK" --r6-sha256 "$EXPECTED_SHA" --r5-audit "$R5_AUDIT" > "$AUDIT/equivalence-before.json"
COMMIT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["commit"])' "$SOURCE/bootstrap.json")
TV=32799f5ea99f29821eb799dc03f439d09d5a58028f94e227e5b24190f0756dda
BIN=/opt/storylens/bin/storylens-online-deploy-lightweight
LEGACY_LOCK=/opt/storylens/lib/storylens-online-deploy/sl-accept-webd20260904.lock
stat -c '%d:%i:%u:%g:%a:%h:%s:%Y' "$LEGACY_LOCK" > "$AUDIT/legacy-before.txt"
PREVIOUS_ENTRY=$(readlink "$BIN" || true)
set +e
python3 -I -B "$SOURCE/infra/online/deploy_install.py" install --source "$SOURCE" > "$AUDIT/install.log" 2>&1
RC=$?
set -e
if [ "$RC" -ne 0 ]; then
  test "$(readlink "$BIN" || true)" = "$PREVIOUS_ENTRY"
  printf '%s\n' B_INSTALL_FAILED_ENTRY_RESTORED
  exit 1
fi
LIB=/opt/storylens/lib/storylens-online-deploy/$COMMIT
test "$(readlink -f "$BIN")" = "$LIB/deploy-lightweight.sh"
test "$(stat -c '%u:%g:%a' "$LIB")" = 0:0:700
test "$(stat -c '%u:%g:%a' "$LIB/deploy-lightweight.sh")" = 0:0:555
test "$(stat -c '%u:%g:%a' "$LIB/deploy_cli.py")" = 0:0:444
sh -n "$LIB/deploy-lightweight.sh"
"$BIN" version > "$AUDIT/version.json"
python3 -c 'import json,sys;m=json.load(open(sys.argv[1]));assert m["protocol"]==2 and m["tool_version"]==sys.argv[2] and m["commit"]==sys.argv[3]' "$AUDIT/version.json" "$TV" "$COMMIT"
python3 -I -B "$LIB/deploy_install.py" list > "$AUDIT/registry.json"
stat -c '%d:%i:%u:%g:%a:%h:%s:%Y' "$LEGACY_LOCK" > "$AUDIT/legacy-after.txt"
cmp "$AUDIT/legacy-before.txt" "$AUDIT/legacy-after.txt"
python3 -I -B "$GATE" --r5-package "$R5_PACK" --r6-package "$PACK" --r6-sha256 "$EXPECTED_SHA" --r5-audit "$R5_AUDIT" > "$AUDIT/equivalence-installed.json"
cmp "$AUDIT/equivalence-before.json" "$AUDIT/equivalence-installed.json"
printf '%s\n' A_B_OK_R5_DG_LINKABLE_H_STILL_REQUIRED
```

gate失败只输出R6_GATE_FAILED_FULL_ACCEPTANCE_REQUIRED/exit1。不得继续H-only或把门禁替换为true。
不会启动旧session、创建新业务容器、修改current或写入生产数据库；失败也不清理资源。

## C. Windows离线（在R6干净仓库中）

```powershell
.\.venv\Scripts\python.exe -m pytest infra/online/tests/test_deploy_lightweight.py -q -k "powershell_offline_preflight or classifier or protocol" -p no:cacheprovider
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy_online.ps1 -Mode web -Server operator@example.invalid -IdentityFile C:\unused-no-key -BaselineCommit d6416111a6fc5cc8de0c036caa4f0989cfb74f2c -DryRun
```

第一条应42 passed；第二条必须FULL_DEPLOYMENT_REQUIRED/exit1，不连接服务器。

## D–G. 关联而非重跑

只有gate成功才关联sl-accept-webd20260904r5、webe20260904r5、appf20260904r5、appg20260904r5。
equivalence-before.json记录每个保护文件摘要和四组证据文件摘要；保留全部原件，不改写R5。
R6没有新的D–G执行结果，不声称重跑通过。

## H. 纠正测试及最终复查

继续同一root shell；外层umask077，测试输出重定向在子shell之外，文件由外层创建为0600。
仍实际运行原real_linux测试的root0700及UID/GID10001场景，不改场景或跳过。

```bash
test "$(umask)" = 0077
python3 -m venv "$AUDIT/test-venv"
"$AUDIT/test-venv/bin/python" -m pip install pytest > "$AUDIT/pip.log" 2>&1
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
python3 -I -B "$GATE" --r5-package "$R5_PACK" --r6-package "$PACK" --r6-sha256 "$EXPECTED_SHA" --r5-audit "$R5_AUDIT" > "$AUDIT/equivalence-after.json"
cmp "$AUDIT/equivalence-before.json" "$AUDIT/equivalence-after.json"
test "$(curl -sS --max-time 20 -o /dev/null -w '%{http_code}' https://app.dstorylens.com/)" = 200
test "$(readlink -f /opt/storylens/current)" = /opt/storylens/releases/4ae7f663
printf '%s\n' R6_CORRECTIVE_CHECKS_OK_PENDING_OPERATOR_SIGNOFF
```

须人工复核full日志没有失败，real_linux确实1passed无skipped，数据库/stdin18passed；API等仍healthy、
Worker running、PB-initExited0。仅在A/B/C、等价、历史D–G关联、H全部成立且生产开关仍关闭后，
操作者才可提供最终A–H验收证据另行登记verified。脚本不修改CHG状态。
保留R5和R6全部产物、日志、锁、容器、镜像和卷；不执行down或删除操作。
若需要关闭稳定入口（不卸载版本、不动服务）：

```bash
python3 -I -B "$LIB/deploy_install.py" unlink --commit "$COMMIT"
```

若需恢复已核验旧入口，按ACCEPTANCE.md末尾activate命令操作；superseded包不用于新安装。
任一等价门禁失败，完整重验仅使用全新项目sl-accept-webd20260904r6、sl-accept-webe20260904r6、
sl-accept-appf20260904r6、sl-accept-appg20260904r6（可选appw20260904r6），执行ACCEPTANCE.md
完整A–H；不复用任何R5资源、不删除失败证据、不强行降级检查。
