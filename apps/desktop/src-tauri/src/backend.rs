use serde::Serialize;
use std::io::{BufRead, BufReader};
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
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

pub struct BackendState {
    pub status: BackendStatus,
    pub child: Option<Arc<Mutex<Child>>>,
}

impl Default for BackendState {
    fn default() -> Self {
        Self {
            status: BackendStatus::Starting,
            child: None,
        }
    }
}

#[derive(Debug, Clone)]
pub struct BackendError {
    pub user_message: String,
    pub detail: String,
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
            // Tauri externalBin may live next to resources
            paths.push(dir.join("binaries").join("storylens-api.exe"));
        }
    }
    if let Ok(resource) = app.path().resource_dir() {
        paths.push(resource.join("storylens-api.exe"));
        paths.push(resource.join("binaries").join("storylens-api.exe"));
    }
    // Dev: src-tauri/binaries/<name>-<triple>.exe
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

fn spawn_sidecar(path: &PathBuf, port: u16, log_dir: &PathBuf) -> Result<Child, BackendError> {
    let _ = std::fs::create_dir_all(log_dir);
    let mut cmd = Command::new(path);
    cmd.env("STORYLENS_APP_HOST", "127.0.0.1")
        .env("STORYLENS_APP_PORT", port.to_string())
        .env("STORYLENS_APP_ENV", "production")
        .stdout(Stdio::null())
        .stderr(Stdio::piped());

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

    Ok(child)
}

fn wait_for_health(port: u16, child: &Arc<Mutex<Child>>) -> Result<(), BackendError> {
    let url = format!("http://127.0.0.1:{port}/health");
    let deadline = Instant::now() + Duration::from_secs(60);
    let agent = ureq::AgentBuilder::new()
        .timeout_connect(Duration::from_secs(2))
        .timeout(Duration::from_secs(3))
        .build();

    while Instant::now() < deadline {
        if let Ok(mut guard) = child.lock() {
            match guard.try_wait() {
                Ok(Some(status)) => {
                    return Err(BackendError {
                        user_message: "本地分析服务意外退出。请重启 StoryLens；若反复出现，请重新安装。".into(),
                        detail: format!("sidecar exited during health wait: {status}"),
                    });
                }
                Ok(None) => {}
                Err(e) => {
                    return Err(BackendError {
                        user_message: "无法确认本地分析服务状态。请重启 StoryLens。".into(),
                        detail: format!("try_wait failed: {e}"),
                    });
                }
            }
        }

        if let Ok(resp) = agent.get(&url).call() {
            if resp.status() == 200 {
                return Ok(());
            }
        }
        thread::sleep(Duration::from_millis(300));
    }

    Err(BackendError {
        user_message: "本地分析服务启动超时。请确认端口未被占用后重试。".into(),
        detail: format!("health check timeout for {url}"),
    })
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

    let port = find_free_port()?;
    let sidecar = resolve_sidecar(app)?;
    let log_dir = user_log_dir();
    let child = spawn_sidecar(&sidecar, port, &log_dir)?;
    let child = Arc::new(Mutex::new(child));

    {
        let mut guard = state.lock().map_err(|e| BackendError {
            user_message: "应用内部状态异常，请重启 StoryLens。".into(),
            detail: e.to_string(),
        })?;
        guard.child = Some(child.clone());
    }

    if let Err(err) = wait_for_health(port, &child) {
        if let Ok(mut guard) = child.lock() {
            let _ = guard.kill();
            let _ = guard.wait();
        }
        if let Ok(mut guard) = state.lock() {
            guard.child = None;
            guard.status = BackendStatus::Failed {
                user_message: err.user_message.clone(),
                detail: err.detail.clone(),
            };
        }
        return Err(err);
    }
    let api_base = format!("http://127.0.0.1:{port}");

    {
        let mut guard = state.lock().map_err(|e| BackendError {
            user_message: "应用内部状态异常，请重启 StoryLens。".into(),
            detail: e.to_string(),
        })?;
        guard.status = BackendStatus::Ready {
            api_base: api_base.clone(),
            port,
        };
    }

    let _ = app.emit("backend-ready", api_base.clone());

    // Watch unexpected exit
    let watch_app = app.clone();
    let watch_child = child.clone();
    thread::spawn(move || loop {
        thread::sleep(Duration::from_secs(2));
        let exited = match watch_child.lock() {
            Ok(mut guard) => match guard.try_wait() {
                Ok(Some(status)) => Some(format!("{status}")),
                Ok(None) => None,
                Err(e) => Some(format!("try_wait error: {e}")),
            },
            Err(e) => Some(format!("lock error: {e}")),
        };
        if let Some(detail) = exited {
            let user_message =
                "本地分析服务意外退出。请重启 StoryLens；若反复出现，请重新安装。".to_string();
            let _ = watch_app.emit("backend-error", user_message.clone());
            if let Some(state) = watch_app.try_state::<Mutex<BackendState>>() {
                if let Ok(mut guard) = state.lock() {
                    guard.status = BackendStatus::Failed {
                        user_message,
                        detail,
                    };
                    guard.child = None;
                }
            }
            break;
        }
    });

    Ok(())
}

pub fn stop_backend(state: &Mutex<BackendState>) {
    if let Ok(mut guard) = state.lock() {
        if let Some(child) = guard.child.take() {
            if let Ok(mut child_guard) = child.lock() {
                let _ = child_guard.kill();
                let _ = child_guard.wait();
            }
        }
        guard.status = BackendStatus::Stopped;
    }
}
