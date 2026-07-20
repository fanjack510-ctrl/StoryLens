#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;
mod updater_support;
#[cfg(windows)]
mod win_lifecycle;

use backend::{BackendState, BackendStatus};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager, RunEvent, State};

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
            updater_enabled
        ])
        .build(tauri::generate_context!())
        .expect("StoryLens failed to start");

    app.run(|app_handle, event| match event {
        RunEvent::ExitRequested { .. } | RunEvent::Exit => {
            if let Some(state) = app_handle.try_state::<Mutex<BackendState>>() {
                backend::stop_backend(&state);
            }
        }
        _ => {}
    });
}
