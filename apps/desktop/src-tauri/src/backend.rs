use serde::Serialize;
use std::collections::HashSet;
use std::io::{BufRead, BufReader};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager};

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "state", rename_all = "snake_case")]
pub enum BackendStatus {
    Stopped,
    Starting,
    Ready {
        api_base: String,
        port: u16,
    },
    Failed {
        user_message: String,
        detail: String,
    },
}

/// Lifecycle object for one StoryLens-owned sidecar instance.
pub struct SidecarLifecycle {
    pub child: Option<Child>,
    pub spawn_pid: u32,
    pub owned_pids: Vec<u32>,
    pub port: u16,
    pub sidecar_path: PathBuf,
    pub shutdown_token: String,
    pub baseline_path_pids: HashSet<u32>,
    #[cfg(windows)]
    pub job: Option<crate::win_lifecycle::JobHandle>,
}

pub struct BackendState {
    pub status: BackendStatus,
    pub lifecycle: Option<SidecarLifecycle>,
}

impl Default for BackendState {
    fn default() -> Self {
        Self {
            status: BackendStatus::Starting,
            lifecycle: None,
        }
    }
}

#[derive(Debug, Clone)]
pub struct BackendError {
    pub user_message: String,
    pub detail: String,
}

/// Merge PID sets without duplicates; used by stop logic and unit tests.
pub fn merge_owned_pids(sets: &[&[u32]]) -> Vec<u32> {
    let mut out = Vec::new();
    let mut seen = HashSet::new();
    for set in sets {
        for &pid in *set {
            if pid == 0 {
                continue;
            }
            if seen.insert(pid) {
                out.push(pid);
            }
        }
    }
    out
}

/// Path-delta ownership: new PIDs for the same executable that were not present at baseline.
pub fn path_delta_pids(baseline: &HashSet<u32>, current: &[u32]) -> Vec<u32> {
    current
        .iter()
        .copied()
        .filter(|pid| *pid != 0 && !baseline.contains(pid))
        .collect()
}

/// Decide whether a candidate PID belongs to this instance (never other StoryLens installs).
pub fn is_owned_candidate(pid: u32, owned: &[u32], baseline: &HashSet<u32>) -> bool {
    if pid == 0 || baseline.contains(&pid) {
        return false;
    }
    owned.contains(&pid)
}

fn find_free_port() -> Result<u16, BackendError> {
    TcpListener::bind("127.0.0.1:0")
        .map_err(|e| BackendError {
            user_message: "无法分配本地端口，请稍后重试或重启电脑。".into(),
            detail: format!("bind 127.0.0.1:0 failed: {e}"),
        })
        .and_then(|listener| {
            listener.local_addr().map(|addr| addr.port()).map_err(|e| {
                BackendError {
                    user_message: "无法分配本地端口，请稍后重试或重启电脑。".into(),
                    detail: format!("local_addr failed: {e}"),
                }
            })
        })
}

fn sidecar_candidates(app: &AppHandle) -> Vec<PathBuf> {
    let mut paths = Vec::new();
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            paths.push(dir.join("storylens-api.exe"));
            paths.push(dir.join("storylens-api"));
            paths.push(dir.join("binaries").join("storylens-api.exe"));
        }
    }
    if let Ok(resource) = app.path().resource_dir() {
        paths.push(resource.join("storylens-api.exe"));
        paths.push(resource.join("binaries").join("storylens-api.exe"));
    }
    if let Ok(manifest) = std::env::var("CARGO_MANIFEST_DIR") {
        let triple = std::env::var("TARGET")
            .unwrap_or_else(|_| "x86_64-pc-windows-msvc".into());
        let base = PathBuf::from(manifest).join("binaries");
        paths.push(base.join(format!("storylens-api-{triple}.exe")));
        paths.push(base.join("storylens-api.exe"));
    }
    paths
}

fn resolve_sidecar(app: &AppHandle) -> Result<PathBuf, BackendError> {
    for path in sidecar_candidates(app) {
        if path.is_file() {
            return Ok(path);
        }
    }
    Err(BackendError {
        user_message: "安装不完整：缺少本地分析服务组件。请重新安装 StoryLens。".into(),
        detail: format!("sidecar not found; tried {:?}", sidecar_candidates(app)),
    })
}

fn normalize_path_key(path: &Path) -> String {
    path.canonicalize()
        .unwrap_or_else(|_| path.to_path_buf())
        .to_string_lossy()
        .trim_end_matches(['\\', '/'])
        .to_lowercase()
}

