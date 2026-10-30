use serde_json::{Value, json};
use std::{
    ffi::{CStr, CString, c_char, c_void},
    panic::{AssertUnwindSafe, catch_unwind},
};

#[derive(Default)]
struct Engine {
    state: Value,
    buffer: Vec<u8>,
}
fn object() -> Value {
    json!({})
}
fn modes(key: &str) -> Vec<(&'static str, u8)> {
    if key == "anc" {
        vec![
            ("High", 1),
            ("Mid", 2),
            ("Low", 3),
            ("Adaptive", 4),
            ("Off", 5),
            ("Transparency", 7),
        ]
    } else {
        vec![
            ("Dirac Opteo", 0),
            ("Rock", 1),
            ("Electronic", 2),
            ("Pop", 3),
            ("Enhance vocals", 4),
            ("Classical", 5),
        ]
    }
}
fn read(key: &str) -> Result<(u16, Vec<u8>), String> {
    Ok(match key {
        "model" => (0xc01c, vec![]),
        "battery" => (0xc007, vec![]),
        "anc" => (0xc01e, vec![3]),
        "eq" => (0xc050, vec![]),
        "in_ear" => (0xc00e, vec![]),
        "low_latency" => (0xc041, vec![]),
        "spatial" => (0xc04f, vec![]),
        "bass" => (0xc04e, vec![]),
        "dual" => (0xc027, vec![]),
        "codec" => (0xc029, vec![]),
        "firmware" => (0xc042, vec![]),
        _ => return Err("Unknown read setting".into()),
    })
}
fn write(key: &str, value: &Value) -> Result<(u16, Vec<u8>), String> {
    if matches!(key, "anc" | "eq") {
        if let Some((_, id)) = modes(key)
            .into_iter()
            .find(|(name, _)| Some(*name) == value.as_str())
        {
            return Ok(if key == "anc" {
                (0xf00f, vec![1, id, 0])
            } else {
                (0xf01d, vec![id, 0])
            });
        }
    }
    if let Some(v) = value.as_bool() {
        let b = u8::from(v);
        match key {
            "spatial" => return Ok((0xf052, vec![b, 0])),
            "in_ear" => return Ok((0xf004, vec![1, 1, b])),
            "low_latency" => return Ok((0xf040, vec![if v { 1 } else { 2 }, 0])),
            "dual" => return Ok((0xf01a, vec![b])),
            _ => {}
        }
    }
    if key == "bass" && value.as_array().is_some_and(|a| a.len() == 2) {
        if let (Some(enabled), Some(level)) = (value[0].as_bool(), value[1].as_f64()) {
            if (0.0..=5.0).contains(&level) && (level * 2.0).fract() == 0.0 {
                return Ok((0xf051, vec![u8::from(enabled), (level * 2.0) as u8]));
            }
        }
    }
    if key == "codec" {
        if let Some(v) = value.as_u64().filter(|v| *v == 0 || *v == 2) {
            return Ok((0xf01c, vec![v as u8]));
        }
    }
    if key == "find" && value.as_array().is_some_and(|a| a.len() == 2) {
        if let (Some(side), Some(enabled)) = (
            value[0].as_u64().filter(|v| *v == 2 || *v == 3),
            value[1].as_bool(),
        ) {
            return Ok((0xf002, vec![side as u8, u8::from(enabled)]));
        }
    }
    Err(format!("Invalid value for {key}"))
}
fn crc(data: &[u8]) -> u16 {
    let mut value = 0xffff;
    for b in data {
        value ^= *b as u16;
        for _ in 0..8 {
            value = (value >> 1) ^ if value & 1 != 0 { 0xa001 } else { 0 }
        }
    }
    value
}
fn encode(command: u16, payload: &[u8], sequence: u8) -> Result<Vec<u8>, String> {
    if payload.len() > 4096 {
        return Err("Payload too large".into());
    }
    let len = payload.len() as u16;
    let mut out = vec![
        0x55,
        0x60,
        1,
        command as u8,
        (command >> 8) as u8,
        len as u8,
        (len >> 8) as u8,
        sequence,
    ];
    out.extend_from_slice(payload);
    let sum = crc(&out);
    out.extend_from_slice(&sum.to_le_bytes());
    Ok(out)
}
fn pairs(p: &[u8]) -> Vec<(u8, u8)> {
    if p.is_empty() || p.len() < 1 + 2 * p[0] as usize {
        return vec![];
    }
    p[1..1 + 2 * p[0] as usize]
        .chunks_exact(2)
        .map(|p| (p[0], p[1]))
        .collect()
}
fn parse(command: u16, p: &[u8]) -> Value {
    let mut out = object();
    match command {
        0xc007 | 0xe001 => {
            let mut battery = object();
            for (key, value) in pairs(p) {
                let part = match key {
                    2 => "left",
                    3 => "right",
                    4 => "case",
                    6 => "headphone",
                    _ => continue,
                };
                let level = value & 0x7f;
                battery[part] = if level <= 100 {
                    json!({"level":level,"charging":value&0x80!=0})
                } else {
                    Value::Null
                }
            }
            if !battery.as_object().unwrap().is_empty() {
                out["battery"] = battery
            }
        }
        0xc01e | 0xe003 => {
            let mut mode = 0;
            let mut strength = 0;
            for entry in p.chunks_exact(3) {
                if entry[0] == 1 {
                    mode = entry[1]
                }
                if entry[0] == 2 {
                    strength = entry[1]
                }
            }
            if (1..=4).contains(&mode) && (1..=4).contains(&strength) {
                mode = strength
            }
            if let Some((name, _)) = modes("anc").into_iter().find(|(_, id)| *id == mode) {
                out["anc"] = json!(name)
            }
        }
        0xc050 if !p.is_empty() => {
            let value = if p.len() > 1 { p[1] } else { p[0] };
            out["eq"] = json!(
                modes("eq")
                    .into_iter()
                    .find(|(_, id)| *id == value)
                    .map(|(name, _)| name.to_string())
                    .unwrap_or_else(|| format!("Device preset {value}"))
            );
        }
        0xc00e => {
            for (key, value) in pairs(p) {
                if key == 1 && value <= 1 {
                    out["in_ear"] = json!(value == 1)
                }
            }
        }
        0xc041 if !p.is_empty() && (p[0] == 1 || p[0] == 2) => {
            out["low_latency"] = json!(p[0] == 1)
        }
        0xc04f if !p.is_empty() && p[0] <= 1 => out["spatial"] = json!(p[0] == 1),
        0xc04e if p.len() >= 2 && p[0] <= 1 && p[1] <= 10 => {
            out["bass"] = json!([p[0] == 1, p[1] as f64 / 2.0])
        }
        0xc029 if !p.is_empty() && p[0] <= 2 => out["codec"] = json!(p[0]),
        0xc027 if !p.is_empty() && p[0] <= 1 => out["dual"] = json!(p[0] == 1),
        0xc042 if !p.is_empty() => {
            out["firmware"] =
                json!(String::from_utf8_lossy(p).trim_matches(['\0', '\r', '\n', ' ']))
        }
        0xc01c if !p.is_empty() => {
            out["model"] = json!(if p == [0x72, 0xb1] {
                "B172".into()
            } else if p == [0x87, 0xb1] {
                "B187".into()
            } else {
                String::from_utf8_lossy(p)
                    .trim_matches(['\0', '\r', '\n', ' '])
                    .to_uppercase()
            })
        }
        _ => {}
    }
    out
}
impl Engine {
    fn new() -> Self {
        Self {
            state: object(),
            buffer: vec![],
        }
    }
    fn apply(&mut self, command: u16, payload: &[u8]) {
        let mut update = parse(command, payload);
        if let Some(incoming) = update.get("battery").cloned() {
            let mut battery = self.state.get("battery").cloned().unwrap_or_else(object);
            for part in ["left", "right", "case", "headphone"] {
                if let Some(mut value) = incoming.get(part).filter(|v| !v.is_null()).cloned() {
                    value["available"] = json!(true);
                    battery[part] = value
                } else if incoming.get(part).is_some() || (command == 0xc007 && part == "case") {
                    if let Some(value) = battery.get_mut(part) {
                        value["available"] = json!(false)
                    }
                }
            }
            update["battery"] = battery
        }
        for (key, value) in update.as_object().unwrap() {
            self.state[key] = value.clone()
        }
    }
    fn call(&mut self, request: &Value) -> Result<Value, String> {
        let op = request["op"].as_str().unwrap_or("");
        match op {
            "reset" => {
                self.state = object();
                self.buffer.clear();
                Ok(self.state.clone())
            }
            "state" => Ok(self.state.clone()),
            "feed" => {
                self.buffer.extend(bytes(&request["bytes"])?);
                if self.buffer.len() > 65536 {
                    self.buffer.clear();
                    return Err("Packet buffer limit exceeded".into());
                }
                let mut frames = vec![];
                while !self.buffer.is_empty() {
                    if self.buffer[0] != 0x55 {
                        self.buffer.remove(0);
                        continue;
                    }
                    if self.buffer.len() < 8 {
                        break;
                    }
                    let control = u16::from_le_bytes([self.buffer[1], self.buffer[2]]);
                    let length = u16::from_le_bytes([self.buffer[5], self.buffer[6]]) as usize;
                    if length > 4096 || control & 0xff00 > 0x0100 {
                        self.buffer.remove(0);
                        continue;
                    }
                    let end = 8 + length;
                    let total = end + if control & 0x20 != 0 { 2 } else { 0 };
                    if self.buffer.len() < total {
                        break;
                    }
                    if control & 0x20 != 0
                        && crc(&self.buffer[..end])
                            != u16::from_le_bytes([self.buffer[end], self.buffer[end + 1]])
                    {
                        self.buffer.remove(0);
                        continue;
                    }
                    let command = u16::from_le_bytes([self.buffer[3], self.buffer[4]]) | 0x8000;
                    let sequence = self.buffer[7];
                    let payload = self.buffer[8..end].to_vec();
                    self.buffer.drain(..total);
                    self.apply(command, &payload);
                    frames.push(json!({"command":command,"sequence":sequence,"payload":payload}));
                }
                Ok(json!({"frames":frames,"state":self.state}))
            }
            "read" | "write" | "packet" => {
                let key = request["key"].as_str().unwrap_or("");
                let (command, payload) = match op {
                    "packet" => (
                        request["command"]
                            .as_u64()
                            .filter(|v| *v <= 65535)
                            .ok_or("Invalid command")? as u16,
                        bytes(&request["payload"])?,
                    ),
                    "read" => read(key)?,
                    _ => {
                        if !matches!(self.state["model"].as_str(), Some("B172" | "B187")) {
                            return Err("Device model is not configured for writes".into());
                        }
                        if key != "find" && self.state.get(key).is_none() {
                            return Err("The device has not reported this setting".into());
                        }
                        write(key, &request["value"])?
                    }
                };
                let sequence = request.get("sequence").and_then(Value::as_u64).unwrap_or(1);
                if !(1..=255).contains(&sequence) {
                    return Err("Invalid packet sequence".into());
                }
                Ok(json!({"command":command,"bytes":encode(command,&payload,sequence as u8)?}))
            }
            _ => Err("Unknown engine operation".into()),
        }
    }
}
fn bytes(value: &Value) -> Result<Vec<u8>, String> {
    if value.is_null() {
        return Ok(vec![]);
    }
    value
        .as_array()
        .ok_or_else(|| "Invalid packet bytes".to_string())?
        .iter()
        .map(|v| {
            v.as_u64()
                .filter(|n| *n <= 255)
                .map(|n| n as u8)
                .ok_or_else(|| "Invalid packet bytes".to_string())
        })
        .collect()
}
#[unsafe(no_mangle)]
pub extern "C" fn nx_engine_create() -> *mut c_void {
    Box::into_raw(Box::new(Engine::new())).cast()
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn nx_engine_destroy(context: *mut c_void) {
    if !context.is_null() {
        drop(unsafe { Box::from_raw(context.cast::<Engine>()) })
    }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn nx_engine_free(text: *mut c_char) {
    if !text.is_null() {
        drop(unsafe { CString::from_raw(text) })
    }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn nx_engine_call(context: *mut c_void, input: *const c_char) -> *mut c_char {
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<Value, String> {
        if context.is_null() || input.is_null() {
            return Err("Invalid engine context".into());
        }
        let text = unsafe { CStr::from_ptr(input) }
            .to_str()
            .map_err(|_| "Invalid UTF-8 request")?;
        let request = serde_json::from_str(text).map_err(|_| "Invalid JSON request")?;
        unsafe { &mut *context.cast::<Engine>() }.call(&request)
    }));
    let response = match result {
        Ok(Ok(value)) => json!({"ok":true,"result":value}),
        Ok(Err(error)) => json!({"ok":false,"error":error}),
        Err(_) => json!({"ok":false,"error":"Native engine failure"}),
    };
    CString::new(response.to_string())
        .map(CString::into_raw)
        .unwrap_or(std::ptr::null_mut())
}
