use cosmic::{
    Element, Task,
    applet::cosmic_panel_config::PanelAnchor,
    iced::{Alignment, Length, Limits, Subscription, futures, window::Id},
    widget::{self, button, column, container, icon, row, scrollable, space, text},
};
use futures::SinkExt;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, HashSet},
    path::PathBuf,
    process::Stdio,
};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    sync::mpsc,
};

#[cfg(not(feature = "rust-backend"))]
const APP_ID: &str = "io.github.basanta_bhandari.NothingXApplet.Cpp";
#[cfg(feature = "rust-backend")]
const APP_ID: &str = "io.github.basanta_bhandari.NothingXApplet.Rust";
const BACKEND: &str = if cfg!(feature = "rust-backend") {
    "rust"
} else {
    "cpp"
};

#[derive(Debug, Clone)]
enum Message {
    TogglePopup,
    PopupClosed(Id),
    BridgeReady(mpsc::UnboundedSender<String>),
    BridgeEvent(Value),
    BridgeError(String),
    Action(&'static str),
    Set(&'static str, Value),
    Audio(&'static str, Value, Option<String>),
    Tab(bool),
    Theme(String),
    Surface(cosmic::surface::Action<Message>),
    OpenFull,
    FullClosed,
    FullFailed(String),
}

struct Applet {
    core: cosmic::Core,
    popup: Option<Id>,
    sender: Option<mpsc::UnboundedSender<String>>,
    state: Value,
    audio: Value,
    phase: String,
    detail: String,
    pending: HashSet<String>,
    requested: BTreeMap<String, Value>,
    audio_tab: bool,
    opening_full: bool,
}

fn project_dir() -> PathBuf {
    std::env::var_os("NOTHINGX_APP_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            let data = std::env::var_os("XDG_DATA_HOME")
                .map(PathBuf::from)
                .unwrap_or_else(|| {
                    PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join(".local/share")
                });
            data.join(format!("nothingx-{BACKEND}-applet"))
        })
}
fn preferences_path() -> PathBuf {
    std::env::var_os("NOTHINGX_PREFERENCES")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            std::env::var_os("XDG_CONFIG_HOME")
                .map(PathBuf::from)
                .unwrap_or_else(|| {
                    PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join(".config")
                })
                .join("nothingx/preferences.json")
        })
}
fn theme_colors() -> [cosmic::iced::Color; 5] {
    let config = preferences_path();
    let preferences: Value = std::fs::read(config)
        .ok()
        .and_then(|data| serde_json::from_slice(&data).ok())
        .unwrap_or_else(|| json!({}));
    let registry: Value = std::fs::read(project_dir().join("nothingx/assets/themes/themes.json"))
        .ok()
        .and_then(|data| serde_json::from_slice(&data).ok())
        .unwrap_or_else(|| json!({}));
    let key = preferences["theme"].as_str().unwrap_or("nothing");
    let chosen = registry["themes"].as_array().and_then(|themes| {
        themes
            .iter()
            .find(|theme| theme["id"].as_str() == Some(key))
    });
    let color = |field: &str, fallback: u32| {
        let rgb = chosen
            .and_then(|theme| theme[field].as_str())
            .and_then(|text| u32::from_str_radix(text.trim_start_matches('#'), 16).ok())
            .unwrap_or(fallback);
        cosmic::iced::Color::from_rgb8((rgb >> 16) as u8, (rgb >> 8) as u8, rgb as u8)
    };
    [
        color("panel", 0x171717),
        color("text", 0xf0efed),
        color("accent", 0xff343b),
        color("card", 0x242424),
        color("ink", 0x090909),
    ]
}

