//! Persist the accessory position independently of its content-driven size.
use serde_json::{json, Value};
use std::sync::Mutex;
use tauri::Manager;

#[derive(Default)]
pub struct PositionState(pub Mutex<bool>);

fn path(app: &tauri::AppHandle) -> Result<std::path::PathBuf, String> {
    Ok(app.path().app_config_dir().map_err(|e| e.to_string())?.join("usage-position.json"))
}
pub fn read(app: &tauri::AppHandle) -> Option<Value> {
    serde_json::from_slice(&std::fs::read(path(app).ok()?).ok()?).ok()
}
pub fn save(app: &tauri::AppHandle) -> Result<(), String> {
    if !*app.state::<PositionState>().0.lock().map_err(|_| "Position lock poisoned")? { return Ok(()); }
    let window = app.get_webview_window("usage").ok_or("Usage window unavailable")?;
    let Some(monitor) = window.current_monitor().map_err(|e| e.to_string())? else { return Ok(()); };
    let pos = window.outer_position().map_err(|e| e.to_string())?;
    let area = monitor.work_area();
    let value = json!({"monitor":monitor.name(),
        "x":(pos.x as f64-area.position.x as f64)/monitor.scale_factor(),
        "y":(pos.y as f64-area.position.y as f64)/monitor.scale_factor()});
    let dest = path(app)?;
    std::fs::create_dir_all(dest.parent().ok_or("Missing position directory")?).map_err(|e| e.to_string())?;
    let temp = dest.with_extension("tmp");
    std::fs::write(&temp, value.to_string()).map_err(|e| e.to_string())?;
    std::fs::rename(temp, dest).map_err(|e| e.to_string())
}

pub fn coordinates(origin: (i32,i32), area: (u32,u32), size: (u32,u32), scale: f64, saved: Option<(f64,f64)>) -> (i32,i32) {
    let offset = saved.filter(|(x,y)| x.is_finite() && y.is_finite())
        .unwrap_or((8.0, ((area.1.saturating_sub(size.1)) as f64 / scale / 2.0).max(8.0)));
    let clamp = |start: i32, length: u32, item: u32, offset: f64| {
        (start as f64 + offset * scale).clamp(start as f64, start as f64 + length.saturating_sub(item) as f64).round() as i32
    };
    (clamp(origin.0,area.0,size.0,offset.0),clamp(origin.1,area.1,size.1,offset.1))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn first_launch_is_left_and_vertically_centered() {
        assert_eq!(coordinates((0,40),(2880,1760),(240,400),2.0,None),(16,720));
    }
    #[test] fn restore_uses_monitor_relative_logical_coordinates() {
        assert_eq!(coordinates((-1920,0),(1920,1080),(120,300),1.0,Some((8.0,100.0))),(-1912,100));
        assert_eq!(coordinates((0,40),(2880,1760),(240,600),2.0,Some((8.0,100.0))),(16,240));
    }
    #[test] fn changed_screen_and_oversized_content_stay_visible() {
        assert_eq!(coordinates((0,20),(1000,700),(120,300),1.0,Some((3000.0,-99.0))),(880,20));
        assert_eq!(coordinates((0,20),(100,100),(120,300),1.0,Some((8.0,100.0))),(0,20));
    }
    #[test] fn invalid_saved_position_uses_left_default() {
        assert_eq!(coordinates((0,0),(1000,700),(120,300),1.0,Some((f64::NAN,0.0))),(8,200));
    }
}
