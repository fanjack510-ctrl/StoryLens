//! Updater enablement + staging/stable channel endpoints.
//! Public key stays in tauri.conf.json — never regenerate for channel isolation.

use std::fs;
use std::path::PathBuf;
use tauri::{AppHandle, Manager, Runtime};

pub const STABLE_UPDATE_ENDPOINT: &str =
    "https://github.com/fanjack510-ctrl/StoryLens/releases/latest/download/latest.json";

pub const STAGING_UPDATE_ENDPOINT: &str =
    "https://github.com/fanjack510-ctrl/StoryLens/releases/download/staging/latest.json";

pub fn updater_enabled() -> bool {
    if cfg!(debug_assertions) {
        return false;
    }
    match std::env::var("STORYLENS_DISABLE_UPDATER") {
        Ok(value) => {
            let v = value.trim().to_ascii_lowercase();
            !(v == "1" || v == "true" || v == "yes" || v == "on")
        }
        Err(_) => true,
    }
}

pub fn normalize_channel(raw: &str) -> &'static str {
    match raw.trim().to_ascii_lowercase().as_str() {
        "staging" => "staging",
        _ => "stable",
    }
}

pub fn endpoint_for_channel(channel: &str) -> &'static str {
    if normalize_channel(channel) == "staging" {
        STAGING_UPDATE_ENDPOINT
    } else {
        STABLE_UPDATE_ENDPOINT
    }
}

fn channel_config_path<R: Runtime>(app: &AppHandle<R>) -> Option<PathBuf> {
    app.path()
        .app_config_dir()
        .ok()
        .map(|dir| dir.join("updater_channel.txt"))
}

/// Resolve channel: env STORYLENS_UPDATE_CHANNEL → config file → stable.
pub fn resolve_updater_channel<R: Runtime>(app: &AppHandle<R>) -> String {
    if let Ok(env_channel) = std::env::var("STORYLENS_UPDATE_CHANNEL") {
        return normalize_channel(&env_channel).to_string();
    }
    if let Some(path) = channel_config_path(app) {
        if let Ok(text) = fs::read_to_string(&path) {
            return normalize_channel(&text).to_string();
        }
    }
    "stable".to_string()
}

pub fn write_updater_channel<R: Runtime>(
    app: &AppHandle<R>,
    channel: &str,
) -> Result<String, String> {
    let normalized = normalize_channel(channel).to_string();
    let path = channel_config_path(app).ok_or_else(|| "无法解析应用配置目录。".to_string())?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("无法创建配置目录：{e}"))?;
    }
    fs::write(&path, &normalized).map_err(|e| format!("无法写入更新通道：{e}"))?;
    Ok(normalized)
}

pub fn get_updater_channel<R: Runtime>(app: &AppHandle<R>) -> String {
    resolve_updater_channel(app)
}
