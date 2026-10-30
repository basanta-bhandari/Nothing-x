#include "bluetooth.hpp"
#include <algorithm>
#include <bluetooth/bluetooth.h>
#include <bluetooth/rfcomm.h>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <glib-unix.h>
#include <regex>
#include <sys/socket.h>
#include <unistd.h>

Bluetooth::Bluetooth(Emit output) : emit(std::move(output)) {
  timer = g_timeout_add(
      20,
      [](gpointer data) -> gboolean {
        auto &self = *static_cast<Bluetooth *>(data);
        auto now = Clock::now();
        if (self.opening && self.connect_watch && now >= self.connect_deadline)
          self.next_channel();
        if (self.active && now >= self.active->deadline)
          self.complete(std::nullopt);
        std::vector<int> expired;
        for (const auto &[side, end] : self.ringing)
          if (now >= end)
            expired.push_back(side);
        for (int side : expired)
          self.write("find", Json::array({side, false}));
        if (self.linked && now - self.last_poll > std::chrono::seconds(25)) {
          self.last_poll = now;
          if (!self.refresh_keys.count("battery") && !self.demo)
            self.enqueue(reads.at("battery"), 0.6);
        }
        return G_SOURCE_CONTINUE;
      },
      this);
}
Bluetooth::~Bluetooth() {
  if (timer)
    g_source_remove(timer);
  disconnect(false);
}
void Bluetooth::status(const char *phase, const std::string &detail) {
  emit(
      Json::object({{"type", "status"}, {"phase", phase}, {"detail", detail}}));
}
void Bluetooth::message(const std::string &text, bool error) {
  emit(Json::object({{"type", "message"}, {"text", text}, {"error", error}}));
}
void Bluetooth::close_socket() {
  for (auto *watch : {&input_watch, &output_watch, &connect_watch})
    if (*watch) {
      g_source_remove(*watch);
      *watch = 0;
    }
  if (fd >= 0) {
    ::close(fd);
    fd = -1;
  }
  buffer.clear();
  output.clear();
  active.reset();
  requests.clear();
}
void Bluetooth::disconnect(bool notify) {
  if (fd >= 0)
    for (const auto &[side, end] : ringing) {
      auto bytes = encode({0xF002, {uint8_t(side), 0}}, ++sequence);
      ::send(fd, bytes.data(), bytes.size(), MSG_NOSIGNAL);
    }
  close_socket();
  linked = opening = demo = false;
  ringing.clear();
  refresh_keys.clear();
  for (const auto &key : pending_keys)
    emit(Json::object({{"type", "completed"}, {"key", key}}));
  pending_keys.clear();
  state = Json::object();
  if (notify) {
    emit(Json::object({{"type", "state"}, {"state", state}}));
    status("disconnected", "Disconnected");
  }
}
void Bluetooth::connect(const std::string &mac, int channel) {
  if (!std::regex_match(mac,
                        std::regex("([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}")) ||
      channel < 0 || channel > 30)
    throw std::runtime_error(
        "Select paired earbuds or enter a valid Bluetooth address.");
  disconnect(false);
  address = mac;
  opening = true;
  emit(Json::object({{"type", "state"}, {"state", state}}));
  status("connecting", "Connecting…");
  candidates.clear();
  auto add = [this](int value) {
    if (std::find(candidates.begin(), candidates.end(), value) ==
        candidates.end())
      candidates.push_back(value);
  };
  if (channel)
    add(channel);
  else {
    if (channels.count(mac))
      add(channels[mac]);
    for (int value : {15, 16, 17})
      add(value);
    for (int value = 1; value <= 30; ++value)
      add(value);
  }
  candidate_index = 0;
  next_channel();
}
void Bluetooth::next_channel() {
  close_socket();
  if (!opening)
    return;
  if (candidate_index >= candidates.size()) {
    failed("Cannot open the control connection. Connect the buds in Bluetooth "
           "settings and close other companion apps.");
    return;
  }
  int channel = candidates[candidate_index++];
  fd = ::socket(AF_BLUETOOTH, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC,
                BTPROTO_RFCOMM);
  if (fd < 0) {
    failed(std::strerror(errno));
    return;
  }
  sockaddr_rc remote{};
  remote.rc_family = AF_BLUETOOTH;
  remote.rc_channel = uint8_t(channel);
  str2ba(address.c_str(), &remote.rc_bdaddr);
  int result =
      ::connect(fd, reinterpret_cast<sockaddr *>(&remote), sizeof(remote));
  if (result == 0) {
    established();
    return;
  }
  if (errno != EINPROGRESS) {
    next_channel();
    return;
  }
  connect_deadline = Clock::now() + std::chrono::seconds(1);
  connect_watch = g_unix_fd_add(
      fd, GIOCondition(G_IO_OUT | G_IO_ERR | G_IO_HUP),
      [](gint socket, GIOCondition, gpointer data) -> gboolean {
        auto &self = *static_cast<Bluetooth *>(data);
        self.connect_watch = 0;
        int error = 0;
        socklen_t length = sizeof(error);
        getsockopt(socket, SOL_SOCKET, SO_ERROR, &error, &length);
        if (error)
          self.next_channel();
        else
          self.established();
        return G_SOURCE_REMOVE;
      },
      this);
}
void Bluetooth::established() {
  input_watch = g_unix_fd_add(
      fd, GIOCondition(G_IO_IN | G_IO_HUP | G_IO_ERR),
      [](gint socket, GIOCondition condition, gpointer data) -> gboolean {
        auto &self = *static_cast<Bluetooth *>(data);
        if (condition & G_IO_IN)
          self.receive();
        if (self.fd != socket)
          return G_SOURCE_REMOVE;
        if (condition & (G_IO_HUP | G_IO_ERR)) {
          self.input_watch = 0;
          if (self.opening)
            self.next_channel();
          else
            self.failed("Earbuds disconnected.");
          return G_SOURCE_REMOVE;
        }
        return G_SOURCE_CONTINUE;
      },
      this);
  enqueue({0xC001, {}}, 0.8, [this](std::optional<Frame> frame) {
    if (!frame) {
      next_channel();
      return;
    }
    enqueue(
        {0xF001, {}}, 0.2,
        [this](std::optional<Frame>) {
          enqueue(
              reads.at("model"), 0.6,
              [this](std::optional<Frame>) {
                opening = false;
                linked = true;
                channels[address] = candidates[candidate_index - 1];
                status("connected", "Connected");
                last_poll = Clock::now();
                refresh();
              },
              true);
        },
        true);
  });
}
void Bluetooth::failed(const std::string &detail) {
  disconnect();
  message(detail, true);
}
void Bluetooth::enqueue(Command command, double timeout,
                        std::function<void(std::optional<Frame>)> done,
                        bool priority) {
  Request request{
      std::move(command), timeout, std::move(done), 0, {}, priority};
  if (priority)
    requests.push_front(std::move(request));
  else
    requests.push_back(std::move(request));
  if (priority && linked && active && !active->urgent && !dispatching) {
    complete(std::nullopt);
    return;
  }
  pump();
}
void Bluetooth::pump() {
  if (dispatching || active || requests.empty() || fd < 0)
    return;
  active = std::move(requests.front());
  requests.pop_front();
  sequence = sequence == 255 ? 1 : sequence + 1;
  active->sequence = sequence;
  active->deadline =
      Clock::now() + std::chrono::milliseconds(int(active->timeout * 1000));
  auto bytes = encode(active->command, sequence);
  output.insert(output.end(), bytes.begin(), bytes.end());
  flush();
}
void Bluetooth::flush() {
  while (fd >= 0 && !output.empty()) {
    ssize_t written = ::send(fd, output.data(), output.size(), MSG_NOSIGNAL);
    if (written > 0)
      output.erase(output.begin(), output.begin() + written);
    else if (written < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
      if (!output_watch)
        output_watch = g_unix_fd_add(
            fd, G_IO_OUT,
            [](gint, GIOCondition, gpointer data) -> gboolean {
              auto &self = *static_cast<Bluetooth *>(data);
              self.output_watch = 0;
              self.flush();
              return G_SOURCE_REMOVE;
            },
            this);
      break;
    } else {
      failed("Bluetooth write failed.");
      return;
    }
  }
}
void Bluetooth::complete(std::optional<Frame> response) {
  if (!active)
    return;
  auto callback = std::move(active->done);
  active.reset();
  dispatching = true;
  if (callback)
    callback(std::move(response));
  dispatching = false;
  pump();
}
void Bluetooth::receive() {
  uint8_t bytes[4096];
  while (fd >= 0) {
    ssize_t count = ::recv(fd, bytes, sizeof(bytes), 0);
    if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
      break;
    if (count <= 0) {
      if (opening)
        next_channel();
      else
        failed("The earbuds closed the control connection.");
      return;
    }
    buffer.insert(buffer.end(), bytes, bytes + count);
    for (const auto &frame : decode(buffer)) {
      apply(frame);
      if (active && frame.command == active->command.command &&
          frame.sequence == active->sequence)
        complete(frame);
      if (fd < 0)
        return;
    }
  }
}
void Bluetooth::apply(const Frame &frame) {
  auto update = parse_frame(frame);
  if (update.has("battery")) {
    auto battery = state.get("battery").null() ? Json::object()
                                               : state.get("battery").clone();
    for (const char *part : {"left", "right", "case", "headphone"}) {
      auto incoming = update.get("battery").get(part);
      if (!incoming.null()) {
        incoming.set("available", true);
        incoming.set("updated_at", g_get_real_time() / 1000000.0);
        battery.set(part, incoming);
      } else if (update.get("battery").has(part) ||
                 (frame.command == 0xC007 && std::string(part) == "case")) {
        auto cached = battery.get(part);
        if (!cached.null()) {
          cached.set("available", false);
          battery.set(part, cached);
        }
      }
    }
    update.set("battery", battery);
  }
  bool changed = false;
  for (const char *key :
       {"model", "battery", "anc", "eq", "in_ear", "low_latency", "spatial",
        "bass", "dual", "codec", "firmware"})
    if (update.has(key)) {
      state.set(key, update.get(key));
      changed = true;
    }
  if (changed)
    emit(Json::object({{"type", "state"}, {"state", state}}));
}
void Bluetooth::refresh() {
  if (demo) {
    emit(Json::object({{"type", "state"}, {"state", state}}));
    emit(Json::object({{"type", "completed"}, {"key", "_refresh"}}));
    return;
  }
  if (!linked) {
    emit(Json::object({{"type", "completed"}, {"key", "_refresh"}}));
    return;
  }
  for (const char *name :
       {"battery", "anc", "eq", "low_latency", "bass", "spatial", "in_ear",
        "dual", "codec", "firmware", "model"}) {
    std::string key = name;
    if (refresh_keys.count(key))
      continue;
    refresh_keys.insert(key);
    enqueue(reads.at(key), 0.6, [this, key](std::optional<Frame>) {
      refresh_keys.erase(key);
      if (refresh_keys.empty())
        emit(Json::object({{"type", "completed"}, {"key", "_refresh"}}));
    });
  }
}
void Bluetooth::write(const std::string &key, const Json &value) {
  try {
    auto command = write_command(key, value);
    if (!linked)
      throw std::runtime_error("Connect your earbuds first.");
    auto model = state.get("model").str();
    if (model != "B172" && model != "B187")
      throw std::runtime_error(
          "Writes require a confirmed CMF Buds Pro 2 model.");
    if (key != "find" && !state.has(key))
      throw std::runtime_error("The earbuds have not reported this setting.");
    if (pending_keys.count(key) && key != "find")
      throw std::runtime_error("This setting is still being confirmed.");
    if (demo) {
      if (key != "find")
        state.set(key, value);
      emit(Json::object({{"type", "state"}, {"state", state}}));
      finish_write(key, value, true);
      return;
    }
    pending_keys.insert(key);
    enqueue(
        std::move(command), 0.16,
        [this, key, value](std::optional<Frame>) {
          if (key == "find") {
            int side = value.at(0).number();
            if (value.at(1).boolean())
              ringing[side] = Clock::now() + std::chrono::seconds(15);
            else
              ringing.erase(side);
            finish_write(key, value, true);
          } else if (state.get(key) == value)
            finish_write(key, value, true);
          else
            verify(key, value, 0);
        },
        true);
  } catch (const std::exception &error) {
    message(error.what(), true);
    emit(Json::object({{"type", "completed"}, {"key", key}}));
  }
}
void Bluetooth::verify(const std::string &key, const Json &value, int attempt) {
  enqueue(
      reads.at(key), attempt ? 0.6 : 0.35,
      [this, key, value, attempt](std::optional<Frame>) {
        if (state.get(key) == value)
          finish_write(key, value, true);
        else if (attempt == 0)
          verify(key, value, 1);
        else
          finish_write(key, value, false);
      },
      true);
}
void Bluetooth::finish_write(const std::string &key, const Json &,
                             bool confirmed) {
  pending_keys.erase(key);
  if (confirmed)
    message(key == "find" ? "Locator updated" : "Updated");
  else
    message("The earbuds did not confirm this setting. Showing the last "
            "reported value.",
            true);
  emit(Json::object({{"type", "completed"}, {"key", key}}));
}
void Bluetooth::start_demo() {
  disconnect(false);
  demo = linked = true;
  state = Json::parse(
      R"({"model":"B172","battery":{"left":{"level":92,"charging":false},"right":{"level":88,"charging":false},"case":{"level":76,"charging":false}},"anc":"Adaptive","eq":"Dirac Opteo","in_ear":true,"low_latency":false,"spatial":false,"bass":[true,3],"dual":true,"codec":0,"firmware":"Demo · 0.0.0"})");
  emit(Json::object({{"type", "state"}, {"state", state}}));
  status("demo", "Demo mode");
}
