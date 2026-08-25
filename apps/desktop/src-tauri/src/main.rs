#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;
mod updater_support;
#[cfg(windows)]
mod win_lifecycle;

use backend::{BackendState, BackendStatus};
use serde::Serialize;
#[cfg(windows)]
use std::ffi::OsStr;
use std::fs::{self, OpenOptions};
use std::io::Write;
#[cfg(windows)]
use std::os::windows::ffi::OsStrExt;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager, Runtime, State, Webview};
use tauri_plugin_updater::UpdaterExt;

#[tauri::command]
fn get_api_base(state: State<'_, Mutex<BackendState>>) -> Result<String, String> {
    let guard = state.lock().map_err(|e| e.to_string())?;
    match &guard.status {
        BackendStatus::Ready { api_base, .. } => Ok(api_base.clone()),
        BackendStatus::Failed { user_message, .. } => Err(user_message.clone()),
        BackendStatus::Starting => Err("本地服务正在启动，请稍候…".into()),
        BackendStatus::Stopped => Err("本地服务尚未启动。".into()),
    }
}

#[tauri::command]
fn get_backend_status(state: State<'_, Mutex<BackendState>>) -> Result<BackendStatus, String> {
    let guard = state.lock().map_err(|e| e.to_string())?;
    Ok(guard.status.clone())
}

#[tauri::command]
fn get_app_version(app: AppHandle) -> String {
    app.package_info().version.to_string()
}

const MAX_DOWNLOAD_BYTES: usize = 64 * 1024 * 1024;

fn safe_download_filename(filename: &str) -> String {
    let basename = Path::new(filename.trim())
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("StoryLens-export.pdf");
    let mut cleaned: String = basename
        .chars()
        .map(|ch| {
            if ch.is_control() || matches!(ch, '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*')
            {
                '_'
            } else {
                ch
            }
        })
        .take(180)
        .collect();
    cleaned = cleaned.trim_matches([' ', '.']).to_string();
    if cleaned.is_empty() {
        return "StoryLens-export.pdf".into();
    }

    let stem = Path::new(&cleaned)
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_ascii_uppercase();
    let reserved = matches!(
        stem.as_str(),
        "CON"
            | "PRN"
            | "AUX"
            | "NUL"
            | "COM1"
            | "COM2"
            | "COM3"
            | "COM4"
            | "COM5"
            | "COM6"
            | "COM7"
            | "COM8"
            | "COM9"
            | "LPT1"
            | "LPT2"
            | "LPT3"
            | "LPT4"
            | "LPT5"
            | "LPT6"
            | "LPT7"
            | "LPT8"
            | "LPT9"
    );
    if reserved {
        cleaned.insert(0, '_');
    }
    cleaned
}

fn numbered_download_path(directory: &Path, filename: &str, index: usize) -> PathBuf {
    if index == 0 {
        return directory.join(filename);
    }
    let path = Path::new(filename);
    let stem = path
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("StoryLens-export");
    match path.extension().and_then(|value| value.to_str()) {
        Some(extension) if !extension.is_empty() => {
            directory.join(format!("{stem} ({index}).{extension}"))
        }
        _ => directory.join(format!("{stem} ({index})")),
    }
}

/// Persist a generated export through the desktop shell. WebView download anchors are not
/// reliable in installed Tauri builds, so the UI sends the already-rendered bytes here and gets
/// the exact final path back for a visible success message.
#[tauri::command]
fn save_download_file(app: AppHandle, filename: String, bytes: Vec<u8>) -> Result<String, String> {
    if bytes.is_empty() {
        return Err("导出文件为空，未保存。".into());
    }
    if bytes.len() > MAX_DOWNLOAD_BYTES {
        return Err("导出文件超过 64 MB，未保存。".into());
    }

    let directory = app
        .path()
        .download_dir()
        .map_err(|error| format!("无法定位系统下载目录：{error}"))?;
    fs::create_dir_all(&directory).map_err(|error| format!("无法创建下载目录：{error}"))?;
    let filename = safe_download_filename(&filename);

    for index in 0..10_000 {
        let target = numbered_download_path(&directory, &filename, index);
        match OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&target)
        {
            Ok(mut file) => {
                if let Err(error) = file.write_all(&bytes).and_then(|_| file.flush()) {
                    drop(file);
                    let _ = fs::remove_file(&target);
                    return Err(format!("保存导出文件失败：{error}"));
                }
                return Ok(target.to_string_lossy().into_owned());
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(format!("无法写入下载目录：{error}")),
        }
    }
    Err("下载目录中同名文件过多，请整理后重试。".into())
}

