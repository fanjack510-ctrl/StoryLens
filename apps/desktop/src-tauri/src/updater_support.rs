//! Updater is enabled for packaged release builds unless explicitly disabled.

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
