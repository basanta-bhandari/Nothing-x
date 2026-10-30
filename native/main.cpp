#include "audio.hpp"
#include <cerrno>
#include <fcntl.h>
#include <glib-unix.h>
#include <iostream>
#include <signal.h>
#include <unistd.h>

class Application {
  GMainLoop *loop;
  GDBusConnection *bus = nullptr;
  guint stdin_watch = 0, signal_watch = 0, retry_timer = 0, bluez_signal = 0,
        discovery_timer = 0;
  bool discovering = false, auto_connect = false, desired = false;
  std::string input, address;
  Clock::time_point next_retry = Clock::now();
  Bluetooth bluetooth;
  Audio audio;

public:
  explicit Application(bool automatic)
      : loop(g_main_loop_new(nullptr, false)), auto_connect(automatic),
        desired(automatic), bluetooth([this](const Json &event) {
          output(event);
          if (event.get("type").str() == "status" &&
              event.get("phase").str() == "disconnected")
            next_retry = Clock::now() + std::chrono::seconds(15);
        }),
        audio([this](const Json &event) { output(event); }) {
    ::signal(SIGPIPE, SIG_IGN);
    fcntl(STDIN_FILENO, F_SETFL, fcntl(STDIN_FILENO, F_GETFL) | O_NONBLOCK);
    stdin_watch = g_unix_fd_add(
        STDIN_FILENO, GIOCondition(G_IO_IN | G_IO_HUP | G_IO_ERR),
        [](gint, GIOCondition condition, gpointer data) -> gboolean {
          auto &self = *static_cast<Application *>(data);
          char bytes[4096];
          while (true) {
            ssize_t count = ::read(STDIN_FILENO, bytes, sizeof(bytes));
            if (count > 0)
              self.input.append(bytes, count);
            else if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
              break;
            else {
              self.stdin_watch = 0;
              g_main_loop_quit(self.loop);
              return G_SOURCE_REMOVE;
            }
            if (self.input.size() > 1024 * 1024) {
              self.stdin_watch = 0;
              g_main_loop_quit(self.loop);
              return G_SOURCE_REMOVE;
            }
            size_t end;
            while ((end = self.input.find('\n')) != std::string::npos) {
              auto line = self.input.substr(0, end);
              self.input.erase(0, end + 1);
              try {
                self.command(Json::parse(line));
              } catch (const std::exception &error) {
                self.output(Json::object({{"type", "message"},
                                          {"text", error.what()},
                                          {"error", true}}));
              }
            }
          }
          if (condition & (G_IO_HUP | G_IO_ERR)) {
            self.stdin_watch = 0;
            g_main_loop_quit(self.loop);
            return G_SOURCE_REMOVE;
          }
          return G_SOURCE_CONTINUE;
        },
        this);
    signal_watch = g_unix_signal_add(
        SIGTERM,
        [](gpointer data) -> gboolean {
          auto &self = *static_cast<Application *>(data);
          g_main_loop_quit(self.loop);
          return G_SOURCE_CONTINUE;
        },
        this);
    retry_timer = g_timeout_add_seconds(
        3,
        [](gpointer data) -> gboolean {
          auto &self = *static_cast<Application *>(data);
          if (self.desired && !self.bluetooth.connected() &&
              !self.bluetooth.connecting() && Clock::now() >= self.next_retry)
            self.discover();
          return G_SOURCE_CONTINUE;
        },
        this);
    g_bus_get(
        G_BUS_TYPE_SYSTEM, nullptr,
        [](GObject *, GAsyncResult *result, gpointer data) {
          auto &self = *static_cast<Application *>(data);
          GError *error = nullptr;
          self.bus = g_bus_get_finish(result, &error);
          if (!self.bus) {
            if (error)
              g_error_free(error);
            self.output(Json::object(
                {{"type", "devices"}, {"devices", Json::array()}}));
            return;
          }
          self.bluez_signal = g_dbus_connection_signal_subscribe(
              self.bus, "org.bluez", "org.freedesktop.DBus.Properties",
              "PropertiesChanged", nullptr, "org.bluez.Device1",
              G_DBUS_SIGNAL_FLAGS_NONE,
              [](GDBusConnection *, const gchar *, const gchar *, const gchar *,
                 const gchar *, GVariant *, gpointer data) {
                auto &self = *static_cast<Application *>(data);
                if (!self.discovery_timer)
                  self.discovery_timer = g_timeout_add(
                      150,
                      [](gpointer data) -> gboolean {
                        auto &self = *static_cast<Application *>(data);
                        self.discovery_timer = 0;
                        self.discover();
                        return G_SOURCE_REMOVE;
                      },
                      &self);
              },
              &self, nullptr);
          self.discover();
        },
        this);
    output(Json::object(
        {{"type", "ready"}, {"backend", "C++"}, {"version", "0.3.0"}}));
  }
  ~Application() {
    bluetooth.disconnect(false);
    for (auto id : {stdin_watch, signal_watch, retry_timer, discovery_timer})
      if (id)
        g_source_remove(id);
    if (bus) {
      if (bluez_signal)
        g_dbus_connection_signal_unsubscribe(bus, bluez_signal);
      g_object_unref(bus);
    }
    g_main_loop_unref(loop);
  }
  void output(const Json &event) {
    std::cout << event.dump() << '\n' << std::flush;
    if (!std::cout)
      g_main_loop_quit(loop);
  }
  void discover() {
    if (!bus || discovering)
      return;
    discovering = true;
    g_dbus_connection_call(
        bus, "org.bluez", "/", "org.freedesktop.DBus.ObjectManager",
        "GetManagedObjects", nullptr, G_VARIANT_TYPE("(a{oa{sa{sv}}})"),
        G_DBUS_CALL_FLAGS_NONE, 2500, nullptr,
        [](GObject *object, GAsyncResult *result, gpointer data) {
          auto &self = *static_cast<Application *>(data);
          self.discovering = false;
          GError *error = nullptr;
          GVariant *reply = g_dbus_connection_call_finish(
              G_DBUS_CONNECTION(object), result, &error);
          auto devices = Json::array();
          std::vector<std::string> matches;
          bool selected_connected = false;
          if (reply) {
            GVariant *objects = g_variant_get_child_value(reply, 0);
            GVariantIter iter;
            g_variant_iter_init(&iter, objects);
            const gchar *path;
            GVariant *interfaces;
            while (g_variant_iter_next(&iter, "{&o@a{sa{sv}}}", &path,
                                       &interfaces)) {
              GVariant *properties = g_variant_lookup_value(
                  interfaces, "org.bluez.Device1", G_VARIANT_TYPE("a{sv}"));
              if (properties) {
                gboolean paired = false, connected = false;
                const gchar *mac = "";
                const gchar *name = "";
                g_variant_lookup(properties, "Paired", "b", &paired);
                g_variant_lookup(properties, "Connected", "b", &connected);
                g_variant_lookup(properties, "Address", "&s", &mac);
                if (!g_variant_lookup(properties, "Alias", "&s", &name))
                  g_variant_lookup(properties, "Name", "&s", &name);
                if (paired) {
                  devices.push(Json::array({mac, name}));
                  std::string title = name;
                  std::transform(
                      title.begin(), title.end(), title.begin(),
                      [](unsigned char c) { return std::tolower(c); });
                  if (connected && title.find("cmf") != std::string::npos &&
                      title.find("pro 2") != std::string::npos)
                    matches.emplace_back(mac);
                  if (connected && self.address == mac)
                    selected_connected = true;
                }
                g_variant_unref(properties);
              }
              g_variant_unref(interfaces);
            }
            g_variant_unref(objects);
            g_variant_unref(reply);
          }
          if (error)
            g_error_free(error);
          self.output(
              Json::object({{"type", "devices"}, {"devices", devices}}));
          if (self.desired && !self.bluetooth.connected() &&
              !self.bluetooth.connecting() && Clock::now() >= self.next_retry) {
            if (self.address.empty() && matches.size() == 1) {
              self.address = matches.front();
              selected_connected = true;
            }
            if (selected_connected) {
              self.audio.set_address(self.address);
              self.next_retry = Clock::now() + std::chrono::seconds(15);
              try {
                self.bluetooth.connect(self.address);
              } catch (const std::exception &error) {
                self.output(Json::object({{"type", "message"},
                                          {"text", error.what()},
                                          {"error", true}}));
              }
            }
          }
        },
        this);
  }
  void command(const Json &request) {
    if (!request.is(json_type_object))
      throw std::runtime_error("Invalid backend request.");
    auto action = request.get("action").str();
    if (action == "quit") {
      bluetooth.disconnect(false);
      g_main_loop_quit(loop);
    } else if (action == "devices")
      discover();
    else if (action == "demo") {
      desired = false;
      bluetooth.start_demo();
    } else if (action == "connect") {
      auto mac = request.get("address").str();
      desired = true;
      next_retry = Clock::now();
      if (!mac.empty()) {
        address = mac;
        audio.set_address(mac);
        bluetooth.connect(mac, request.get("channel").number());
      } else
        discover();
    } else if (action == "disconnect") {
      desired = false;
      bluetooth.disconnect();
    } else if (action == "refresh") {
      bluetooth.refresh();
      audio.refresh();
    } else if (action == "write")
      bluetooth.write(request.get("key").str(), request.get("value"));
    else if (action == "audio") {
      if (request.get("key").str() == "address") {
        address = request.get("value").str();
        audio.set_address(address);
      } else {
        try {
          audio.command(request.get("key").str(), request.get("value"),
                        request.get("target").str());
        } catch (const std::exception &error) {
          output(Json::object(
              {{"type", "audio_completed"}, {"key", request.get("key")}}));
          throw;
        }
      }
    } else
      throw std::runtime_error("Unsupported backend request.");
  }
  int run() {
    g_main_loop_run(loop);
    return 0;
  }
};
int main(int argc, char **argv) {
  if (argc > 1 && std::string(argv[1]) == "--version") {
    std::cout << "nothingx-core 0.3.0 (C++20)\n";
    return 0;
  }
  try {
    Application application(argc > 1 && std::string(argv[1]) == "--auto");
    return application.run();
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
