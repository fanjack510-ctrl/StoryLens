#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;
mod updater_support;
#[cfg(windows)]
mod win_lifecycle;

use backend::{BackendState, BackendStatus};
use serde::Serialize;
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
