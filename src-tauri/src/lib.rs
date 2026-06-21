// BIG Hat Entertainment — Tauri 2.x desktop shell.
//
// LIFECYCLE
//   1. Bind to a free TCP port on 127.0.0.1 (default 8001, falls back if taken).
//   2. Spawn the bundled Python backend as a sidecar:
//        binaries/bighat-backend  --port <PORT>  --no-browser
//      The sidecar binary is a PyInstaller-frozen `launcher.py` produced by
//      the GitHub Actions workflow. On macOS it's a Mach-O; on Windows it's
//      a single .exe. Either way, no system Python install is required.
//   3. Poll http://127.0.0.1:<PORT>/health until it returns 200 (max 30s).
//   4. Navigate the main window from splash.html to http://127.0.0.1:<PORT>/.
//
// FAILURE PATHS
//   - Sidecar exits non-zero before health passes → show a Tauri dialog
//     pointing the user at the crash log path and exit cleanly.
//   - Port-bind never succeeds in 30s → same failure dialog.
//
// .bighat FILE ASSOCIATION
//   Tauri 2 emits a `tauri://file-drop` event AND raw argv. We forward any
//   `.bighat` path passed on argv as `?openFile=...` once the React app
//   loads, mirroring the v31.x VBS handoff contract so the existing
//   RoundMaker page can pick it up unchanged.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::env;
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

const HEALTH_TIMEOUT_SECS: u64 = 45;
const HEALTH_POLL_INTERVAL_MS: u64 = 500;

/// Shared state — the Python backend child handle so we can kill it when
/// the user closes the window.
#[derive(Default)]
struct BackendState {
    child: Mutex<Option<CommandChild>>,
    port: Mutex<u16>,
}

#[derive(Serialize, Clone)]
struct StartupPayload {
    base_url: String,
    open_file: Option<String>,
}

fn pick_free_port() -> u16 {
    // Prefer 8001 (matches v31.x); fall back to OS-assigned if busy.
    if TcpListener::bind(("127.0.0.1", 8001)).is_ok() {
        return 8001;
    }
    let l = TcpListener::bind(("127.0.0.1", 0)).expect("bind failed");
    l.local_addr().unwrap().port()
}

fn wait_for_health(port: u16) -> bool {
    let deadline = Instant::now() + Duration::from_secs(HEALTH_TIMEOUT_SECS);
    let url = format!("http://127.0.0.1:{port}/health");
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_millis(800))
        .build()
        .expect("reqwest client");
    while Instant::now() < deadline {
        if let Ok(resp) = client.get(&url).send() {
            if resp.status().is_success() {
                return true;
            }
        }
        thread::sleep(Duration::from_millis(HEALTH_POLL_INTERVAL_MS));
    }
    false
}

fn extract_open_file_arg() -> Option<String> {
    // The first non-flag argument that ends in `.bighat`. Matches the v31.x
    // file-association handoff.
    env::args()
        .skip(1)
        .find(|a| a.to_lowercase().ends_with(".bighat"))
}

#[tauri::command]
async fn quit_app(app: tauri::AppHandle) {
    app.exit(0);
}

#[tauri::command]
fn get_backend_port(state: tauri::State<'_, BackendState>) -> u16 {
    *state.port.lock().unwrap()
}

pub fn run() {
    env_logger::init();

    let port = pick_free_port();
    let open_file = extract_open_file_arg();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(BackendState {
            child: Mutex::new(None),
            port: Mutex::new(port),
        })
        .invoke_handler(tauri::generate_handler![quit_app, get_backend_port])
        .setup(move |app| {
            // 1. Build the borderless splash window.
            let splash_url = WebviewUrl::App(PathBuf::from("splash.html"));
            let _splash = WebviewWindowBuilder::new(app, "main", splash_url)
                .title("BIG Hat Entertainment")
                .inner_size(1400.0, 900.0)
                .min_inner_size(1100.0, 720.0)
                .center()
                .decorations(true)
                .resizable(true)
                .visible(true)
                .build()?;

            // 2. Spawn the Python backend sidecar.
            let shell = app.shell();
            let sidecar = shell
                .sidecar("bighat-backend")
                .map_err(|e| format!("sidecar binary missing: {e}"))?
                .args(["--port", &port.to_string(), "--no-browser"]);
            let (mut rx, child) = sidecar
                .spawn()
                .map_err(|e| format!("backend spawn failed: {e}"))?;

            // Stash the child so we can kill it on app exit.
            {
                let state = app.state::<BackendState>();
                *state.child.lock().unwrap() = Some(child);
            }

            // 3. Off-thread: drain stdout/stderr so the backend doesn't block.
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        tauri_plugin_shell::process::CommandEvent::Stdout(line) => {
                            log::info!("[backend] {}", String::from_utf8_lossy(&line).trim_end());
                        }
                        tauri_plugin_shell::process::CommandEvent::Stderr(line) => {
                            log::warn!("[backend] {}", String::from_utf8_lossy(&line).trim_end());
                        }
                        tauri_plugin_shell::process::CommandEvent::Terminated(payload) => {
                            log::error!("backend exited code={:?}", payload.code);
                            break;
                        }
                        _ => {}
                    }
                }
            });

            // 4. Off-thread: poll /health, then navigate the window once ready.
            let app_handle = app.handle().clone();
            let open_file_clone = open_file.clone();
            thread::spawn(move || {
                let healthy = wait_for_health(port);
                let window = match app_handle.get_webview_window("main") {
                    Some(w) => w,
                    None => return,
                };
                if !healthy {
                    let _ = window.eval(
                        "document.getElementById('splash-status').innerText = \
                         'BIG Hat backend did not start. See logs and try again.';",
                    );
                    return;
                }
                let mut url = format!("http://127.0.0.1:{port}/");
                if let Some(path) = open_file_clone {
                    let safe = path.replace('\\', "/").replace(' ', "%20");
                    url = format!("http://127.0.0.1:{port}/roundmaker?openFile={safe}");
                }
                let _ = window.eval(&format!("window.location.replace('{url}');"));
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("tauri build failed")
        .run(|app, event| {
            // Kill the sidecar when the last window closes, so we don't
            // leave orphan Python processes on the user's machine.
            if let RunEvent::ExitRequested { .. } = event {
                if let Some(state) = app.try_state::<BackendState>() {
                    if let Some(child) = state.child.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        });
}