fn themed_button(selected: bool) -> cosmic::theme::Button {
    let [_, foreground, accent, card, ink] = theme_colors();
    let style = move |disabled: bool, hover: bool| cosmic::widget::button::Style {
        background: Some(if selected { accent } else { card }.into()),
        text_color: Some(if selected { ink } else { foreground }),
        border_radius: 22.0.into(),
        border_width: if hover { 1.5 } else { 0.5 },
        border_color: if hover {
            accent
        } else {
            foreground.scale_alpha(0.25)
        },
        overlay: if disabled {
            Some(card.scale_alpha(0.6).into())
        } else {
            None
        },
        ..Default::default()
    };
    cosmic::theme::Button::Custom {
        active: Box::new(move |_, _| style(false, false)),
        disabled: Box::new(move |_| style(true, false)),
        hovered: Box::new(move |_, _| style(false, true)),
        pressed: Box::new(move |_, _| style(false, true)),
    }
}

fn bridge_subscription() -> Subscription<Message> {
    Subscription::run(|| {
        cosmic::iced::stream::channel(
            64,
            |mut output: futures::channel::mpsc::Sender<Message>| async move {
                let directory = project_dir();
                let backend = directory.join(".venv/bin/python");
                let mut child = match tokio::process::Command::new(&backend)
                    .current_dir(&directory)
                    .args([
                        "-m",
                        "nothingx.service_entry",
                        "--backend",
                        BACKEND,
                        "--auto",
                    ])
                    .stdin(Stdio::piped())
                    .stdout(Stdio::piped())
                    .stderr(Stdio::null())
                    .kill_on_drop(true)
                    .spawn()
                {
                    Ok(child) => child,
                    Err(error) => {
                        let _ = output
                            .send(Message::BridgeError(format!(
                                "Cannot start Bluetooth backend: {error}"
                            )))
                            .await;
                        futures::future::pending::<()>().await;
                        return;
                    }
                };
                let mut stdin = child.stdin.take().expect("piped stdin");
                let mut lines = BufReader::new(child.stdout.take().expect("piped stdout")).lines();
                let (sender, mut requests) = mpsc::unbounded_channel::<String>();
                if output.send(Message::BridgeReady(sender)).await.is_err() {
                    return;
                }
                loop {
                    tokio::select! {
                        line = lines.next_line() => match line {
                            Ok(Some(line)) => if let Ok(value) = serde_json::from_str::<Value>(&line) {
                                if output.send(Message::BridgeEvent(value)).await.is_err() { break; }
                            },
                            _ => break,
                        },
                        request = requests.recv() => match request {
                            Some(request) => {
                                if stdin.write_all(request.as_bytes()).await.is_err() || stdin.write_all(b"\n").await.is_err() { break; }
                            },
                            None => break,
                        },
                    }
                }
                let _ = output
                    .send(Message::BridgeError(
                        "Bluetooth backend stopped. Reopen the applet.".into(),
                    ))
                    .await;
                futures::future::pending::<()>().await;
            },
        )
    })
}

