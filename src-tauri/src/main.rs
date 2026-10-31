#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::{io::{BufRead, BufReader, Write}, process::{Child, ChildStdin, ChildStdout, Command, Stdio}, sync::{Arc, Mutex}};
use tauri::{Manager, State};
use serde_json::Value;
mod updates;
mod usage_position;
struct Bridge { child: Child, input: Option<ChildStdin>, output: BufReader<ChildStdout> }
impl Drop for Bridge {
    fn drop(&mut self) {
        drop(self.input.take()); // EOF lets Python stop its owned agent process groups.
        for _ in 0..30 {
            if matches!(self.child.try_wait(), Ok(Some(_))) { return; }
            std::thread::sleep(std::time::Duration::from_millis(200));
        }
        let _ = self.child.kill(); let _ = self.child.wait();
    }
}
struct Backend(Arc<Mutex<Option<Bridge>>>);
fn runtime_path() -> std::ffi::OsString {
    let mut paths: Vec<std::path::PathBuf> = std::env::var_os("PATH")
        .map(|p| std::env::split_paths(&p).collect()).unwrap_or_default();
    if let Some(home) = std::env::var_os("HOME") {
        let home = std::path::PathBuf::from(home);
        for suffix in [".local/bin", ".npm-global/bin", ".volta/bin", "miniconda3/bin", "anaconda3/bin"] {
            paths.push(home.join(suffix));
        }
        if let Ok(entries) = std::fs::read_dir(home.join(".nvm/versions/node")) {
            let mut versions: Vec<_> = entries.flatten().map(|e| e.path().join("bin")).collect();
            versions.sort(); versions.reverse(); paths.extend(versions);
        }
    }
    for path in ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"] {
        paths.push(path.into());
    }
    std::env::join_paths(paths).unwrap_or_default()
}
#[tauri::command]
async fn rpc(window: tauri::WebviewWindow, app: tauri::AppHandle, backend: State<'_, Backend>, request: Value) -> Result<Value, String> {
    if window.label() != "main" && (window.label() != "usage" || request.get("op").and_then(Value::as_str) != Some("agent_status")) {
        return Err("The usage window can only read account usage.".into());
    }
    backend_rpc(app, backend, request).await
}
async fn backend_rpc(app: tauri::AppHandle, backend: State<'_, Backend>, request: Value) -> Result<Value, String> {
    // The bridge has one ordered response stream; all subprocess work happens on Python threads.
    let shared = backend.0.clone();
    tauri::async_runtime::spawn_blocking(move || {
    let mut guard = shared.lock().map_err(|_| "Backend lock poisoned")?;
    if guard.is_none() {
        let root = if cfg!(debug_assertions) { std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../backend") }
            else { app.path().resource_dir().map_err(|e| e.to_string())?.join("backend") };
        let cache = app.path().app_cache_dir().map_err(|e| e.to_string())?;
        std::fs::create_dir_all(&cache).map_err(|e| e.to_string())?;
        let mut command = if cfg!(debug_assertions) {
            let python = std::env::var("ACC_PYTHON").unwrap_or_else(|_| if cfg!(windows) {"python"} else {"python3"}.into());
            let mut cmd = Command::new(python);
            cmd.arg("-u").arg(root.join("bridge.py")); cmd
        } else {
            let resource = app.path().resource_dir().map_err(|e| e.to_string())?;
            Command::new(resource.join("runtime/acc-backend/acc-backend"))
        };
        let mut child = command.arg("--cache").arg(cache).env("PATH", runtime_path())
            .env_remove("PYTHONHOME").env_remove("PYTHONPATH")
            .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::inherit()).spawn()
            .map_err(|e| format!("Application backend could not start: {e}. Reinstall the complete application bundle."))?;
        let input = child.stdin.take().ok_or("Missing stdin")?;
        let output = BufReader::new(child.stdout.take().ok_or("Missing stdout")?);
        *guard = Some(Bridge {child, input: Some(input), output});
    }
    let bridge = guard.as_mut().unwrap();
    let input = bridge.input.as_mut().ok_or("Bridge is stopping")?;
    writeln!(input, "{}", request).map_err(|e| e.to_string())?;
    input.flush().map_err(|e| e.to_string())?;
    let mut line = String::new();
    if bridge.output.read_line(&mut line).map_err(|e| e.to_string())? == 0 {
        *guard = None; return Err("Python bridge stopped; active runs need reconciliation.".into());
    }
    serde_json::from_str(&line).map_err(|e| e.to_string())
    }).await.map_err(|e| e.to_string())?
}
#[tauri::command]
fn fit_usage(window: tauri::WebviewWindow, height: f64, width: Option<f64>, zoom: Option<f64>) -> Result<f64, String> {
    if window.label() != "usage" || !height.is_finite() || !(40.0..=20000.0).contains(&height) {
        return Err("Invalid usage window size".into());
    }
    let width = width.unwrap_or(172.0);
    let zoom = zoom.unwrap_or(1.0);
    if !width.is_finite() || !(80.0..=400.0).contains(&width) || !zoom.is_finite() || !(0.65..=1.5).contains(&zoom) {
        return Err("Invalid usage window scale".into());
    }
    let state = window.state::<usage_position::PositionState>();
    let mut initialized = state.0.lock().map_err(|_| "Position lock poisoned")?;
    let saved = if !*initialized { usage_position::read(window.app_handle()) } else { None };
    let saved_monitor = saved.as_ref().and_then(|v| v.get("monitor")).and_then(Value::as_str);
    let matched = if !*initialized { window.available_monitors().map_err(|e|e.to_string())?.into_iter()
        .find(|m| saved_monitor.is_some() && m.name().map(String::as_str) == saved_monitor) } else { None };
    let restore = matched.is_some();
    let monitor = if !*initialized { matched.or(window.primary_monitor().map_err(|e|e.to_string())?) }
        else { window.current_monitor().map_err(|e|e.to_string())?.or(window.primary_monitor().map_err(|e|e.to_string())?) };
    let available = monitor.as_ref().map(|m| m.work_area().size.height as f64 / m.scale_factor() - 16.0).unwrap_or(800.0);
    let scale = (available / height).min(zoom);
    window.set_size(tauri::LogicalSize::new(width * scale, height * scale)).map_err(|e|e.to_string())?;
    if let Some(m) = monitor {
        let area = m.work_area();
        let size = window.outer_size().map_err(|e|e.to_string())?;
        let current = window.outer_position().map_err(|e|e.to_string())?;
        let offset = if *initialized { Some(((current.x as f64-area.position.x as f64)/m.scale_factor(), (current.y as f64-area.position.y as f64)/m.scale_factor())) }
            else if restore { saved.as_ref().and_then(|v| Some((v.get("x")?.as_f64()?,v.get("y")?.as_f64()?))) } else { None };
        let (x,y) = usage_position::coordinates((area.position.x,area.position.y),(area.size.width,area.size.height),(size.width,size.height),m.scale_factor(),offset);
        window.set_position(tauri::PhysicalPosition::new(x,y)).map_err(|e|e.to_string())?;
    }
    if !*initialized { *initialized = true; window.show().map_err(|e|e.to_string())?; }
    Ok(scale)
}
#[tauri::command]
fn usage_window(app: tauri::AppHandle, window: tauri::WebviewWindow, action: String) -> Result<(), String> {
    match action.as_str() {
        "drag" if window.label() == "usage" => window.start_dragging().map_err(|e| e.to_string()),
        "hide" => { usage_position::save(&app)?; app.get_webview_window("usage").ok_or("Usage window unavailable")?.hide().map_err(|e| e.to_string()) },
        "show" | "main" => {
            let target = if action == "show" { "usage" } else { "main" };
            let target = app.get_webview_window(target).ok_or("Window unavailable")?;
            target.show().map_err(|e| e.to_string())?;
            target.unminimize().map_err(|e| e.to_string())?;
            target.set_focus().map_err(|e| e.to_string())
        },
        _ => Err("Unknown usage window action".into()),
    }
}
fn main() {
    tauri::Builder::default().plugin(tauri_plugin_updater::Builder::new().build()).manage(usage_position::PositionState::default()).manage(updates::Updates::default()).manage(Backend(Arc::new(Mutex::new(None)))).invoke_handler(tauri::generate_handler![rpc, usage_window, fit_usage, updates::update_status, updates::app_update])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "usage" { if let Err(e) = usage_position::save(window.app_handle()) { eprintln!("Usage position: {e}"); } }
                api.prevent_close();
                let _ = window.hide(); // Closing the dashboard leaves the independent widget alive.
            }
        })
        .build(tauri::generate_context!()).expect("Unable to build Agent Control Center")
        .run(|app, event| {
            #[cfg(target_os = "macos")]
            if matches!(event, tauri::RunEvent::Reopen { .. }) {
                if let Some(main) = app.get_webview_window("main") { let _ = main.show(); let _ = main.set_focus(); }
            }
            if matches!(event, tauri::RunEvent::ExitRequested { .. }) {
                if let Err(e) = usage_position::save(app) { eprintln!("Usage position: {e}"); }
                if let Ok(mut bridge) = app.state::<Backend>().0.lock() { *bridge = None; }
            }
        });
}
