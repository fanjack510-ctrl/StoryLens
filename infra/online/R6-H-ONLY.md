# R7：关联 R5 D–G，纠正 Linux 测试隔离（CHG 仍 tested）

沿用文件名 R6-H-ONLY.md，是为了兼容已冻结的等价门禁白名单；本文件内容现为R7指南。
`tests/r6_gate.py`和其`--r6-package/--r6-sha256`参数名保持原样，参数值传入R7包。
不新增安装工具或构建输入，不修改生产trusted检查，不重跑D–G容器。

## 已知现场与剩余门禁

用户提供R6香港结果：A/B/C通过，R5/R6的79个运行与构建文件等价、R5 D–G证据可关联。
H全量10 failed、261 passed、9 skipped；十例均来自test_r6_corrective.py。
它们仅patch了deploy_image_contract.trusted，tree_hashes实际使用deploy_acceptance.trusted；
直接调用其他模块的测试函数不会运行该模块的autouse fixture。Linux /tmp祖先导致
UNTRUSTED_PATH提前失败，Windows原检查跳过POSIX属性，未捕获该遗漏。
这是测试隔离缺陷，运行时没有变化。R6包2b2e6b1e已superseded，入口已unlink。
R5实际D–G成功、R1–R6全部历史、容器、卷、镜像、session和锁继续保留。
生产仍4ae7f663、HTTP200（用户证据）；CHG保持tested，香港R7完成前不得verified。

Protocol=2，tool_version仍为
`32799f5ea99f29821eb799dc03f439d09d5a58028f94e227e5b24190f0756dda`。
机器门禁必须证明R7/R5的79个保护文件内容与模式完全一致，包括11个工具、Windows入口、
API/Worker/Web、Dockerfile、Compose、依赖、entrypoint和PB migration。未知输入变化拒绝。
门禁继续核验四组R5 ready session、无pending、更新/回滚状态、镜像完整摘要、Secret边界、
database_unchanged、root600单链接锁及所有留存容器的project/service归属。

## 必须保留的审计输入

PACK、EXPECTED_SHA、EXPECTED_SIZE取本轮最终报告；R5_PACK为原始18f8ee3e包。
R5_AUDIT必须是原始R5 A目录，包含images-before.txt与volumes-before.txt，
不能重建、复制后以新mtime冒充历史。检查容器完整ID、镜像ID、RestartCount、卷名及current。
R5旧命令未记录卷CreatedAt，门禁额外要求当前卷创建时间早于原始卷快照mtime；
若原始文件或Docker时钟不可信、发生过时钟回拨，禁止复用证据，需完整新项目验收。
任何门禁失败都停止；不能更改门禁、删除旧资源或把新查询冒充历史数据库证据。

先人工安全确认生产Phase2B1=false且白名单为空，只记录判断，不打印env。
以下香港命令会安装稳定入口、运行只读证据门禁和测试，不启动或重建任何业务容器。
公开pytest依赖仅安装到新root-only验收目录，不进入API/Worker镜像。

## C：Windows离线命令

在最终R7干净仓库执行并保留输出；香港命令不替代此步骤：

```powershell
.\.venv\Scripts\python.exe -m pytest infra/online/tests/test_deploy_lightweight.py -q -k "powershell_offline_preflight or classifier or protocol" -p no:cacheprovider
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy_online.ps1 -Mode web -Server operator@example.invalid -IdentityFile C:\unused-no-key -BaselineCommit d6416111a6fc5cc8de0c036caa4f0989cfb74f2c -DryRun
```

第一条42 passed；第二条FULL_DEPLOYMENT_REQUIRED/exit1。它不连接服务器、不读取IdentityFile。

## 一条完整香港纠正验收命令