impl Applet {
    fn send(&mut self, value: Value) {
        if self
            .sender
            .as_ref()
            .is_none_or(|sender| sender.send(value.to_string()).is_err())
        {
            self.detail = "Backend unavailable".into();
            self.phase = "disconnected".into();
            self.pending.clear();
            self.requested.clear();
        }
    }
    fn setting(&self, key: &str) -> Option<&Value> {
        self.requested.get(key).or_else(|| self.state.get(key))
    }
    fn ready(&self, key: &str) -> bool {
        matches!(self.phase.as_str(), "connected" | "demo")
            && !self.pending.contains(key)
            && self.state["capabilities"]
                .as_array()
                .is_some_and(|caps| caps.iter().any(|value| value.as_str() == Some(key)))
            && self.state.get(key).is_some()
    }
    fn battery(&self, part: &str) -> String {
        self.state
            .get("battery")
            .and_then(|v| v.get(part))
            .and_then(|v| v.get("level"))
            .and_then(Value::as_u64)
            .map_or_else(|| "—".into(), |level| format!("{level}%"))
    }
    fn artwork(&self, part: &str) -> cosmic::widget::icon::Handle {
        let family = self
            .state
            .pointer("/device/artwork")
            .and_then(Value::as_str)
            .unwrap_or("cmf-buds-pro-2");
        let relative = if family == "cmf-buds-pro-2" {
            format!("cmf-buds-pro-2/blue_{part}.png")
        } else {
            format!("devices/{family}_{part}.png")
        };
        let image = project_dir().join("nothingx/assets").join(relative);
        if image.is_file() {
            icon::from_path(image)
        } else {
            icon::from_name("audio-headphones-symbolic").handle()
        }
    }
    fn single_battery(&self) -> bool {
        matches!(
            self.state.pointer("/device/kind").and_then(Value::as_str),
            Some("headphones" | "neckband")
        )
    }
    fn battery_cell(&self, part: &str, title: &str) -> Element<'_, Message> {
        let detail = if self
            .state
            .pointer(&format!("/battery/{part}/available"))
            .and_then(Value::as_bool)
            == Some(false)
        {
            "Last reported"
        } else if self
            .state
            .pointer(&format!("/battery/{part}/charging"))
            .and_then(Value::as_bool)
            == Some(true)
        {
            "Charging"
        } else {
            title
        };
        row![
            icon::icon(self.artwork(part)).size(44),
            column![
                text::caption(detail.to_string()),
                text::title3(self.battery(part))
            ]
            .spacing(2)
        ]
        .spacing(2)
        .align_y(Alignment::Center)
        .into()
    }
    fn option_button(&self, key: &'static str, value: &str) -> Element<'_, Message> {
        let selected = self.setting(key).and_then(Value::as_str) == Some(value);
        let mut control = button::standard(if selected {
            format!("✓ {value}")
        } else {
            value.to_string()
        })
        .class(themed_button(selected));
        if self.ready(key) {
            control = control.on_press(Message::Set(key, json!(value)));
        }
        control.into()
    }
    fn codec_button(&self, value: i64, title: &str) -> Element<'_, Message> {
        let mut control = button::standard(title.to_string()).class(themed_button(
            self.setting("codec").and_then(Value::as_i64) == Some(value),
        ));
        if self.ready("codec") {
            control = control.on_press(Message::Set("codec", json!(value)));
        }
        control.into()
    }
    fn toggle_row(&self, key: &'static str, title: &'static str) -> Element<'_, Message> {
        let value = self.setting(key).and_then(Value::as_bool);
        let control: Element<'_, Message> = if let Some(enabled) = value {
            let mut toggle = widget::toggler(enabled);
            if self.ready(key) {
                toggle = toggle.on_toggle(move |value| Message::Set(key, json!(value)));
            }
            toggle.into()
        } else {
            text::caption("—").into()
        };
        row![
            text::body(title),
            space::horizontal().width(Length::Fill),
            control
        ]
        .align_y(Alignment::Center)
        .into()
    }
    fn panel_content(&self) -> Element<'_, Message> {
        let image = icon::icon(self.artwork(if self.single_battery() {
            "headphone"
        } else {
            "left"
        }))
        .size(24);
        let l = self
            .state
            .pointer("/battery/left/level")
            .and_then(Value::as_u64);
        let r = self
            .state
            .pointer("/battery/right/level")
            .and_then(Value::as_u64);
        let level = if self.single_battery() {
            self.battery("headphone")
        } else {
            match (l, r) {
                (Some(l), Some(r)) => format!("{}%", l.min(r)),
                (Some(l), None) | (None, Some(l)) => format!("{l}%"),
                _ => "—".into(),
            }
        };
        let value = self.core.applet.text(level).width(Length::Fixed(42.0));
        if matches!(
            self.core.applet.anchor,
            PanelAnchor::Top | PanelAnchor::Bottom
        ) {
            row![image, value]
                .spacing(3)
                .align_y(Alignment::Center)
                .into()
        } else {
            column![image, value]
                .spacing(1)
                .align_x(Alignment::Center)
                .into()
        }
    }
    fn audio_controls(&self) -> Element<'_, Message> {
        if self.audio.get("available").and_then(Value::as_bool) != Some(true) {
            return text::body(
                self.audio
                    .get("error")
                    .and_then(Value::as_str)
                    .unwrap_or("Connecting to PipeWire…")
                    .to_string(),
            )
            .into();
        }
        let mut content = column![text::heading("Bluetooth profile")].spacing(10);
        if let Some(card) = self.audio.get("card").filter(|v| !v.is_null()) {
            let profiles = card
                .get("profiles")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            let titles: Vec<String> = profiles
                .iter()
                .map(|p| p["description"].as_str().unwrap_or("").to_string())
                .collect();
            let names: Vec<String> = profiles
                .iter()
                .map(|p| p["name"].as_str().unwrap_or("").to_string())
                .collect();
            let selected = names
                .iter()
                .position(|name| Some(name.as_str()) == card["profile"].as_str());
            if !titles.is_empty() {
                content = content.push(widget::dropdown::popup_dropdown(
                    titles,
                    selected,
                    move |index| Message::Audio("profile", json!(names[index]), None),
                    self.popup.unwrap_or(Id::NONE),
                    Message::Surface,
                    |m| m,
                ));
            }
        } else {
            content = content.push(text::caption("Connect the buds in Bluetooth settings."));
        }
        if let Some(sink) = self.audio.get("sink").filter(|v| !v.is_null()) {
            let codec = sink["codec"].as_str().unwrap_or("").to_uppercase();
            content = content.push(text::caption(format!(
                "{} · {}",
                codec,
                sink["sample"].as_str().unwrap_or("")
            )));
            let volume = sink["volume"].as_i64().unwrap_or(0).clamp(0, 100) as i32;
            content = content
                .push(text::heading(format!("Volume · {volume}%")))
                .push(widget::slider(0..=100, volume, |v| {
                    Message::Audio("output_volume", json!(v), None)
                }));
            content = content.push(
                row![
                    text::body("Mute"),
                    space::horizontal().width(Length::Fill),
                    widget::toggler(sink["mute"].as_bool().unwrap_or(false))
                        .on_toggle(|v| Message::Audio("output_mute", json!(v), None))
                ]
                .align_y(Alignment::Center),
            );
            let mut default = button::text("Use as default output");
            if sink["name"] != self.audio["default_sink"] {
                default = default.on_press(Message::Audio("default_output", Value::Null, None));
            }
            content = content.push(default);
        }
        if let Some(enabled) = self.audio["auto_headset"].as_bool() {
            content = content
                .push(text::caption(
                    "Allow headset mode for microphone use (all Bluetooth headsets)",
                ))
                .push(
                    widget::toggler(enabled)
                        .on_toggle(|v| Message::Audio("auto_headset", json!(v), None)),
                );
        }
        if let Some(sources) = self.audio["sources"].as_array() {
            let titles: Vec<String> = sources
                .iter()
                .map(|s| s["description"].as_str().unwrap_or("").to_string())
                .collect();
            let names: Vec<String> = sources
                .iter()
                .map(|s| s["name"].as_str().unwrap_or("").to_string())
                .collect();
            let selected = names
                .iter()
                .position(|n| Some(n.as_str()) == self.audio["default_source"].as_str());
            if !titles.is_empty() {
                content = content.push(text::heading("Microphone")).push(
                    widget::dropdown::popup_dropdown(
                        titles,
                        selected,
                        move |i| {
                            Message::Audio("default_input", Value::Null, Some(names[i].clone()))
                        },
                        self.popup.unwrap_or(Id::NONE),
                        Message::Surface,
                        |m| m,
                    ),
                );
            }
        }
        content=content.push(text::caption("Headset profiles provide microphone access with reduced playback quality. Application volume, balance and routing are in full settings."));
        content.into()
    }
    fn buds_controls(&self) -> Element<'_, Message> {
        let mut content = column![].spacing(9);
        for (key, title, field) in [
            ("anc", "Noise control", "anc_modes"),
            ("eq", "Equalizer", "eq_presets"),
        ] {
            if let Some(options) = self.state["device"][field]
                .as_array()
                .filter(|values| !values.is_empty())
            {
                content = content.push(text::heading(title));
                for chunk in options.chunks(3) {
                    let mut options_row = row![].spacing(4);
                    for option in chunk {
                        if let Some(value) = option.as_str().or_else(|| option["name"].as_str()) {
                            options_row = options_row.push(self.option_button(key, value));
                        }
                    }
                    content = content.push(options_row);
                }
            }
        }
        if let Some(bass) = self.setting("bass").and_then(Value::as_array) {
            let enabled = bass.first().and_then(Value::as_bool).unwrap_or(false);
            let level = bass.get(1).and_then(Value::as_f64).unwrap_or(0.0);
            let mut minus = button::standard("−").class(themed_button(false));
            let mut plus = button::standard("+").class(themed_button(false));
            let maximum = self.state["device"]["bass_max"].as_f64().unwrap_or(5.0);
            let mut toggle = widget::toggler(enabled);
            if self.ready("bass") {
                minus = minus.on_press(Message::Set(
                    "bass",
                    json!([enabled, (level - 0.5).max(0.0)]),
                ));
                plus = plus.on_press(Message::Set(
                    "bass",
                    json!([enabled, (level + 0.5).min(maximum)]),
                ));
                toggle = toggle.on_toggle(move |v| Message::Set("bass", json!([v, level])));
            }
            content = content.push(
                row![
                    text::body(format!("Ultra Bass · {level}")),
                    space::horizontal().width(Length::Fill),
                    minus,
                    plus,
                    toggle
                ]
                .spacing(4)
                .align_y(Alignment::Center),
            );
        }
        for (key, title) in [
            ("spatial", "Spatial audio"),
            ("low_latency", "Low latency"),
            ("in_ear", "In-ear detection"),
            ("dual", "Dual connection"),
            ("codec", "High-resolution audio"),
        ] {
            if self.state["capabilities"]
                .as_array()
                .is_some_and(|caps| caps.iter().any(|value| value.as_str() == Some(key)))
            {
                if key == "codec" {
                    content = content.push(text::heading(title)).push(
                        row![
                            self.codec_button(0, "Standard"),
                            self.codec_button(2, "LDAC")
                        ]
                        .spacing(4),
                    );
                } else {
                    content = content.push(self.toggle_row(key, title));
                }
            }
        }
        content.into()
    }
}

