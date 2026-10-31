use std::sync::{Mutex, atomic::{AtomicBool, Ordering}};
use serde_json::{json, Value};
use tauri::{Manager, State};
use tauri_plugin_updater::UpdaterExt;

#[derive(Default)]
pub struct Updates { busy: AtomicBool, status: Mutex<Value> }
struct Busy<'a>(&'a AtomicBool);
impl Drop for Busy<'_> { fn drop(&mut self) { self.0.store(false, Ordering::SeqCst); } }
fn status(state: &Updates, value: Value) { *state.status.lock().unwrap() = value; }
#[tauri::command]
pub fn update_status(app: tauri::AppHandle, state: State<'_, Updates>) -> Value {
    json!({"current":app.package_info().version.to_string(),"busy":state.busy.load(Ordering::SeqCst),"status":state.status.lock().unwrap().clone()})
}
#[tauri::command]
pub async fn app_update(window: tauri::WebviewWindow, app: tauri::AppHandle, state: State<'_, Updates>, install: bool) -> Result<Value,String> {
    if window.label() != "main" { return Err("Open the main window to update the application.".into()); }
    if state.busy.swap(true, Ordering::SeqCst) { return Err("An update operation is already running".into()); }
    let _busy = Busy(&state.busy);
    status(&state, json!({"phase":"Checking for updates…"}));
    let result: Result<Value,String> = async {
        let updater=app.updater_builder().timeout(std::time::Duration::from_secs(120)).build().map_err(|e|e.to_string())?;
        let Some(update)=updater.check().await.map_err(|e|e.to_string())? else {
            return Ok(json!({"phase":"You are up to date"}));
        };
        if !install { return Ok(json!({"phase":"Update available","version":update.version,"notes":update.body})); }
        // Quiesce under the broker's scheduler lock before any task can be claimed.
        let response=crate::backend_rpc(app.clone(),app.state::<crate::Backend>(),json!({"op":"prepare_update"})).await?;
        if response["ok"]!=true { return Err(response["error"].as_str().unwrap_or("Cannot safely update").into()); }
        let mut received=0usize;
        let bytes=update.download(|chunk,total| {
            received+=chunk;
            status(&state,json!({"phase":"Downloading signed update…","received":received,"total":total}));
        },||{}).await.map_err(|e|e.to_string())?;
        status(&state,json!({"phase":"Installing verified update…"}));
        crate::usage_position::save(&app)?;
        update.install(bytes).map_err(|e|e.to_string())?;
        // Explicit cleanup: restart does not guarantee normal exit callbacks.
        let shared=app.state::<crate::Backend>().0.clone();
        tauri::async_runtime::spawn_blocking(move || { if let Ok(mut bridge)=shared.lock() { *bridge=None; } }).await.map_err(|e|e.to_string())?;
        app.restart();
    }.await;
    match result {
        Ok(value)=>{status(&state,value.clone());Ok(value)},
        Err(error)=>{
            let _=crate::backend_rpc(app.clone(),app.state::<crate::Backend>(),json!({"op":"abort_update"})).await;
            status(&state,json!({"phase":"Update failed","error":error}));Err(error)
        }
    }
}