fn pids_for_executable_path(path: &Path) -> Vec<u32> {
    #[cfg(windows)]
    {
        let key = normalize_path_key(path);
        crate::win_lifecycle::pids_for_executable_path(&key)
    }
    #[cfg(not(windows))]
    {
        let _ = path;
        Vec::new()
    }
}

fn descendant_pids(root: u32) -> Vec<u32> {
    #[cfg(windows)]
    {
        crate::win_lifecycle::descendant_pids(root)
    }
    #[cfg(not(windows))]
    {
        let _ = root;
        Vec::new()
    }
}

fn terminate_pid(pid: u32) {
    #[cfg(windows)]
    {
        crate::win_lifecycle::terminate_pid(pid);
    }
    #[cfg(not(windows))]
    {
        let _ = pid;
    }
}

fn pid_alive(pid: u32) -> bool {
    #[cfg(windows)]
    {
        crate::win_lifecycle::pid_alive(pid)
    }
    #[cfg(not(windows))]
    {
        let _ = pid;
        false
    }
}

fn listen_owner_pid(port: u16) -> Option<u32> {
    #[cfg(windows)]
    {
        crate::win_lifecycle::tcp_listen_owner(port)
    }
    #[cfg(not(windows))]
    {
        let _ = port;
        None
    }
}

fn random_shutdown_token() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    format!("sl-{nanos}-{:08x}", std::process::id())
}

fn spawn_sidecar(
    path: &PathBuf,
    port: u16,
    log_dir: &PathBuf,
    shutdown_token: &str,
    baseline_path_pids: HashSet<u32>,
    app_version: &str,
) -> Result<SidecarLifecycle, BackendError> {
    let _ = std::fs::create_dir_all(log_dir);
    let mut cmd = Command::new(path);
    cmd.env("STORYLENS_APP_HOST", "127.0.0.1")
        .env("STORYLENS_APP_PORT", port.to_string())
        .env("STORYLENS_APP_ENV", "production")
        .env("STORYLENS_SHUTDOWN_TOKEN", shutdown_token)
        // V1.2.0 Free contract: installed production sidecar enables formal whole-book.
        // Fixture / diagnostics remain off unless explicitly set by the process environment.
        .env("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", "true")
        .env("STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED", "true")
        .stdout(Stdio::null())
        .stderr(Stdio::piped());

    // CHG-20260727-016: do not force PRO_NATIVE_OVERVIEW_ENABLED for RC builds.
    // Repository / formal default remains off; set the env explicitly for internal validation.
    let _ = app_version;

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = cmd.spawn().map_err(|e| {
        let msg = if e.raw_os_error() == Some(2) {
            "安装不完整：缺少本地分析服务组件。请重新安装 StoryLens。"
        } else {
            "本地分析服务启动失败。请查看日志或重新安装后重试。"
        };
        BackendError {
            user_message: msg.into(),
            detail: format!("spawn {:?} failed: {e}", path),
        }
    })?;

    let spawn_pid = child.id();

    #[cfg(windows)]
    let job = {
        use std::os::windows::io::AsRawHandle;
        let job = crate::win_lifecycle::JobHandle::create();
        if let Some(ref job) = job {
            // Prefer assigning via the Child process handle before it can orphan children.
            let _ = job.assign_raw_handle(child.as_raw_handle());
            let _ = job.assign_pid(spawn_pid);
        }
        job
    };

    if let Some(stderr) = child.stderr.take() {
        let log_path = log_dir.join("sidecar-stderr.log");
        thread::spawn(move || {
            let reader = BufReader::new(stderr);
            if let Ok(mut file) = std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(&log_path)
            {
                use std::io::Write;
                for line in reader.lines().flatten() {
                    let _ = writeln!(file, "{line}");
                }
            }
        });
    }

    Ok(SidecarLifecycle {
        child: Some(child),
        spawn_pid,
        owned_pids: vec![spawn_pid],
        port,
        sidecar_path: path.clone(),
        shutdown_token: shutdown_token.to_string(),
        baseline_path_pids,
        #[cfg(windows)]
        job,
    })
}

const MAX_PORT_ATTEMPTS: u32 = 3;

fn sidecar_stderr_log_path(log_dir: &PathBuf) -> PathBuf {
    log_dir.join("sidecar-stderr.log")
}

fn read_sidecar_error_token(log_dir: &PathBuf) -> Option<String> {
    let path = sidecar_stderr_log_path(log_dir);
    let content = std::fs::read_to_string(path).ok()?;
    for line in content.lines().rev().take(40) {
        if let Some(rest) = line.strip_prefix("STORYLENS_SIDECAR_ERROR=") {
            return Some(rest.to_string());
        }
    }
    None
}

