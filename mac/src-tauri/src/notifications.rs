//! A small bridge to modern macOS UserNotifications, not NSUserNotificationCenter.
use std::{
    ffi::{c_char, CStr, CString},
    sync::OnceLock,
};
use tauri::AppHandle;

static APP: OnceLock<AppHandle> = OnceLock::new();

unsafe extern "C" {
    fn swarm_notifications_init(open_agent: extern "C" fn(*const c_char));
    fn swarm_notifications_enable();
    fn swarm_notifications_send(agent: *const c_char);
    fn swarm_notifications_test();
}

extern "C" fn open_agent(name: *const c_char) {
    if name.is_null() {
        return;
    }
    // The delegate lends a NUL-terminated NSString UTF8String for this call.
    // Copy it before dispatching the Rust action to Tauri's main thread.
    let name = unsafe { CStr::from_ptr(name) }
        .to_string_lossy()
        .into_owned();
    if let Some(app) = APP.get() {
        let target = app.clone();
        if let Err(error) = app.run_on_main_thread(move || crate::app::show_agent(&target, &name)) {
            eprintln!("Buzz notifications: could not open agent: {error}");
        }
    }
}

pub fn initialize(app: AppHandle) {
    let _ = APP.set(app);
    // Called once from the native setup hook on the main thread. The bridge
    // retains its delegate and never retains a pointer into Rust-owned data.
    unsafe {
        swarm_notifications_init(open_agent);
    }
}

pub fn enable() {
    unsafe {
        swarm_notifications_enable();
    }
}

pub fn send(name: &str) {
    if let Ok(name) = CString::new(name) {
        // The bridge copies the name synchronously before scheduling work.
        unsafe {
            swarm_notifications_send(name.as_ptr());
        }
    }
}

pub fn test() {
    unsafe {
        swarm_notifications_test();
    }
}