impl cosmic::Application for Applet {
    type Executor = cosmic::executor::Default;
    type Flags = ();
    type Message = Message;
    const APP_ID: &'static str = APP_ID;
    fn core(&self) -> &cosmic::Core {
        &self.core
    }
    fn core_mut(&mut self) -> &mut cosmic::Core {
        &mut self.core
    }
    fn init(core: cosmic::Core, _: ()) -> (Self, Task<cosmic::Action<Message>>) {
        (
            Self {
                core,
                popup: None,
                sender: None,
                state: json!({}),
                audio: json!({}),
                phase: "disconnected".into(),
                detail: "Connecting…".into(),
                pending: HashSet::new(),
                requested: BTreeMap::new(),
                audio_tab: false,
                opening_full: false,
            },
            Task::none(),
        )
    }
    fn style(&self) -> Option<cosmic::iced::theme::Style> {
        Some(cosmic::applet::style())
    }
    fn on_close_requested(&self, id: Id) -> Option<Message> {
        Some(Message::PopupClosed(id))
    }
    fn subscription(&self) -> Subscription<Message> {
        bridge_subscription()
    }
    fn view(&self) -> Element<'_, Message> {
        let control = button::custom(self.panel_content())
            .padding([0, 5])
            .on_press_down(Message::TogglePopup)
            .class(cosmic::theme::Button::AppletIcon);
        let tooltip = if self.single_battery() {
            format!("Headphone battery · {}", self.battery("headphone"))
        } else {
            format!(
                "Earbud battery · Left {} · Right {}\nCase {}",
                self.battery("left"),
                self.battery("right"),
                self.battery("case")
            )
        };
        self.core
            .applet
            .autosize_window(self.core.applet.applet_tooltip(
                control,
                tooltip,
                self.popup.is_some(),
                Message::Surface,
                None,
            ))
            .into()
    }
    fn view_window(&self, _: Id) -> Element<'_, Message> {
        let header = row![
            icon::icon(self.artwork(if self.single_battery() {
                "headphone"
            } else {
                "case"
            }))
            .size(32),
            text::title3(
                self.state
                    .pointer("/device/name")
                    .and_then(Value::as_str)
                    .unwrap_or("Nothing X")
                    .to_string()
            ),
            space::horizontal().width(Length::Fill),
            button::icon(icon::from_name("view-refresh-symbolic"))
                .on_press(Message::Action("refresh"))
        ]
        .spacing(8)
        .align_y(Alignment::Center);
        let batteries: Element<'_, Message> = if self.single_battery() {
            self.battery_cell("headphone", "Battery")
        } else {
            row![
                self.battery_cell("left", "Left"),
                space::horizontal().width(Length::Fill),
                self.battery_cell("right", "Right"),
                space::horizontal().width(Length::Fill),
                self.battery_cell("case", "Case")
            ]
            .align_y(Alignment::Center)
            .into()
        };
        let connection = if self.phase == "connected" {
            button::text("Disconnect").on_press(Message::Action("disconnect"))
        } else if self.phase == "connecting" {
            button::text("Cancel").on_press(Message::Action("disconnect"))
        } else {
            button::text("Connect").on_press(Message::Action("connect"))
        };
        let tabs = row![
            button::standard("Device")
                .class(themed_button(!self.audio_tab))
                .on_press(Message::Tab(false)),
            button::standard("Audio")
                .class(themed_button(self.audio_tab))
                .on_press(Message::Tab(true))
        ]
        .spacing(6);
        let mut content = column![header, batteries].spacing(10).width(Length::Fill);
        if !self.single_battery() && self.state.pointer("/battery/case/level").is_none() {
            content = content.push(text::caption(
                "Case battery: keep a bud inside with the lid open, then refresh.",
            ));
        }
        if !self.detail.is_empty() && self.detail != "Updated" && self.detail != "Connected" {
            content = content.push(text::caption(self.detail.clone()));
        }
        content = content
            .push(connection)
            .push(tabs)
            .push(if self.audio_tab {
                self.audio_controls()
            } else {
                self.buds_controls()
            })
            .push(button::text("Open full settings").on_press(Message::OpenFull));
        let registry: Value =
            std::fs::read(project_dir().join("nothingx/assets/themes/themes.json"))
                .ok()
                .and_then(|data| serde_json::from_slice(&data).ok())
                .unwrap_or_else(|| json!({}));
        let preferences: Value = std::fs::read(preferences_path())
            .ok()
            .and_then(|data| serde_json::from_slice(&data).ok())
            .unwrap_or_else(|| json!({}));
        if let Some(themes) = registry["themes"].as_array() {
            let titles: Vec<String> = themes
                .iter()
                .map(|t| t["name"].as_str().unwrap_or("").to_string())
                .collect();
            let ids: Vec<String> = themes
                .iter()
                .map(|t| t["id"].as_str().unwrap_or("").to_string())
                .collect();
            let selected = ids
                .iter()
                .position(|id| Some(id.as_str()) == preferences["theme"].as_str());
            content = content.push(widget::dropdown::popup_dropdown(
                titles,
                selected,
                move |i| Message::Theme(ids[i].clone()),
                self.popup.unwrap_or(Id::NONE),
                Message::Surface,
                |m| m,
            ));
        }
        let [background, foreground, _, _, _] = theme_colors();
        self.core
            .applet
            .popup_container(
                container(scrollable(content).height(Length::Shrink))
                    .style(move |_| cosmic::iced::widget::container::Style {
                        background: Some(background.into()),
                        text_color: Some(foreground),
                        ..Default::default()
                    })
                    .padding(16)
                    .width(Length::Fixed(420.0))
                    .max_height(730.0),
            )
            .into()
    }
    fn update(&mut self, message: Message) -> Task<cosmic::Action<Message>> {
        match message {
            Message::Surface(action) => {
                return cosmic::task::message(cosmic::Action::Surface(action));
            }
            Message::TogglePopup => {
                if let Some(id) = self.popup.take() {
                    return cosmic::iced::platform_specific::shell::wayland::commands::popup::destroy_popup(id);
                }
                let id = Id::unique();
                self.popup = Some(id);
                self.send(json!({"action":"audio","key":"refresh"}));
                let mut settings = self.core.applet.get_popup_settings(
                    self.core.main_window_id().unwrap(),
                    id,
                    None,
                    None,
                    None,
                );
                settings.positioner.size_limits = Limits::NONE
                    .min_width(390.0)
                    .max_width(460.0)
                    .min_height(200.0)
                    .max_height(800.0);
                return cosmic::iced::platform_specific::shell::wayland::commands::popup::get_popup(
                    settings,
                );
            }
            Message::PopupClosed(id) => {
                if self.popup == Some(id) {
                    self.popup = None;
                }
            }
            Message::BridgeReady(sender) => self.sender = Some(sender),
            Message::BridgeError(error) => {
                self.sender = None;
                self.phase = "disconnected".into();
                self.detail = error;
                self.pending.clear();
                self.requested.clear();
            }
            Message::BridgeEvent(event) => match event["type"].as_str() {
                Some("state") => {
                    self.state = event.get("state").cloned().unwrap_or_else(|| json!({}))
                }
                Some("audio") => {
                    self.audio = event.get("state").cloned().unwrap_or_else(|| json!({}))
                }
                Some("status") => {
                    self.phase = event["phase"].as_str().unwrap_or("disconnected").into();
                    self.detail = event["detail"].as_str().unwrap_or("").into();
                    if self.phase == "disconnected" {
                        self.pending.clear();
                        self.requested.clear();
                        if self.opening_full {
                            self.opening_full = false;
                            let audio_tab = self.audio_tab;
                            return Task::perform(
                                async move {
                                    let mut command =
                                        tokio::process::Command::new(project_dir().join("run.sh"));
                                    command
                                        .args(["--backend", BACKEND, "--connect"])
                                        .arg("--page")
                                        .arg(if audio_tab { "audio" } else { "overview" });
                                    match command.status().await {
                                        Ok(_) => Message::FullClosed,
                                        Err(error) => Message::FullFailed(format!(
                                            "Could not open settings: {error}"
                                        )),
                                    }
                                },
                                cosmic::Action::App,
                            );
                        }
                    }
                }
                Some("message") => {
                    self.detail = event["text"].as_str().unwrap_or("").into();
                }
                Some("completed") => {
                    if let Some(key) = event["key"].as_str() {
                        self.pending.remove(key);
                        self.requested.remove(key);
                    }
                }
                _ => {}
            },
            Message::Action(action) => self.send(json!({"action":action})),
            Message::Set(key, value) => {
                if self.ready(key) {
                    self.pending.insert(key.into());
                    self.requested.insert(key.into(), value.clone());
                    self.send(json!({"action":"write","key":key,"value":value}));
                }
            }
            Message::Audio(key, value, target) => {
                self.send(json!({"action":"audio","key":key,"value":value,"target":target}));
            }
            Message::Tab(value) => self.audio_tab = value,
            Message::Theme(value) => {
                let path = preferences_path();
                let mut preferences: Value = std::fs::read(&path)
                    .ok()
                    .and_then(|data| serde_json::from_slice(&data).ok())
                    .filter(Value::is_object)
                    .unwrap_or_else(|| json!({}));
                preferences["theme"] = json!(value);
                if let Some(parent) = path.parent() {
                    let _ = std::fs::create_dir_all(parent);
                }
                let temporary = path.with_extension(format!("{}.tmp", std::process::id()));
                if std::fs::write(&temporary, preferences.to_string()).is_ok() {
                    let _ = std::fs::rename(temporary, path);
                }
            }
            Message::OpenFull => {
                self.opening_full = true;
                self.send(json!({"action":"disconnect"}));
            }
            Message::FullClosed => self.send(json!({"action":"connect"})),
            Message::FullFailed(error) => {
                self.detail = error;
                self.send(json!({"action":"connect"}));
            }
        }
        Task::none()
    }
}
fn main() -> cosmic::iced::Result {
    cosmic::applet::run::<Applet>(())
}
