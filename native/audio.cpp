#include "audio.hpp"
#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstring>

static std::string prop(pa_proplist *properties, const char *key) {
  auto *value = properties ? pa_proplist_gets(properties, key) : nullptr;
  return value ? value : "";
}
static std::string upper(std::string text) {
  std::transform(text.begin(), text.end(), text.begin(),
                 [](unsigned char c) { return std::toupper(c); });
  return text;
}
static void release(pa_operation *operation) {
  if (operation)
    pa_operation_unref(operation);
}
Audio::Audio(Emit output) : emit(std::move(output)) {
  mainloop = pa_glib_mainloop_new(nullptr);
  connect_server();
  wireplumber();
}
Audio::~Audio() {
  if (refresh_timer)
    g_source_remove(refresh_timer);
  if (reconnect_timer)
    g_source_remove(reconnect_timer);
  if (context) {
    pa_context_disconnect(context);
    pa_context_unref(context);
  }
  if (mainloop)
    pa_glib_mainloop_free(mainloop);
}
void Audio::connect_server() {
  if (context) {
    pa_context_set_state_callback(context, nullptr, nullptr);
    pa_context_disconnect(context);
    pa_context_unref(context);
  }
  ready = false;
  querying = false;
  remaining = 0;
  context = pa_context_new(pa_glib_mainloop_get_api(mainloop), "Nothing X");
  pa_context_set_state_callback(
      context,
      [](pa_context *context, void *data) {
        auto &self = *static_cast<Audio *>(data);
        switch (pa_context_get_state(context)) {
        case PA_CONTEXT_READY:
          self.ready = true;
          pa_context_set_subscribe_callback(
              context,
              [](pa_context *, pa_subscription_event_type_t, uint32_t,
                 void *data) { static_cast<Audio *>(data)->schedule(); },
              &self);
          release(pa_context_subscribe(
              context,
              pa_subscription_mask_t(
                  PA_SUBSCRIPTION_MASK_SINK | PA_SUBSCRIPTION_MASK_SOURCE |
                  PA_SUBSCRIPTION_MASK_SINK_INPUT |
                  PA_SUBSCRIPTION_MASK_SOURCE_OUTPUT |
                  PA_SUBSCRIPTION_MASK_CARD | PA_SUBSCRIPTION_MASK_SERVER),
              nullptr, nullptr));
          self.refresh();
          break;
        case PA_CONTEXT_FAILED:
        case PA_CONTEXT_TERMINATED:
          self.ready = false;
          self.querying = false;
          self.state =
              Json::object({{"available", false},
                            {"error", "PipeWire audio server unavailable"}});
          self.emit(Json::object({{"type", "audio"}, {"state", self.state}}));
          if (!self.reconnect_timer)
            self.reconnect_timer = g_timeout_add_seconds(
                3,
                [](gpointer data) -> gboolean {
                  auto &self = *static_cast<Audio *>(data);
                  self.reconnect_timer = 0;
                  self.connect_server();
                  return G_SOURCE_REMOVE;
                },
                &self);
          break;
        default:
          break;
        }
      },
      this);
  if (pa_context_connect(context, nullptr, PA_CONTEXT_NOAUTOSPAWN, nullptr) <
      0) {
    state = Json::object(
        {{"available", false},
         {"error", "Cannot connect to PipeWire. Start pipewire-pulse."}});
    emit(Json::object({{"type", "audio"}, {"state", state}}));
  }
}
void Audio::schedule() {
  if (!refresh_timer)
    refresh_timer = g_timeout_add(
        35,
        [](gpointer data) -> gboolean {
          auto &self = *static_cast<Audio *>(data);
          self.refresh_timer = 0;
          self.refresh();
          return G_SOURCE_REMOVE;
        },
        this);
}
void Audio::set_address(const std::string &mac) {
  address = upper(mac);
  schedule();
}
Json Audio::endpoint_data(uint32_t index, const char *name,
                          const char *description, const pa_cvolume &volume,
                          const pa_channel_map &channels, int mute,
                          pa_proplist *properties) {
  auto map = Json::array();
  for (unsigned i = 0; i < channels.channels; ++i)
    map.push(pa_channel_position_to_string(channels.map[i]));
  return Json::object(
      {{"index", index},
       {"name", name},
       {"description", description ? description : name},
       {"volume", int(std::lround(double(pa_cvolume_max(&volume)) * 100 /
                                  PA_VOLUME_NORM))},
       {"mute", bool(mute)},
       {"balance",
        int(std::lround(pa_cvolume_get_balance(&volume, &channels) * 100))},
       {"channels", map},
       {"codec", prop(properties, "api.bluez5.codec")},
       {"card_name", prop(properties, "device.name")}});
}
void Audio::refresh() {
  if (!ready)
    return;
  if (querying) {
    dirty = true;
    return;
  }
  querying = true;
  dirty = false;
  query_failed = false;
  remaining = 6;
  next = Snapshot{};
  release(pa_context_get_server_info(
      context,
      [](pa_context *, const pa_server_info *info, void *data) {
        auto &self = *static_cast<Audio *>(data);
        if (info)
          self.next.server =
              Json::object({{"server", info->server_name},
                            {"default_sink", info->default_sink_name},
                            {"default_source", info->default_source_name}});
        self.query_done(!info);
      },
      this));
  release(pa_context_get_card_info_list(
      context,
      [](pa_context *, const pa_card_info *info, int eol, void *data) {
        auto &self = *static_cast<Audio *>(data);
        if (eol) {
          self.query_done(eol < 0);
          return;
        }
        if (!info)
          return;
        if (prop(info->proplist, "device.api") != "bluez5")
          return;
        auto profiles = Json::array();
        if (info->profiles2)
          for (unsigned i = 0; i < info->n_profiles; ++i) {
            const auto *profile = info->profiles2[i];
            if (profile && profile->available != 0)
              profiles.push(
                  Json::object({{"name", profile->name},
                                {"description", profile->description}}));
          }
        self.next.cards.push(Json::object(
            {{"name", info->name},
             {"index", info->index},
             {"description", prop(info->proplist, "device.description")},
             {"address", upper(prop(info->proplist, "api.bluez5.address"))},
             {"profile", info->active_profile2  ? info->active_profile2->name
                         : info->active_profile ? info->active_profile->name
                                                : ""},
             {"profiles", profiles}}));
      },
      this));
  release(pa_context_get_sink_info_list(
      context,
      [](pa_context *, const pa_sink_info *info, int eol, void *data) {
        auto &self = *static_cast<Audio *>(data);
        if (eol) {
          self.query_done(eol < 0);
          return;
        }
        if (!info)
          return;
        auto value = endpoint_data(info->index, info->name, info->description,
                                   info->volume, info->channel_map, info->mute,
                                   info->proplist);
        value.set("running", info->state == PA_SINK_RUNNING);
        value.set("card_index", info->card);
        char sample[PA_SAMPLE_SPEC_SNPRINT_MAX];
        pa_sample_spec_snprint(sample, sizeof(sample), &info->sample_spec);
        value.set("sample", sample);
        self.next.sinks[info->name] = {value, info->volume, info->channel_map};
      },
      this));
  release(pa_context_get_source_info_list(
      context,
      [](pa_context *, const pa_source_info *info, int eol, void *data) {
        auto &self = *static_cast<Audio *>(data);
        if (eol) {
          self.query_done(eol < 0);
          return;
        }
        if (!info || info->monitor_of_sink != PA_INVALID_INDEX)
          return;
        auto value = endpoint_data(info->index, info->name, info->description,
                                   info->volume, info->channel_map, info->mute,
                                   info->proplist);
        self.next.sources[info->name] = {value, info->volume,
                                         info->channel_map};
      },
      this));
  release(pa_context_get_sink_input_info_list(
      context,
      [](pa_context *, const pa_sink_input_info *info, int eol, void *data) {
        auto &self = *static_cast<Audio *>(data);
        if (eol) {
          self.query_done(eol < 0);
          return;
        }
        if (!info || info->sink == PA_INVALID_INDEX)
          return;
        auto value =
            endpoint_data(info->index, "", "", info->volume, info->channel_map,
                          info->mute, info->proplist);
        auto name = prop(info->proplist, "application.name");
        if (name.empty())
          name = info->name ? info->name : "Audio stream";
        value.set("name", name);
        value.set("media", prop(info->proplist, "media.name"));
        value.set("kind", "playback");
        value.set("target", info->sink);
        value.set("paused", bool(info->corked));
        self.next.streams.push(value);
        self.next.streams_info["playback:" + std::to_string(info->index)] = {
            value, info->volume, info->channel_map};
      },
      this));
  release(pa_context_get_source_output_info_list(
      context,
      [](pa_context *, const pa_source_output_info *info, int eol, void *data) {
        auto &self = *static_cast<Audio *>(data);
        if (eol) {
          self.query_done(eol < 0);
          return;
        }
        if (!info || info->source == PA_INVALID_INDEX)
          return;
        auto value =
            endpoint_data(info->index, "", "", info->volume, info->channel_map,
                          info->mute, info->proplist);
        auto name = prop(info->proplist, "application.name");
        if (name.empty())
          name = info->name ? info->name : "Audio stream";
        value.set("name", name);
        value.set("media", prop(info->proplist, "media.name"));
        value.set("kind", "recording");
        value.set("target", info->source);
        value.set("paused", bool(info->corked));
        self.next.streams.push(value);
        self.next.streams_info["recording:" + std::to_string(info->index)] = {
            value, info->volume, info->channel_map};
      },
      this));
}
void Audio::query_done(bool failed) {
  if (!querying)
    return;
  query_failed |= failed;
  if (--remaining > 0)
    return;
  querying = false;
  if (!query_failed) {
    current = std::move(next);
    publish();
  }
  if (dirty)
    schedule();
}
void Audio::publish() {
  auto value = current.server.clone();
  value.set("available", true);
  value.set("auto_headset", auto_headset);
  auto sinks = Json::array(), sources = Json::array();
  for (const auto &[name, item] : current.sinks)
    sinks.push(item.data);
  for (const auto &[name, item] : current.sources)
    sources.push(item.data);
  value.set("sinks", sinks);
  value.set("sources", sources);
  value.set("streams", current.streams);
  Json card;
  for (const auto &item : current.cards.items()) {
    bool matches = !address.empty()
                       ? upper(item.get("address").str()) == address
                       : upper(item.get("description").str()).find("CMF") !=
                             std::string::npos;
    if (matches) {
      if (!card.null()) {
        card = Json();
        break;
      }
      card = item;
    }
  }
  value.set("card", card);
  Json sink;
  if (!card.null())
    for (const auto &[name, item] : current.sinks)
      if (item.data.get("card_index") == card.get("index")) {
        sink = item.data;
        break;
      }
  value.set("sink", sink);
  state = value;
  emit(Json::object({{"type", "audio"}, {"state", state}}));
}
void Audio::success(pa_context *context, int success, void *data) {
  std::unique_ptr<Operation> operation(static_cast<Operation *>(data));
  auto &self = *operation->self;
  if (!success)
    self.emit(
        Json::object({{"type", "message"},
                      {"text", std::string("Audio change failed: ") +
                                   pa_strerror(pa_context_errno(context))},
                      {"error", true}}));
  self.emit(
      Json::object({{"type", "audio_completed"}, {"key", operation->key}}));
  self.schedule();
}
void Audio::apply(pa_operation *operation, Operation *request) {
  if (operation)
    pa_operation_unref(operation);
  else {
    std::unique_ptr<Operation> cleanup(request);
    throw std::runtime_error("Audio server rejected the request.");
  }
}
void Audio::command(const std::string &action, const Json &value,
                    const std::string &target) {
  if (action == "refresh") {
    refresh();
    return;
  }
  if (!ready)
    throw std::runtime_error("Audio server unavailable.");
  auto card = state.get("card"), sink = state.get("sink");
  if (action == "auto_headset") {
    if (!value.is(json_type_boolean) || auto_headset.null())
      throw std::runtime_error("WirePlumber setting unavailable.");
    wireplumber(value.boolean());
    return;
  }
  auto request = std::make_unique<Operation>(Operation{this, action});
  pa_operation *operation = nullptr;
  auto callback = &Audio::success;
  auto percent = [&value]() {
    if (!value.is(json_type_int) || value.number() < 0 || value.number() > 100)
      throw std::runtime_error("Volume must be between 0 and 100%.");
    return pa_volume_t(
        std::lround(value.number() * double(PA_VOLUME_NORM) / 100));
  };
  auto boolean = [&value]() {
    if (!value.is(json_type_boolean))
      throw std::runtime_error("Invalid mute value.");
    return int(value.boolean());
  };
  if (action == "profile") {
    bool supported = false;
    for (const auto &profile : card.get("profiles").items())
      if (profile.get("name") == value)
        supported = true;
    if (!supported)
      throw std::runtime_error(
          "This Bluetooth profile is no longer available.");
    operation = pa_context_set_card_profile_by_name(
        context, card.get("name").str().c_str(), value.str().c_str(), callback,
        request.get());
  } else if (action == "output_volume" || action == "output_mute" ||
             action == "balance" || action == "default_output") {
    auto found = current.sinks.find(sink.get("name").str());
    if (found == current.sinks.end())
      throw std::runtime_error("Connect the earbuds' audio output first.");
    const auto &item = found->second;
    auto index = uint32_t(item.data.get("index").number());
    if (action == "output_mute")
      operation = pa_context_set_sink_mute_by_index(context, index, boolean(),
                                                    callback, request.get());
    else if (action == "default_output")
      operation = pa_context_set_default_sink(
          context, sink.get("name").str().c_str(), callback, request.get());
    else {
      auto volume = item.volume;
      if (action == "output_volume") {
        auto level = percent();
        if (pa_cvolume_max(&volume) == 0)
          pa_cvolume_set(&volume, volume.channels, level);
        else
          pa_cvolume_scale(&volume, level);
      } else {
        if (!value.is(json_type_int) || value.number() < -100 ||
            value.number() > 100 || !pa_channel_map_can_balance(&item.map))
          throw std::runtime_error("Balance is unavailable for this output.");
        pa_cvolume_set_balance(&volume, &item.map, value.number() / 100.0f);
      }
      operation = pa_context_set_sink_volume_by_index(context, index, &volume,
                                                      callback, request.get());
    }
  } else if (action == "default_input" || action == "input_volume" ||
             action == "input_mute") {
    auto found = current.sources.find(target);
    if (found == current.sources.end())
      throw std::runtime_error("This microphone is no longer available.");
    auto index = uint32_t(found->second.data.get("index").number());
    if (action == "default_input")
      operation = pa_context_set_default_source(context, target.c_str(),
                                                callback, request.get());
    else if (action == "input_mute")
      operation = pa_context_set_source_mute_by_index(context, index, boolean(),
                                                      callback, request.get());
    else {
      auto volume = found->second.volume;
      pa_cvolume_set(&volume, volume.channels, percent());
      operation = pa_context_set_source_volume_by_index(
          context, index, &volume, callback, request.get());
    }
  } else if (action == "stream_volume" || action == "stream_mute" ||
             action == "stream_route") {
    auto found = current.streams_info.find(target);
    if (found == current.streams_info.end())
      throw std::runtime_error("This application stream has closed.");
    const auto &item = found->second;
    auto index = uint32_t(item.data.get("index").number());
    bool playback = item.data.get("kind").str() == "playback";
    if (action == "stream_volume") {
      auto volume = item.volume;
      pa_cvolume_set(&volume, volume.channels, percent());
      operation =
          playback ? pa_context_set_sink_input_volume(context, index, &volume,
                                                      callback, request.get())
                   : pa_context_set_source_output_volume(
                         context, index, &volume, callback, request.get());
    } else if (action == "stream_mute")
      operation =
          playback ? pa_context_set_sink_input_mute(context, index, boolean(),
                                                    callback, request.get())
                   : pa_context_set_source_output_mute(
                         context, index, boolean(), callback, request.get());
    else {
      const auto &endpoints = playback ? current.sinks : current.sources;
      if (!endpoints.count(value.str()))
        throw std::runtime_error(
            "This audio destination is no longer available.");
      operation =
          playback
              ? pa_context_move_sink_input_by_name(context, index,
                                                   value.str().c_str(),
                                                   callback, request.get())
              : pa_context_move_source_output_by_name(context, index,
                                                      value.str().c_str(),
                                                      callback, request.get());
    }
  } else
    throw std::runtime_error("Unsupported audio setting.");
  apply(operation, request.release());
}
void Audio::wireplumber(const std::optional<bool> &value) {
  GError *error = nullptr;
  auto *launcher = g_subprocess_launcher_new(GSubprocessFlags(
      G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDERR_PIPE));
  if (g_getenv("NOTHINGX_BUNDLED")) {
    if (const char *original = g_getenv("LD_LIBRARY_PATH_ORIG"))
      g_subprocess_launcher_setenv(launcher, "LD_LIBRARY_PATH", original, true);
    else
      g_subprocess_launcher_unsetenv(launcher, "LD_LIBRARY_PATH");
  }
  GSubprocess *process =
      value ? g_subprocess_launcher_spawn(
                  launcher, &error, "wpctl", "settings", "--save",
                  "bluetooth.autoswitch-to-headset-profile",
                  *value ? "true" : "false", nullptr)
            : g_subprocess_launcher_spawn(
                  launcher, &error, "wpctl", "settings",
                  "bluetooth.autoswitch-to-headset-profile", nullptr);
  g_object_unref(launcher);
  if (!process) {
    if (error)
      g_error_free(error);
    return;
  }
  auto *operation = new std::pair<Audio *, bool>{this, value.has_value()};
  g_subprocess_communicate_utf8_async(
      process, nullptr, nullptr,
      [](GObject *source, GAsyncResult *result, gpointer data) {
        std::unique_ptr<std::pair<Audio *, bool>> operation(
            static_cast<std::pair<Audio *, bool> *>(data));
        auto &self = *operation->first;
        gchar *output = nullptr;
        gchar *errors = nullptr;
        GError *error = nullptr;
        bool okay =
            g_subprocess_communicate_utf8_finish(G_SUBPROCESS(source), result,
                                                 &output, &errors, &error) &&
            g_subprocess_get_successful(G_SUBPROCESS(source));
        if (operation->second) {
          if (!okay)
            self.emit(Json::object(
                {{"type", "message"},
                 {"text", errors ? errors : "WirePlumber change failed"},
                 {"error", true}}));
          self.emit(Json::object(
              {{"type", "audio_completed"}, {"key", "auto_headset"}}));
          self.wireplumber();
        } else if (okay && output) {
          std::string text = output;
          if (text.find("Value: true") != std::string::npos)
            self.auto_headset = true;
          else if (text.find("Value: false") != std::string::npos)
            self.auto_headset = false;
          if (self.ready)
            self.schedule();
        }
        g_free(output);
        g_free(errors);
        if (error)
          g_error_free(error);
        g_object_unref(source);
      },
      operation);
}