#[cfg(windows)]
#[tauri::command]
fn open_external_https_url(url: String) -> Result<(), String> {
    use windows_sys::Win32::UI::Shell::ShellExecuteW;

    let parsed = url::Url::parse(url.trim()).map_err(|_| "购买地址无效。".to_string())?;
    let host = parsed
        .host_str()
        .map(str::to_ascii_lowercase)
        .ok_or_else(|| "购买地址无效。".to_string())?;
    if parsed.scheme() != "https"
        || host == "localhost"
        || host == "127.0.0.1"
        || host == "::1"
        || host.ends_with(".localhost")
    {
        return Err("购买地址无效。".into());
    }

    let verb: Vec<u16> = OsStr::new("open").encode_wide().chain(Some(0)).collect();
    let target: Vec<u16> = OsStr::new(parsed.as_str())
        .encode_wide()
        .chain(Some(0))
        .collect();
    let result = unsafe {
        ShellExecuteW(
            std::ptr::null_mut(),
            verb.as_ptr(),
            target.as_ptr(),
            std::ptr::null(),
            std::ptr::null(),
            1,
        )
    };
    if result as isize <= 32 {
        return Err("系统浏览器未能打开购买页面。".into());
    }
    Ok(())
}

#[cfg(not(windows))]
#[tauri::command]
fn open_external_https_url(_url: String) -> Result<(), String> {
    Err("当前系统暂不支持打开外部页面。".into())
}

#[tauri::command]
fn updater_enabled() -> bool {
    updater_support::updater_enabled()
}

#[tauri::command]
fn get_updater_channel(app: AppHandle) -> String {
    updater_support::get_updater_channel(&app)
}

#[tauri::command]
fn set_updater_channel(app: AppHandle, channel: String) -> Result<String, String> {
    updater_support::write_updater_channel(&app, &channel)
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct StorylensUpdateMetadata {
    rid: tauri::ResourceId,
    current_version: String,
    version: String,
    date: Option<String>,
    body: Option<String>,
    raw_json: serde_json::Value,
}

/// Channel-aware update check. Does not download or install.
#[tauri::command]
async fn storylens_updater_check<R: Runtime>(
    app: AppHandle<R>,
    webview: Webview<R>,
    channel: Option<String>,
) -> Result<Option<StorylensUpdateMetadata>, String> {
    if !updater_support::updater_enabled() {
        return Err("更新检查未启用。".into());
    }

    let resolved = match channel.as_deref() {
        Some(raw) => updater_support::normalize_channel(raw).to_string(),
        None => updater_support::resolve_updater_channel(&app),
    };
    let endpoint = updater_support::endpoint_for_channel(&resolved);
    let url = url::Url::parse(endpoint).map_err(|e| format!("更新地址无效：{e}"))?;

    let updater = app
        .updater_builder()
        .endpoints(vec![url])
        .map_err(|e| e.to_string())?
        .build()
        .map_err(|e| e.to_string())?;

    let update = updater.check().await.map_err(|e| e.to_string())?;
    let Some(update) = update else {
        return Ok(None);
    };

    let formatted_date = update.date.and_then(|date| {
        date.format(&time::format_description::well_known::Rfc3339)
            .ok()
    });

    Ok(Some(StorylensUpdateMetadata {
        current_version: update.current_version.clone(),
        version: update.version.clone(),
        date: formatted_date,
        body: update.body.clone(),
        raw_json: update.raw_json.clone(),
        rid: webview.resources_table().add(update),
    }))
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_process::init())
        .setup(|app| {
            if updater_support::updater_enabled() {
                app.handle()
                    .plugin(tauri_plugin_updater::Builder::new().build())?;
            }

            let state = Mutex::new(BackendState::default());
            app.manage(state);

            let handle = app.handle().clone();
            std::thread::spawn(move || {
                if let Err(err) = backend::start_backend(&handle) {
                    let _ = handle.emit("backend-error", err.user_message.clone());
                    if let Some(state) = handle.try_state::<Mutex<BackendState>>() {
                        if let Ok(mut guard) = state.lock() {
                            // Failed start must not leave orphan processes.
                            if let Some(life) = guard.lifecycle.take() {
                                backend::stop_lifecycle(life);
                            }
                            guard.status = BackendStatus::Failed {
                                user_message: err.user_message,
                                detail: err.detail,
                            };
                        }
                    }
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                if let Some(state) = window.app_handle().try_state::<Mutex<BackendState>>() {
                    backend::stop_backend(&state);
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_api_base,
            get_backend_status,
            get_app_version,
            save_download_file,
            open_external_https_url,
            updater_enabled,
            get_updater_channel,
            set_updater_channel,
            storylens_updater_check
        ])
        .build(tauri::generate_context!())
        .expect("StoryLens failed to start");

    app.run(|app_handle, event| match event {
        tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit => {
            if let Some(state) = app_handle.try_state::<Mutex<BackendState>>() {
                backend::stop_backend(&state);
            }
        }
        _ => {}
    });
}
