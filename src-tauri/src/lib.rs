// BIG Hat Entertainment — Tauri 2.x desktop shell.
//
// v32.0.0-alpha.2 — adds:
//   • File log at  %LOCALAPPDATA%\BIGHat\tauri-shell.log  (Win)
//                  ~/Library/Logs/BIGHat/tauri-shell.log   (mac)
//     Every important step (sidecar spawn, health-poll result, navigate,
//     exit) writes a timestamped line so customer-side debugging works
//     without me physically having their machine.
//   • Modal error dialog (`rfd`) if the sidecar fails to spawn — replaces
//     the previous "silent black void" behaviour.
//   • Splash status messages updated via window.eval so the user sees
//     "starting Python backend…", "backend ready", etc. instead of a
//     spinner with no context.
//
// LIFECYCLE
//   1. Bind to a free TCP port on 127.0.0.1 (default 8001).
//   2. Spawn the bundled `bighat-backend` sidecar with --port + --no-browser.
//   3. Poll http://127.0.0.1:<PORT>/health until 200 (max 60s).
//   4. Navigate the main window from splash.html to http://127.0.0.1:<PORT>/.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::env;
use std::fs;
use std::io::Write;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::{Manager, RunEvent};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

const HEALTH_TIMEOUT_SECS: u64 = 60;
const HEALTH_POLL_INTERVAL_MS: u64 = 500;

#[derive(Default)]
struct BackendState {
    child: Mutex<Option<CommandChild>>,
    port: Mutex<u16>,
}

// --- File logging -----------------------------------------------------------

fn log_dir() -> PathBuf {
    if cfg!(target_os = "windows") {
        if let Ok(p) = env::var("LOCALAPPDATA") {
            return PathBuf::from(p).join("BIGHat");
        }
    }
    if cfg!(target_os = "macos") {
        if let Ok(home) = env::var("HOME") {
            return PathBuf::from(home).join("Library/Logs/BIGHat");
        }
    }
    env::temp_dir().join("BIGHat")
}

fn log_path() -> PathBuf {
    log_dir().join("tauri-shell.log")
}

fn log_line(level: &str, msg: impl AsRef<str>) {
    let line = format!(
        "[{}] {} {}\n",
        chrono_now(),
        level,
        msg.as_ref()
    );
    let _ = fs::create_dir_all(log_dir());
    if let Ok(mut f) = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_path())
    {
        let _ = f.write_all(line.as_bytes());
    }
    eprintln!("{}", line.trim_end());
}

// minimal ISO-ish timestamp without pulling chrono
fn chrono_now() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    // year/month/day approximation — for debugging purposes only.
    // Avoids a `chrono` dependency for this single line.
    format!("epoch:{secs}")
}

// --- Port + health -----------------------------------------------------------

fn pick_free_port() -> u16 {
    if TcpListener::bind(("127.0.0.1", 8001)).is_ok() {
        return 8001;
    }
    let l = TcpListener::bind(("127.0.0.1", 0)).expect("bind failed");
    l.local_addr().unwrap().port()
}

fn wait_for_health(port: u16, status_cb: impl Fn(&str)) -> bool {
    let deadline = Instant::now() + Duration::from_secs(HEALTH_TIMEOUT_SECS);
    let url = format!("http://127.0.0.1:{port}/health");
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_millis(800))
        .build()
        .expect("reqwest client");
    let mut attempt = 0u32;
    while Instant::now() < deadline {
        attempt += 1;
        match client.get(&url).send() {
            Ok(resp) if resp.status().is_success() => {
                log_line("info", format!("health OK after {attempt} attempts"));
                return true;
            }
            Ok(resp) => {
                log_line(
                    "warn",
                    format!("health returned {} (attempt {attempt})", resp.status()),
                );
                status_cb(&format!(
                    "Backend booting… ({})",
                    resp.status().as_u16()
                ));
            }
            Err(e) => {
                if attempt == 1 || attempt % 6 == 0 {
                    log_line("warn", format!("health connect error attempt={attempt}: {e}"));
                }
                status_cb("Waiting for the backend to start…");
            }
        }
        thread::sleep(Duration::from_millis(HEALTH_POLL_INTERVAL_MS));
    }
    log_line("error", format!("health never reached 200 after {attempt} attempts"));
    false
}

