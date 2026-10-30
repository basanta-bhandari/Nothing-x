#pragma once
#include "bluetooth.hpp"
#include <map>
#include <pulse/glib-mainloop.h>
#include <pulse/pulseaudio.h>

class Audio {
  struct Endpoint {
    Json data;
    pa_cvolume volume;
    pa_channel_map map;
  };
  struct Snapshot {
    Json cards = Json::array(), streams = Json::array(),
         server = Json::object();
    std::map<std::string, Endpoint> sinks, sources, streams_info;
  } next, current;
  struct Operation {
    Audio *self;
    std::string key;
  };
  Emit emit;
  pa_glib_mainloop *mainloop = nullptr;
  pa_context *context = nullptr;
  guint refresh_timer = 0, reconnect_timer = 0;
  bool ready = false, querying = false, dirty = false, query_failed = false;
  int remaining = 0;
  std::string address;
  Json state = Json::object();
  Json auto_headset;
  void connect_server();
  void query_done(bool failed = false);
  void publish();
  void schedule();
  void apply(pa_operation *operation, Operation *request);
  static void success(pa_context *, int, void *);
  static Json endpoint_data(uint32_t index, const char *name,
                            const char *description, const pa_cvolume &volume,
                            const pa_channel_map &channels, int mute,
                            pa_proplist *properties);
  void wireplumber(const std::optional<bool> &value = {});

public:
  explicit Audio(Emit output);
  ~Audio();
  void set_address(const std::string &mac);
  void refresh();
  void command(const std::string &action, const Json &value,
               const std::string &target);
};
