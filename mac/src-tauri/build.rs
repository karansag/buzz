fn main() {
    #[cfg(feature = "desktop")]
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos") {
        println!("cargo:rerun-if-changed=native/notifications.m");
        cc::Build::new()
            .file("native/notifications.m")
            .flag("-fobjc-arc")
            .flag("-fblocks")
            .compile("swarm_notifications");
        for framework in ["Foundation", "AppKit", "UserNotifications"] {
            println!("cargo:rustc-link-lib=framework={framework}");
        }
    }
    #[cfg(feature = "desktop")]
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "attention",
            "agent_notification",
            "setup_info",
            "save_hub",
            "open_dashboard",
        ]),
    ))
    .expect("could not build Tauri app metadata");
}
