#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;
use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // Spawn the frozen Python API from the binaries folder
            let (mut rx, child) = app.shell().sidecar("foundry-backend")
            .expect("Failed to create sidecar command")
                .spawn()
                .expect("Failed to spawn sidecar");

            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    if let CommandEvent::Stdout(line) = event {
                        println!("[Foundry Engine]: {}", String::from_utf8_lossy(&line));
                    } else if let CommandEvent::Stderr(line) = event {
                        eprintln!("[Foundry Engine Error]: {}", String::from_utf8_lossy(&line));
                    }
                }
            });

            app.manage(std::sync::Mutex::new(Some(child)));
            Ok(())
        })
        .on_window_event(|window, event| match event {
            tauri::WindowEvent::Destroyed => {
                let app = window.app_handle();
                if let Some(child_state) = app.try_state::<std::sync::Mutex<Option<tauri_plugin_shell::process::CommandChild>>>() {
                  if let Some(child) = child_state.lock().unwrap().take() {
                      let _ = child.kill();
                  }
              }
            }
            _ => {}
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}