fn map_sidecar_token_to_user_message(token: &str) -> Option<String> {
    if token.starts_with("DATA_DIR_NOT_WRITABLE") {
        return Some(
            "无法写入 StoryLens 数据目录。请检查磁盘空间与文件夹权限，或更换安装位置后重试。"
                .into(),
        );
    }
    if token.starts_with("PORT_OR_BIND_FAILED") {
        return Some("本地分析服务端口被占用。请关闭占用端口的程序后重试。".into());
    }
    None
}

fn should_retry_port(err: &BackendError, log_dir: &PathBuf, attempt: u32) -> bool {
    if attempt >= MAX_PORT_ATTEMPTS {
        return false;
    }
    if err.detail.contains("health check timeout") {
        return false;
    }
    if err.detail.contains("sidecar exited during health wait") {
        if let Some(token) = read_sidecar_error_token(log_dir) {
            if token.starts_with("DATA_DIR_NOT_WRITABLE") {
                return false;
            }
            if token.starts_with("PORT_OR_BIND_FAILED") {
                return true;
            }
        }
        return attempt + 1 < MAX_PORT_ATTEMPTS;
    }
    false
}

fn health_ok(port: u16) -> bool {
    let url = format!("http://127.0.0.1:{port}/health");
    let agent = ureq::AgentBuilder::new()
        .timeout_connect(Duration::from_secs(2))
        .timeout(Duration::from_secs(3))
        .build();
    matches!(agent.get(&url).call(), Ok(resp) if resp.status() == 200)
}

fn discover_owned_pids(
    spawn_pid: u32,
    sidecar_path: &Path,
    baseline: &HashSet<u32>,
    port: u16,
) -> Vec<u32> {
    let path_now = pids_for_executable_path(sidecar_path);
    let delta = path_delta_pids(baseline, &path_now);
    let descendants = descendant_pids(spawn_pid);
    let spawn = [spawn_pid];
    let mut listen = Vec::new();
    if let Some(owner) = listen_owner_pid(port) {
        let tentative = merge_owned_pids(&[&spawn, &delta, &descendants]);
        if is_owned_candidate(owner, &tentative, baseline)
            || (!baseline.contains(&owner)
                && (delta.contains(&owner)
                    || descendants.contains(&owner)
                    || owner == spawn_pid
                    || (path_now.contains(&owner) && !baseline.contains(&owner))))
        {
            listen.push(owner);
        }
    }
    merge_owned_pids(&[&spawn, &delta, &descendants, &listen])
}

fn wait_for_health(
    lifecycle: &mut SidecarLifecycle,
    log_dir: &PathBuf,
) -> Result<(), BackendError> {
    let port = lifecycle.port;
    let deadline = Instant::now() + Duration::from_secs(60);

    while Instant::now() < deadline {
        lifecycle.owned_pids = discover_owned_pids(
            lifecycle.spawn_pid,
            &lifecycle.sidecar_path,
            &lifecycle.baseline_path_pids,
            port,
        );

        if health_ok(port) {
            lifecycle.owned_pids = discover_owned_pids(
                lifecycle.spawn_pid,
                &lifecycle.sidecar_path,
                &lifecycle.baseline_path_pids,
                port,
            );
            return Ok(());
        }

        let wrapper_exited = match lifecycle.child.as_mut() {
            Some(child) => match child.try_wait() {
                Ok(Some(_)) => {
                    lifecycle.child = None;
                    true
                }
                Ok(None) => false,
                Err(e) => {
                    return Err(BackendError {
                        user_message: "无法确认本地分析服务状态。请重启 StoryLens。".into(),
                        detail: format!("try_wait failed: {e}"),
                    });
                }
            },
            None => true,
        };

        if wrapper_exited {
            // PyInstaller onefile may leave the real service alive after wrapper exit.
            let any_owned_alive = lifecycle.owned_pids.iter().any(|pid| pid_alive(*pid));
            if !any_owned_alive {
                let mut user_message =
                    "本地分析服务意外退出。请重启 StoryLens；若反复出现，请重新安装。".to_string();
                let mut detail = "sidecar exited during health wait".to_string();
                if let Some(token) = read_sidecar_error_token(log_dir) {
                    detail = format!("{detail}; token={token}");
                    if let Some(mapped) = map_sidecar_token_to_user_message(&token) {
                        user_message = mapped;
                    }
                }
                return Err(BackendError {
                    user_message,
                    detail,
                });
            }
        }

        thread::sleep(Duration::from_millis(300));
    }

    Err(BackendError {
        user_message: "本地分析服务启动超时。请确认端口未被占用后重试。".into(),
        detail: format!("health check timeout for http://127.0.0.1:{port}/health"),
    })
}