先设置上述五个非秘密变量为实际文件路径和可信报告值。位置参数经sudo传递，不依赖sudo保留环境。
命令中的所有目录均为本次唯一目录；输出目录root0700，日志由外层umask077创建为root0600。
pytest子shell局部使用umask022。先50项纠正测试全部通过，再执行完整部署测试，
然后原real_linux必须1 passed无skipped，database/stdin必须18 passed无skipped。
full在香港平台的跳过数可能与Windows不同，必须exit0且零失败；不能用固定总数掩盖失败。

```bash
sudo bash -s -- "${PACK:?R7包绝对路径}" "${EXPECTED_SHA:?R7可信SHA256}" "${EXPECTED_SIZE:?R7可信字节数}" "${R5_PACK:?原始R5包绝对路径}" "${R5_AUDIT:?原始R5 A审计目录}" <<'R7_ACCEPTANCE'
set -Eeuo pipefail
set +x
umask 077
trap 'printf "%s\n" R7_CORRECTIVE_FAILED_EVIDENCE_RETAINED >&2' ERR
test "$(id -u)" = 0
test "$#" = 5
PACK=$1; EXPECTED_SHA=$2; EXPECTED_SIZE=$3; R5_PACK=$4; R5_AUDIT=$5
test "$(readlink -f /opt/storylens/current)" = /opt/storylens/releases/4ae7f663
test "$(curl -sS --max-time 20 -o /dev/null -w '%{http_code}' https://app.dstorylens.com/ </dev/null)" = 200
test -f "$PACK" && test ! -L "$PACK"
test "$(stat -c %s "$PACK")" = "$EXPECTED_SIZE"
test "$(sha256sum "$PACK" | cut -d ' ' -f1)" = "$EXPECTED_SHA"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)-$$
AUDIT=/opt/storylens/r7-corrective-$STAMP
SOURCE=/opt/storylens/bootstrap-r7-$STAMP
test ! -e "$AUDIT" && test ! -e "$SOURCE"
install -d -m 0700 "$AUDIT"
install -d -m 0755 "$SOURCE"
tar --no-same-owner --no-same-permissions -xzf "$PACK" -C "$SOURCE"
GATE=$SOURCE/infra/online/tests/r6_gate.py
gate_check() {
  python3 -I -B "$GATE" --r5-package "$R5_PACK" --r6-package "$PACK" --r6-sha256 "$EXPECTED_SHA" --r5-audit "$R5_AUDIT" </dev/null
}
gate_check > "$AUDIT/equivalence-before.json"
COMMIT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["commit"])' "$SOURCE/bootstrap.json" </dev/null)
TV=32799f5ea99f29821eb799dc03f439d09d5a58028f94e227e5b24190f0756dda
BIN=/opt/storylens/bin/storylens-online-deploy-lightweight
LEGACY_LOCK=/opt/storylens/lib/storylens-online-deploy/sl-accept-webd20260904.lock
stat -c '%d:%i:%u:%g:%a:%h:%s:%Y' "$LEGACY_LOCK" > "$AUDIT/legacy-before.txt"
PREVIOUS_ENTRY=$(readlink "$BIN" || true)
if python3 -I -B "$SOURCE/infra/online/deploy_install.py" install --source "$SOURCE" > "$AUDIT/install.log" 2>&1 </dev/null; then
  :
else
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
"$BIN" version > "$AUDIT/version.json" </dev/null
python3 -c 'import json,sys;m=json.load(open(sys.argv[1]));assert m["protocol"]==2 and m["tool_version"]==sys.argv[2] and m["commit"]==sys.argv[3]' "$AUDIT/version.json" "$TV" "$COMMIT" </dev/null
python3 -I -B "$LIB/deploy_install.py" list > "$AUDIT/registry.json" </dev/null
stat -c '%d:%i:%u:%g:%a:%h:%s:%Y' "$LEGACY_LOCK" > "$AUDIT/legacy-after.txt"
cmp "$AUDIT/legacy-before.txt" "$AUDIT/legacy-after.txt"
gate_check > "$AUDIT/equivalence-installed.json"
cmp "$AUDIT/equivalence-before.json" "$AUDIT/equivalence-installed.json"
printf '%s\n' A_B_OK_R5_DG_LINKABLE_H_STILL_REQUIRED

python3 -m venv "$AUDIT/test-venv" </dev/null
"$AUDIT/test-venv/bin/python" -m pip install pytest > "$AUDIT/pip.log" 2>&1 </dev/null
(umask 022; "$AUDIT/test-venv/bin/python" -m pytest "$SOURCE/infra/online/tests/test_r6_corrective.py" -q -p no:cacheprovider) > "$AUDIT/tests-corrective.log" 2>&1 </dev/null
grep -Eq '(^|[=[:space:]])50 passed( in |,)' "$AUDIT/tests-corrective.log"
if grep -Eq '[0-9]+ (skipped|failed|error)' "$AUDIT/tests-corrective.log"; then exit 1; fi
printf '%s\n' R7_CORRECTIVE_TESTS_OK
(umask 022; "$AUDIT/test-venv/bin/python" -m pytest "$SOURCE/infra/online/tests" -q -p no:cacheprovider) > "$AUDIT/tests-full.log" 2>&1 </dev/null
(umask 022; "$AUDIT/test-venv/bin/python" -m pytest "$SOURCE/infra/online/tests/test_deploy_secret_boundary.py" -q -k real_linux -p no:cacheprovider) > "$AUDIT/tests-real-linux.log" 2>&1 </dev/null
grep -Eq '(^|[=[:space:]])1 passed( in |,)' "$AUDIT/tests-real-linux.log"
if grep -Eq '[0-9]+ (skipped|failed|error)' "$AUDIT/tests-real-linux.log"; then exit 1; fi
(umask 022; "$AUDIT/test-venv/bin/python" -m pytest "$SOURCE/infra/online/tests/test_deploy_database_stdin.py" -q -p no:cacheprovider) > "$AUDIT/tests-database-stdin.log" 2>&1 </dev/null
grep -Eq '(^|[=[:space:]])18 passed( in |,)' "$AUDIT/tests-database-stdin.log"
if grep -Eq '[0-9]+ (skipped|failed|error)' "$AUDIT/tests-database-stdin.log"; then exit 1; fi
test "$(umask)" = 0077
test "$(stat -c '%u:%g:%a' "$AUDIT")" = 0:0:700
for name in corrective full real-linux database-stdin; do
  test "$(stat -c '%u:%g:%a' "$AUDIT/tests-$name.log")" = 0:0:600
done
gate_check > "$AUDIT/equivalence-after.json"
cmp "$AUDIT/equivalence-before.json" "$AUDIT/equivalence-after.json"
test "$(curl -sS --max-time 20 -o /dev/null -w '%{http_code}' https://app.dstorylens.com/ </dev/null)" = 200
test "$(readlink -f /opt/storylens/current)" = /opt/storylens/releases/4ae7f663
printf '%s\n' R7_CORRECTIVE_CHECKS_OK_PENDING_OPERATOR_SIGNOFF
printf 'AUDIT=%s\nCOMMIT=%s\n' "$AUDIT" "$COMMIT"
R7_ACCEPTANCE
```

成功后保留AUDIT路径以及全部日志；人工复核API等healthy、Worker running、PB-init Exited0，
模型开关仍关闭且白名单为空。只有R7纠正测试、full、真实权限、数据库/stdin、生产身份复查和
Windows C全部满足，才由操作者提供事实另行登记verified。本命令不修改CHG。

失败会exit非零并保留证据及工具目录；没有自动删卷、停止容器或清理旧锁。
若须撤销新稳定入口，只使用已验证R7的LIB/COMMIT调用
`python3 -I -B "$LIB/deploy_install.py" unlink --commit "$COMMIT"`；不要删除版本目录。
任一运行/构建文件或留存证据门禁不通过，停止H-only，另行完整验收；不得自动重跑旧容器。
