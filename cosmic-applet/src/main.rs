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

fn themed_slider() -> cosmic::theme::style::iced::Slider {
    use cosmic::iced::widget::slider::{Breakpoint, Handle, HandleShape, Rail, Style};
    let [_, foreground, accent, card, _] = theme_colors();
    let style = move |_: &cosmic::Theme| Style {
        rail: Rail {
            backgrounds: (accent.into(), card.into()),
            width: 5.0,
            border: Default::default(),
        },
        handle: Handle {
            shape: HandleShape::Circle { radius: 8.0 },
            background: foreground.into(),
            border_width: 0.0,
            border_color: foreground,
        },
        breakpoint: Breakpoint { color: card },
    };
    cosmic::theme::style::iced::Slider::Custom {
        active: std::rc::Rc::new(style),
        hovered: std::rc::Rc::new(style),
        dragging: std::rc::Rc::new(style),
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
    fn choice(&self, key: &'static str, value: &str, title: &str) -> Element<'_, Message> {
        let selected = self.setting(key).and_then(Value::as_str) == Some(value);
        let mut control = button::standard(title.to_string()).class(themed_button(selected));
        if self.ready(key) {
            control = control.on_press(Message::Set(key, json!(value)));
        }
        control.into()
    }
    fn volume_controls(&self) -> Element<'_, Message> {
        let mut content = column![].spacing(10);
        if let Some(sink) = self.audio.get("sink").filter(|value| !value.is_null()) {
            let volume = sink["volume"].as_i64().unwrap_or(0).clamp(0, 100) as i32;
            let muted = sink["mute"].as_bool().unwrap_or(false);
            content = content.push(
                row![
                    text::heading(format!("Volume · {volume}%")),
                    space::horizontal().width(Length::Fill),
                    button::standard(if muted { "Unmute" } else { "Mute" })
                        .class(themed_button(muted))
                        .on_press(Message::Audio("output_mute", json!(!muted), None))
                ]
                .align_y(Alignment::Center),
            );
            content = content.push(
                widget::slider(0..=100, volume, |value| {
                    Message::Audio("output_volume", json!(value), None)
                })
                .class(themed_slider()),
            );
        }
        content.into()
    }
    fn audio_controls(&self) -> Element<'_, Message> {
        let mut content = column![self.volume_controls()].spacing(14);
        if let Some(card) = self.audio.get("card").filter(|value| !value.is_null()) {
            if let Some(profiles) = card["profiles"].as_array() {
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
                    content = content.push(text::heading("Bluetooth profile")).push(
                        widget::dropdown::popup_dropdown(
                            titles,
                            selected,
                            move |i| Message::Audio("profile", json!(names[i]), None),
                            self.popup.unwrap_or(Id::NONE),
                            Message::Surface,
                            |m| m,
                        ),
                    );
                }
            }
        }
        if let Some(sink) = self.audio.get("sink").filter(|value| !value.is_null()) {
            content = content.push(text::caption(format!(
                "{} · {}",
                sink["codec"].as_str().unwrap_or("").to_uppercase(),
                sink["sample"].as_str().unwrap_or("")
            )));
            if sink["name"] != self.audio["default_sink"] {
                content = content.push(
                    button::standard("Set as default output")
                        .class(themed_button(false))
                        .on_press(Message::Audio("default_output", Value::Null, None)),
                );
            }
        } else {
            content = content.push(text::caption(
                "Connect your device in system Bluetooth settings.",
            ));
        }
        content = content.push(text::caption(
            "Microphone and application routing are in full settings.",
        ));
        content.into()
    }
    fn buds_controls(&self) -> Element<'_, Message> {
        let mut content = column![].spacing(12);
        if let Some(modes) = self.state["device"]["anc_modes"]
            .as_array()
            .filter(|values| !values.is_empty())
        {
            let current = self.setting("anc").and_then(Value::as_str).unwrap_or("");
            let cancelled = !["", "Off", "Transparency"].contains(&current);
            let fallback = ["Adaptive", "High", "Low"]
                .into_iter()
                .find(|name| modes.iter().any(|m| m.as_str() == Some(name)))
                .unwrap_or("High");
            let cancellation = if cancelled { current } else { fallback };
            content = content.push(text::heading("Noise control"));
            content = content.push(
                row![
                    self.choice("anc", cancellation, "Cancellation"),
                    self.option_button("anc", "Transparency"),
                    self.option_button("anc", "Off")
                ]
                .spacing(5),
            );
            if cancelled {
                let mut levels = row![].spacing(5);
                for name in ["Low", "Mid", "High", "Adaptive"] {
                    if modes.iter().any(|m| m.as_str() == Some(name)) {
                        levels = levels.push(self.option_button("anc", name));
                    }
                }
                content = content.push(levels);
            }
        }
        if self.ready("eq") {
            if let Some(presets) = self.state["device"]["eq_presets"].as_array() {
                let names: Vec<String> = presets
                    .iter()
                    .filter_map(|preset| preset["name"].as_str().map(str::to_string))
                    .collect();
                let selected = names.iter().position(|name| {
                    Some(name.as_str()) == self.setting("eq").and_then(Value::as_str)
                });
                let values = names.clone();
                content = content.push(text::heading("Equalizer")).push(
                    widget::dropdown::popup_dropdown(
                        names,
                        selected,
                        move |i| Message::Set("eq", json!(values[i])),
                        self.popup.unwrap_or(Id::NONE),
                        Message::Surface,
                        |m| m,
                    ),
                );
            }
        }
        content = content.push(self.volume_controls());
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
            button::standard("Quick controls")
                .class(themed_button(!self.audio_tab))
                .on_press(Message::Tab(false)),
            button::standard("Audio")
                .class(themed_button(self.audio_tab))
                .on_press(Message::Tab(true))
        ]
        .spacing(6);
        let mut content = column![header, batteries].spacing(16).width(Length::Fill);
        if self.phase != "connected" && self.phase != "demo" {
            content = content.push(connection);
        }
        if !self.single_battery() && self.state.pointer("/battery/case/level").is_none() {
            content = content.push(text::caption("Open the case to refresh its battery."));
        }
        if !self.detail.is_empty() && self.detail != "Updated" && self.detail != "Connected" {
            content = content.push(text::caption(self.detail.clone()));
        }
        content = content
            .push(tabs)
            .push(if self.audio_tab {
                self.audio_controls()
            } else {
                self.buds_controls()
            })
            .push(button::text("Open full settings").on_press(Message::OpenFull));
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
                    .width(Length::Fixed(410.0))
                    .max_height(650.0),
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
            Message::OpenFull => {
                if self.opening_full {
                    return Task::none();
                }
                self.opening_full = true;
                let audio_tab = self.audio_tab;
                return Task::perform(
                    async move {
                        let mut command =
                            tokio::process::Command::new(project_dir().join("run.sh"));
                        command.args([
                            "--backend",
                            BACKEND,
                            "--page",
                            if audio_tab { "audio" } else { "overview" },
                        ]);
                        match command.status().await {
                            Ok(_) => Message::FullClosed,
                            Err(error) => {
                                Message::FullFailed(format!("Could not open settings: {error}"))
                            }
                        }
                    },
                    cosmic::Action::App,
                );
            }
            Message::FullClosed => self.opening_full = false,
            Message::FullFailed(error) => {
                self.opening_full = false;
                self.detail = error;
            }
        }
        Task::none()
    }
}
fn main() -> cosmic::iced::Result {
    cosmic::applet::run::<Applet>(())
}