fn request_http_shutdown(port: u16, token: &str) -> bool {
    let url = format!("http://127.0.0.1:{port}/internal/shutdown");
    let agent = ureq::AgentBuilder::new()
        .timeout_connect(Duration::from_secs(2))
        .timeout(Duration::from_secs(3))
        .build();
    match agent
        .post(&url)
        .set("Authorization", &format!("Bearer {token}"))
        .call()
    {
        Ok(resp) => resp.status() == 200,
        Err(_) => false,
    }
}

fn wait_pids_exit(pids: &[u32], timeout: Duration) -> Vec<u32> {
    let deadline = Instant::now() + timeout;
    loop {
        let alive: Vec<u32> = pids.iter().copied().filter(|p| pid_alive(*p)).collect();
        if alive.is_empty() {
            return Vec::new();
        }
        if Instant::now() >= deadline {
            return alive;
        }
        thread::sleep(Duration::from_millis(100));
    }
}

fn force_stop_owned_pids(pids: &[u32]) {
    for pid in pids.iter().rev() {
        if pid_alive(*pid) {
            terminate_pid(*pid);
        }
    }
}

/// Stop this app's sidecar: prefer graceful HTTP shutdown, then exact owned PIDs.
pub fn stop_lifecycle(mut life: SidecarLifecycle) {
    life.owned_pids = discover_owned_pids(
        life.spawn_pid,
        &life.sidecar_path,
        &life.baseline_path_pids,
        life.port,
    );

    let _ = request_http_shutdown(life.port, &life.shutdown_token);
    let remaining = wait_pids_exit(&life.owned_pids, Duration::from_secs(5));
    if !remaining.is_empty() {
        force_stop_owned_pids(&remaining);
        let _ = wait_pids_exit(&remaining, Duration::from_secs(3));
    }

    // Also re-scan path delta in case a late orphan appeared.
    let late = discover_owned_pids(
        life.spawn_pid,
        &life.sidecar_path,
        &life.baseline_path_pids,
        life.port,
    );
    let still = wait_pids_exit(&late, Duration::from_millis(200));
    if !still.is_empty() {
        force_stop_owned_pids(&still);
        let _ = wait_pids_exit(&still, Duration::from_secs(2));
    }

    if let Some(mut child) = life.child.take() {
        let _ = child.try_wait();
    }

    // Dropping the Job handle with KILL_ON_JOB_CLOSE is a final safety net on Windows.
    #[cfg(windows)]
    {
        drop(life.job.take());
    }
}

fn cleanup_failed_spawn(life: SidecarLifecycle) {
    stop_lifecycle(life);
}

fn user_log_dir() -> PathBuf {
    let base = std::env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(".").join("data"));
    base.join("StoryLens").join("logs")
}