fn extract_open_file_arg() -> Option<String> {
    env::args()
        .skip(1)
        .find(|a| a.to_lowercase().ends_with(".bighat"))
}

// --- Tauri commands ----------------------------------------------------------

#[tauri::command]
async fn quit_app(app: tauri::AppHandle) {
    log_line("info", "quit_app invoked");
    app.exit(0);
}

#[tauri::command]
fn get_backend_port(state: tauri::State<'_, BackendState>) -> u16 {
    *state.port.lock().unwrap()
}

#[tauri::command]
fn get_log_path() -> String {
    log_path().to_string_lossy().to_string()
}

// --- App entry ---------------------------------------------------------------

pub fn run() {
    let _ = fs::create_dir_all(log_dir());
    log_line("info", format!("=== BIG Hat shell start, args={:?} ===", env::args().collect::<Vec<_>>()));
    log_line("info", format!("exe={:?}", env::current_exe()));
    log_line("info", format!("cwd={:?}", env::current_dir()));

    let port = pick_free_port();
    let open_file = extract_open_file_arg();
    log_line("info", format!("chose port={port}, open_file={open_file:?}"));

    // Surface any Tauri-side panic into the log. Without this, panics
    // from plugin init / generate_context! / capability validation kill
    // the windows-subsystem process silently — exactly what bit us in
    // alpha.1 and alpha.2 first launches.
    std::panic::set_hook(Box::new(|info| {
        log_line("panic", format!("{info}"));
    }));

    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        run_inner(port, open_file)
    }));
    if let Err(panic_payload) = result {
        let msg = if let Some(s) = panic_payload.downcast_ref::<&str>() {
            (*s).to_string()
        } else if let Some(s) = panic_payload.downcast_ref::<String>() {
            s.clone()
        } else {
            "<non-string panic payload>".to_string()
        };
        log_line("fatal", format!("run_inner panicked: {msg}"));
    }
    log_line("info", "=== BIG Hat shell exit ===");
}

