use cosmic::{
    Element, Task,
    applet::cosmic_panel_config::PanelAnchor,
    iced::{Alignment, Length, Limits, Subscription, futures, window::Id},
    widget::{self, button, column, container, icon, row, scrollable, space, text},
};
use futures::SinkExt;
use serde_json::{Value, json};
use std::{path::PathBuf, process::Stdio};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    sync::mpsc,
};

const APP_ID: &str = "io.github.basanta_bhandari.NothingXApplet";

#[derive(Debug, Clone)]
enum Message {
    TogglePopup,
    PopupClosed(Id),
    BridgeReady(mpsc::UnboundedSender<String>),
    BridgeEvent(Value),
    BridgeError(String),
    Action(&'static str),
    Set(&'static str, Value),
    OpenFull,
}

struct Applet {
    core: cosmic::Core,
    popup: Option<Id>,
    sender: Option<mpsc::UnboundedSender<String>>,
    state: Value,
    phase: String,
    detail: String,
    pending: bool,
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
            data.join("nothingx-cosmic/app")
        })
}

fn bridge_subscription() -> Subscription<Message> {
    Subscription::run(|| {
        cosmic::iced::stream::channel(
            64,
            |mut output: futures::channel::mpsc::Sender<Message>| async move {
                let directory = project_dir();
                let python = directory.join(".venv/bin/python");
                let mut child = match tokio::process::Command::new(&python)
                    .current_dir(&directory)
                    .args(["-m", "nothingx.cosmic_bridge"])
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
            self.detail = "Bluetooth backend unavailable".into();
            self.phase = "disconnected".into();
            self.pending = false;
        }
    }

    fn ready(&self, key: &str) -> bool {
        self.phase == "connected"
            && !self.pending
            && matches!(
                self.state.get("model").and_then(Value::as_str),
                Some("B172" | "B187")
            )
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

    fn battery_cell(&self, part: &str, label: &str) -> Element<'_, Message> {
        let image = project_dir()
            .join("nothingx/assets/cmf-buds-pro-2")
            .join(format!("blue_{part}.png"));
        row![
            icon::icon(icon::from_path(image)).size(48),
            column![
                text::caption(label.to_string()),
                text::title3(self.battery(part))
            ]
            .spacing(2)
        ]
        .spacing(3)
        .align_y(Alignment::Center)
        .into()
    }

    fn option_button(&self, key: &'static str, value: &'static str) -> Element<'_, Message> {
        let selected = self.state.get(key).and_then(Value::as_str) == Some(value);
        let label = if selected {
            format!("✓ {value}")
        } else {
            value.to_string()
        };
        let mut button = button::standard(label);
        if self.ready(key) {
            button = button.on_press(Message::Set(key, json!(value)));
        }
        button.into()
    }

    fn toggle_row(&self, key: &'static str, title: &'static str) -> Element<'_, Message> {
        let value = self.state.get(key).and_then(Value::as_bool);
        let control: Element<'_, Message> = if let Some(enabled) = value.filter(|_| self.ready(key))
        {
            widget::toggler(enabled)
                .on_toggle(move |next| Message::Set(key, json!(next)))
                .into()
        } else {
            text::caption(if value.is_some() { "Busy" } else { "—" }).into()
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
        let icon = icon::icon(icon::from_path(
            project_dir().join("nothingx/assets/cmf-buds-pro-2/blue_case.png"),
        ))
        .size(22);
        let left = self
            .state
            .pointer("/battery/left/level")
            .and_then(Value::as_u64);
        let right = self
            .state
            .pointer("/battery/right/level")
            .and_then(Value::as_u64);
        let level = match (left, right) {
            (Some(l), Some(r)) => format!("{}%", l.min(r)),
            (Some(l), None) | (None, Some(l)) => format!("{l}%"),
            _ => "—".to_string(),
        };
        let value = self.core.applet.text(level);
        if matches!(
            self.core.applet.anchor,
            PanelAnchor::Top | PanelAnchor::Bottom
        ) {
            row![icon, value]
                .spacing(5)
                .align_y(Alignment::Center)
                .into()
        } else {
            column![icon, value]
                .spacing(2)
                .align_x(Alignment::Center)
                .into()
        }
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
                phase: "disconnected".into(),
                detail: "Connecting…".into(),
                pending: false,
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
        button::custom(self.panel_content())
            .padding(4)
            .on_press_down(Message::TogglePopup)
            .class(cosmic::theme::Button::AppletIcon)
            .into()
    }

    fn view_window(&self, _: Id) -> Element<'_, Message> {
        let header = row![
            icon::icon(icon::from_path(
                project_dir().join("nothingx/assets/cmf-buds-pro-2/blue_case.png")
            ))
            .size(32),
            text::title3("CMF Buds Pro 2"),
            space::horizontal().width(Length::Fill),
            button::icon(icon::from_name("view-refresh-symbolic"))
                .on_press(Message::Action("refresh"))
        ]
        .spacing(8)
        .align_y(Alignment::Center);
        let batteries = row![
            self.battery_cell("left", "Left"),
            space::horizontal().width(Length::Fill),
            self.battery_cell("right", "Right"),
            space::horizontal().width(Length::Fill),
            self.battery_cell("case", "Case"),
        ]
        .align_y(Alignment::Center);
        let connection = if self.phase == "connected" {
            button::text("Disconnect").on_press(Message::Action("disconnect"))
        } else if self.phase == "connecting" {
            button::text("Cancel").on_press(Message::Action("disconnect"))
        } else {
            button::text("Connect").on_press(Message::Action("connect"))
        };
        let mut content = column![
            header,
            text::caption(self.detail.clone()),
            batteries,
            connection,
            text::heading("Noise control"),
            row![
                self.option_button("anc", "Off"),
                self.option_button("anc", "Transparency"),
                self.option_button("anc", "Adaptive")
            ]
            .spacing(4),
            row![
                self.option_button("anc", "Low"),
                self.option_button("anc", "Mid"),
                self.option_button("anc", "High")
            ]
            .spacing(4),
            text::heading("Equalizer"),
            row![
                self.option_button("eq", "Dirac Opteo"),
                self.option_button("eq", "Rock"),
                self.option_button("eq", "Pop")
            ]
            .spacing(4),
            row![
                self.option_button("eq", "Electronic"),
                self.option_button("eq", "Enhance vocals"),
                self.option_button("eq", "Classical")
            ]
            .spacing(4),
        ]
        .spacing(9)
        .width(Length::Fill);
        if let Some(bass) = self.state.get("bass").and_then(Value::as_array) {
            let enabled = bass.first().and_then(Value::as_bool).unwrap_or(false);
            let level = bass.get(1).and_then(Value::as_f64).unwrap_or(0.0);
            let mut minus = button::standard("−");
            let mut plus = button::standard("+");
            let mut toggle = button::text(if enabled { "Disable" } else { "Enable" });
            if self.ready("bass") {
                minus = minus.on_press(Message::Set(
                    "bass",
                    json!([enabled, (level - 0.5).max(0.0)]),
                ));
                plus = plus.on_press(Message::Set(
                    "bass",
                    json!([enabled, (level + 0.5).min(5.0)]),
                ));
                toggle = toggle.on_press(Message::Set("bass", json!([!enabled, level])));
            }
            content = content.push(
                row![
                    text::body(format!("Ultra Bass: {level}")),
                    space::horizontal().width(Length::Fill),
                    minus,
                    plus,
                    toggle
                ]
                .spacing(4)
                .align_y(Alignment::Center),
            );
        }
        content = content
            .push(self.toggle_row("spatial", "Spatial audio"))
            .push(self.toggle_row("low_latency", "Low latency"))
            .push(self.toggle_row("in_ear", "In-ear detection"))
            .push(self.toggle_row("dual", "Dual connection"))
            .push(button::text("Open full settings").on_press(Message::OpenFull));
        self.core
            .applet
            .popup_container(
                container(scrollable(content).height(Length::Shrink))
                    .padding(16)
                    .width(Length::Fixed(400.0))
                    .max_height(700.0),
            )
            .into()
    }

    fn update(&mut self, message: Message) -> Task<cosmic::Action<Message>> {
        match message {
            Message::TogglePopup => {
                if let Some(id) = self.popup.take() {
                    return cosmic::iced::platform_specific::shell::wayland::commands::popup::destroy_popup(id);
                }
                let id = Id::unique();
                self.popup = Some(id);
                let mut settings = self.core.applet.get_popup_settings(
                    self.core.main_window_id().unwrap(),
                    id,
                    None,
                    None,
                    None,
                );
                settings.positioner.size_limits = Limits::NONE
                    .min_width(350.0)
                    .max_width(440.0)
                    .min_height(250.0)
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
                self.pending = false;
            }
            Message::BridgeEvent(event) => match event.get("type").and_then(Value::as_str) {
                Some("state") => {
                    self.state = event.get("state").cloned().unwrap_or_else(|| json!({}))
                }
                Some("status") => {
                    self.phase = event
                        .get("phase")
                        .and_then(Value::as_str)
                        .unwrap_or("disconnected")
                        .into();
                    self.detail = event
                        .get("detail")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .into();
                    if self.phase == "disconnected" {
                        self.pending = false;
                    }
                }
                Some("message") => {
                    self.detail = event
                        .get("text")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .into()
                }
                Some("completed") => self.pending = false,
                _ => {}
            },
            Message::Action(action) => self.send(json!({"action":action})),
            Message::Set(key, value) => {
                if self.ready(key) {
                    self.pending = true;
                    self.send(json!({"action":"write", "key":key, "value":value}));
                }
            }
            Message::OpenFull => {
                self.send(json!({"action":"disconnect"}));
                if let Err(error) = std::process::Command::new(project_dir().join("run.sh")).spawn()
                {
                    self.detail = format!("Could not open full settings: {error}");
                }
            }
        }
        Task::none()
    }
}

fn main() -> cosmic::iced::Result {
    cosmic::applet::run::<Applet>(())
}