pub fn start_backend(app: &AppHandle) -> Result<(), BackendError> {
    let state = app
        .try_state::<Mutex<BackendState>>()
        .ok_or_else(|| BackendError {
            user_message: "应用内部状态异常，请重启 StoryLens。".into(),
            detail: "BackendState missing".into(),
        })?;

    {
        let mut guard = state.lock().map_err(|e| BackendError {
            user_message: "应用内部状态异常，请重启 StoryLens。".into(),
            detail: e.to_string(),
        })?;
        guard.status = BackendStatus::Starting;
    }

    let sidecar = resolve_sidecar(app)?;
    let log_dir = user_log_dir();
    // Capture same-path PIDs before any spawn so we never claim other instances.
    let baseline_path_pids: HashSet<u32> = pids_for_executable_path(&sidecar).into_iter().collect();

    let mut ready_life: Option<SidecarLifecycle> = None;

    let app_version = app.package_info().version.to_string();

    for attempt in 0..MAX_PORT_ATTEMPTS {
        let port = find_free_port()?;
        let token = random_shutdown_token();
        let mut life = spawn_sidecar(
            &sidecar,
            port,
            &log_dir,
            &token,
            baseline_path_pids.clone(),
            &app_version,
        )?;

        {
            let mut guard = state.lock().map_err(|e| BackendError {
                user_message: "应用内部状态异常，请重启 StoryLens。".into(),
                detail: e.to_string(),
            })?;
            if let Some(prev) = guard.lifecycle.take() {
                cleanup_failed_spawn(prev);
            }
        }

        match wait_for_health(&mut life, &log_dir) {
            Ok(()) => {
                ready_life = Some(life);
                break;
            }
            Err(err) => {
                cleanup_failed_spawn(life);
                if should_retry_port(&err, &log_dir, attempt) {
                    continue;
                }
                if let Ok(mut guard) = state.lock() {
                    guard.lifecycle = None;
                    guard.status = BackendStatus::Failed {
                        user_message: err.user_message.clone(),
                        detail: err.detail.clone(),
                    };
                }
                return Err(err);
            }
        }
    }

    let life = ready_life.ok_or_else(|| BackendError {
        user_message: "本地分析服务启动失败。请重新安装后重试。".into(),
        detail: "no sidecar child after port attempts".into(),
    })?;

    let api_base = format!("http://127.0.0.1:{}", life.port);
    let watch_spawn = life.spawn_pid;
    let watch_port = life.port;
    let watch_path = life.sidecar_path.clone();
    let watch_baseline = life.baseline_path_pids.clone();

    {
        let mut guard = state.lock().map_err(|e| BackendError {
            user_message: "应用内部状态异常，请重启 StoryLens。".into(),
            detail: e.to_string(),
        })?;
        guard.status = BackendStatus::Ready {
            api_base: api_base.clone(),
            port: life.port,
        };
        guard.lifecycle = Some(life);
    }

    let _ = app.emit("backend-ready", api_base);

    // Watch unexpected exit of the *service*, not merely the wrapper process.
    let watch_app = app.clone();
    thread::spawn(move || loop {
        thread::sleep(Duration::from_secs(2));
        let owned = discover_owned_pids(watch_spawn, &watch_path, &watch_baseline, watch_port);
        let service_alive = health_ok(watch_port) || owned.iter().any(|p| pid_alive(*p));
        if service_alive {
            if let Some(state) = watch_app.try_state::<Mutex<BackendState>>() {
                if let Ok(mut guard) = state.lock() {
                    if let Some(life) = guard.lifecycle.as_mut() {
                        life.owned_pids = owned;
                    }
                }
            }
            continue;
        }

        let detail = "sidecar service no longer reachable".to_string();
        let user_message =
            "本地分析服务意外退出。请重启 StoryLens；若反复出现，请重新安装。".to_string();
        let _ = watch_app.emit("backend-error", user_message.clone());
        if let Some(state) = watch_app.try_state::<Mutex<BackendState>>() {
            if let Ok(mut guard) = state.lock() {
                guard.status = BackendStatus::Failed {
                    user_message,
                    detail,
                };
                if let Some(life) = guard.lifecycle.take() {
                    force_stop_owned_pids(&life.owned_pids);
                }
            }
        }
        break;
    });

    Ok(())
}

pub fn stop_backend(state: &Mutex<BackendState>) {
    if let Ok(mut guard) = state.lock() {
        if let Some(life) = guard.lifecycle.take() {
            stop_lifecycle(life);
        }
        guard.status = BackendStatus::Stopped;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn merge_owned_pids_dedupes_and_skips_zero() {
        let a = [1u32, 2, 0];
        let b = [2u32, 3];
        assert_eq!(merge_owned_pids(&[&a, &b]), vec![1, 2, 3]);
    }

    #[test]
    fn path_delta_excludes_baseline() {
        let mut baseline = HashSet::new();
        baseline.insert(10);
        baseline.insert(11);
        let current = [10u32, 12, 13];
        assert_eq!(path_delta_pids(&baseline, &current), vec![12, 13]);
    }

    #[test]
    fn owned_candidate_ignores_other_instance_baseline() {
        let mut baseline = HashSet::new();
        baseline.insert(99);
        let owned = [42u32, 43];
        assert!(!is_owned_candidate(99, &owned, &baseline));
        assert!(is_owned_candidate(42, &owned, &baseline));
        assert!(!is_owned_candidate(77, &owned, &baseline));
    }

    #[test]
    fn wrapper_exit_still_tracks_service_pid_via_delta() {
        // Simulate: spawn wrapper 100 exits; service 200 is new same-path PID.
        let mut baseline = HashSet::new();
        baseline.insert(50); // unrelated pre-existing instance
        let current_after = [50u32, 200];
        let delta = path_delta_pids(&baseline, &current_after);
        let owned = merge_owned_pids(&[&[100], &delta]);
        assert!(owned.contains(&200));
        assert!(owned.contains(&100));
        assert!(!owned.contains(&50));
        assert!(is_owned_candidate(200, &owned, &baseline));
        assert!(!is_owned_candidate(50, &owned, &baseline));
    }
}