fn run_inner(port: u16, open_file: Option<String>) {
    log_line("info", "creating tauri::Builder");
    let builder = tauri::Builder::default();
    log_line("info", "+ plugin: shell");
    let builder = builder.plugin(tauri_plugin_shell::init());
    log_line("info", "+ plugin: process");
    let builder = builder.plugin(tauri_plugin_process::init());
    log_line("info", "+ plugin: dialog");
    let builder = builder.plugin(tauri_plugin_dialog::init());
    log_line("info", "+ state managed");
    let builder = builder.manage(BackendState {
        child: Mutex::new(None),
        port: Mutex::new(port),
    });
    log_line("info", "+ invoke_handler wired");
    let builder = builder.invoke_handler(tauri::generate_handler![
        quit_app,
        get_backend_port,
        get_log_path
    ]);

    log_line("info", "registering setup() callback");
    let builder = builder.setup(move |app| {
            log_line("info", "tauri setup() entered");

            // The window is declared in tauri.conf.json (label="main"). Just
            // fetch it — DON'T re-create it, that panics with
            // "a webview with label `main` already exists" (see alpha.4 log).
            let window = app.get_webview_window("main").ok_or_else(|| {
                log_line("fatal", "main window not found (tauri.conf.json windows[] missing?)");
                std::io::Error::new(std::io::ErrorKind::Other, "main window missing")
            })?;
            log_line("info", "main window resolved ok");

            // 2. Spawn the Python backend sidecar.
            let shell = app.shell();
            let sidecar_result = shell
                .sidecar("bighat-backend")
                .map(|cmd| cmd.args(["--port", &port.to_string(), "--no-browser"]))
                .and_then(|cmd| cmd.spawn());

            let (mut rx, child) = match sidecar_result {
                Ok(pair) => pair,
                Err(e) => {
                    log_line("fatal", format!("sidecar spawn failed: {e}"));
                    let log = log_path().to_string_lossy().to_string();
                    app.dialog()
                        .message(format!(
                            "BIG Hat couldn't start its backend.\n\nError: {e}\n\nLog file:\n{log}\n\nThe app will now close.",
                        ))
                        .kind(MessageDialogKind::Error)
                        .title("BIG Hat — backend failed to start")
                        .buttons(MessageDialogButtons::Ok)
                        .blocking_show();
                    app.handle().exit(1);
                    return Err(Box::new(std::io::Error::new(
                        std::io::ErrorKind::Other,
                        format!("sidecar spawn failed: {e}"),
                    )) as Box<dyn std::error::Error>);
                }
            };
            log_line("info", "sidecar spawned ok");

            // Stash the child so we kill it on app exit.
            {
                let state = app.state::<BackendState>();
                *state.child.lock().unwrap() = Some(child);
            }

            // 3. Drain sidecar stdout/stderr to the log.
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        tauri_plugin_shell::process::CommandEvent::Stdout(line) => {
                            log_line(
                                "py-out",
                                String::from_utf8_lossy(&line).trim_end(),
                            );
                        }
                        tauri_plugin_shell::process::CommandEvent::Stderr(line) => {
                            log_line(
                                "py-err",
                                String::from_utf8_lossy(&line).trim_end(),
                            );
                        }
                        tauri_plugin_shell::process::CommandEvent::Terminated(payload) => {
                            log_line(
                                "warn",
                                format!("sidecar terminated code={:?}", payload.code),
                            );
                            break;
                        }
                        _ => {}
                    }
                }
            });

            // 4. Off-thread: poll /health, then navigate.
            let app_handle = app.handle().clone();
            let window_for_thread = window.clone();
            let open_file_clone = open_file.clone();
            thread::spawn(move || {
                let healthy = wait_for_health(port, |msg| {
                    let safe = msg.replace('\'', "\\'");
                    let _ = window_for_thread.eval(&format!(
                        "var el=document.getElementById('splash-status'); if(el) el.innerText='{safe}';"
                    ));
                });
                if !healthy {
                    log_line("fatal", "backend never responded — showing dialog");
                    let log = log_path().to_string_lossy().to_string();
                    app_handle
                        .dialog()
                        .message(format!(
                            "BIG Hat's backend started but never responded.\n\nThis usually means a Windows security tool is blocking localhost connections, or the embedded Python tree was corrupted on install.\n\nLog file:\n{log}",
                        ))
                        .kind(MessageDialogKind::Error)
                        .title("BIG Hat — backend not responding")
                        .buttons(MessageDialogButtons::Ok)
                        .blocking_show();
                    app_handle.exit(1);
                    return;
                }
                let mut url = format!("http://127.0.0.1:{port}/");
                if let Some(path) = open_file_clone {
                    let safe = path.replace('\\', "/").replace(' ', "%20");
                    url = format!("http://127.0.0.1:{port}/roundmaker?openFile={safe}");
                }
                log_line("info", format!("navigating to {url}"));
                let _ = window_for_thread
                    .eval(&format!("window.location.replace('{url}');"));
            });

            Ok(())
        });

    log_line("info", "calling Builder::build() (generate_context + capability validation)");
    let app = match builder.build(tauri::generate_context!()) {
        Ok(app) => {
            log_line("info", "Builder::build() OK");
            app
        }
        Err(e) => {
            log_line("fatal", format!("Builder::build() failed: {e}"));
            return;
        }
    };

    log_line("info", "entering event loop (App::run)");
    app.run(|app, event| {
        if let RunEvent::ExitRequested { .. } = event {
            log_line("info", "ExitRequested — killing sidecar");
            if let Some(state) = app.try_state::<BackendState>() {
                if let Some(child) = state.child.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        }
    });
}

// Silence unused warnings if cross-compiling without the Path import.
#[allow(dead_code)]
fn _unused_path_marker(_: &Path) {}
