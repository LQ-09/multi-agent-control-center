#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::{io::{BufRead, BufReader, Write}, process::{Child, ChildStdin, ChildStdout, Command, Stdio}, sync::{Arc, Mutex}};
use tauri::{Manager, State};
use serde_json::Value;
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
async fn rpc(app: tauri::AppHandle, backend: State<'_, Backend>, request: Value) -> Result<Value, String> {
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
fn main() {
    tauri::Builder::default().manage(Backend(Arc::new(Mutex::new(None)))).invoke_handler(tauri::generate_handler![rpc])
        .build(tauri::generate_context!()).expect("Unable to build Agent Control Center")
        .run(|app, event| {
            if matches!(event, tauri::RunEvent::ExitRequested { .. }) {
                if let Ok(mut bridge) = app.state::<Backend>().0.lock() { *bridge = None; }
            }
        });
}
