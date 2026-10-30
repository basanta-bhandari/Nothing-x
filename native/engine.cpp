#include "protocol.hpp"
#include <chrono>
#include <cstdlib>
#include <cstring>

struct Engine {
  Json state = Json::object();
  Json profiles = Json::object();
  std::vector<uint8_t> buffer;
  void apply(const Frame &frame) {
    auto update = parse_frame(frame);
    auto profile = profiles.get(state.get("model").str());
    if ((frame.command == 0xC050 || frame.command == 0xC01F) &&
        !frame.payload.empty() && !profile.null()) {
      int offset = profile.get("eq_index").number();
      int value =
          frame.payload[frame.payload.size() > size_t(offset) ? offset : 0];
      std::string name = "Device preset " + std::to_string(value);
      for (const auto &preset : profile.get("eq_presets").items())
        if (preset.get("value").number() == value)
          name = preset.get("name").str();
      update.set("eq", name);
    }
    if (update.has("battery")) {
      auto battery = state.get("battery").null() ? Json::object()
                                                 : state.get("battery").clone();
      for (const char *part : {"left", "right", "case", "headphone"}) {
        auto value = update.get("battery").get(part);
        if (!value.null()) {
          value.set("available", true);
          battery.set(part, value);
        } else if (update.get("battery").has(part) ||
                   (frame.command == 0xC007 && std::string(part) == "case")) {
          auto previous = battery.get(part);
          if (!previous.null()) {
            previous.set("available", false);
            battery.set(part, previous);
          }
        }
      }
      update.set("battery", battery);
    }
    for (const char *key :
         {"model", "battery", "anc", "eq", "in_ear", "low_latency", "spatial",
          "bass", "dual", "codec", "firmware"})
      if (update.has(key))
        state.set(key, update.get(key));
    auto model = state.get("model").str();
    if (!model.empty()) {
      auto profile = profiles.get(model);
      state.set("device", profile.null()
                              ? Json::object({{"id", model},
                                              {"name", "Nothing audio device"},
                                              {"kind", "unknown"},
                                              {"features", Json::array()}})
                              : profile);
      state.set("capabilities", profile.get("features").null()
                                    ? Json::array()
                                    : profile.get("features"));
    }
  }
  Json call(const Json &request) {
    auto op = request.get("op").str();
    if (op == "configure") {
      profiles = request.get("profiles").clone();
      return Json::object();
    }
    if (op == "reset") {
      state = Json::object();
      buffer.clear();
      return state;
    }
    if (op == "state")
      return state;
    if (op == "feed") {
      for (const auto &item : request.get("bytes").items()) {
        if (!item.is(json_type_int) || item.number() < 0 || item.number() > 255)
          throw std::runtime_error("Invalid packet bytes");
        buffer.push_back(uint8_t(item.number()));
      }
      if (buffer.size() > 65536) {
        buffer.clear();
        throw std::runtime_error("Packet buffer limit exceeded");
      }
      auto frames = Json::array();
      for (const auto &frame : decode(buffer)) {
        apply(frame);
        auto payload = Json::array();
        for (auto byte : frame.payload)
          payload.push(int(byte));
        frames.push(Json::object({{"command", int(frame.command)},
                                  {"sequence", int(frame.sequence)},
                                  {"payload", payload}}));
      }
      return Json::object({{"frames", frames}, {"state", state}});
    }
    if (op == "packet" || op == "read" || op == "write") {
      auto profile = profiles.get(state.get("model").str());
      Command command;
      if (op == "packet") {
        int id = request.get("command").number(-1);
        if (id < 0 || id > 65535)
          throw std::runtime_error("Invalid command");
        command.command = id;
        for (const auto &item : request.get("payload").items()) {
          if (!item.is(json_type_int) || item.number() < 0 ||
              item.number() > 255)
            throw std::runtime_error("Invalid payload");
          command.payload.push_back(item.number());
        }
      } else if (op == "read") {
        auto key = request.get("key").str();
        if (!reads.count(key))
          throw std::runtime_error("Unknown read setting");
        command = reads.at(key);
        if (key == "eq" && !profile.null())
          command.command = profile.get("eq_read").number(0xC050);
      } else {
        auto key = request.get("key").str();
        auto value = request.get("value");
        bool allowed = false;
        for (const auto &feature : profile.get("features").items())
          if (feature.str() == key)
            allowed = true;
        if (!allowed)
          throw std::runtime_error("This model does not support that control");
        if (key != "find" && !state.has(key))
          throw std::runtime_error("The device has not reported this setting");
        if (key == "anc") {
          bool mode = false;
          for (const auto &choice : profile.get("anc_modes").items())
            if (choice == value)
              mode = true;
          if (!mode)
            throw std::runtime_error("Noise mode not supported by this model");
        }
        if (key == "bass" &&
            value.at(1).real() > profile.get("bass_max").real(5))
          throw std::runtime_error("Bass level outside this model's range");
        if (key == "eq") {
          bool found = false;
          for (const auto &preset : profile.get("eq_presets").items())
            if (preset.get("name") == value) {
              command = {uint16_t(profile.get("eq_write").number()),
                         {uint8_t(preset.get("value").number()), 0}};
              found = true;
            }
          if (!found)
            throw std::runtime_error(
                "Equalizer preset not supported by this model");
        } else {
          command = write_command(key, value);
          if (key == "find") {
            bool single = profile.get("kind").str() != "earbuds";
            if ((single && value.at(0).number() != 6) ||
                (!single && value.at(0).number() == 6))
              throw std::runtime_error("Invalid locator target for this model");
            if (profile.get("ring_legacy").boolean())
              command.payload = {uint8_t(value.at(1).boolean())};
          }
        }
      }
      int sequence = request.get("sequence").number(1);
      if (sequence < 1 || sequence > 255)
        throw std::runtime_error("Invalid packet sequence");
      auto bytes = Json::array();
      for (auto byte : encode(command, sequence))
        bytes.push(int(byte));
      return Json::object(
          {{"command", int(command.command)}, {"bytes", bytes}});
    }
    throw std::runtime_error("Unknown engine operation");
  }
};
extern "C" {
void *nx_engine_create() {
  try {
    return new Engine;
  } catch (...) {
    return nullptr;
  }
}
void nx_engine_destroy(void *engine) { delete static_cast<Engine *>(engine); }
void nx_engine_free(char *text) { std::free(text); }
char *nx_engine_call(void *context, const char *input) {
  Json result;
  try {
    if (!context || !input)
      throw std::runtime_error("Invalid engine context");
    result = Json::object(
        {{"ok", true},
         {"result", static_cast<Engine *>(context)->call(Json::parse(input))}});
  } catch (const std::exception &error) {
    result = Json::object({{"ok", false}, {"error", error.what()}});
  }
  auto text = result.dump();
  auto *output = static_cast<char *>(std::malloc(text.size() + 1));
  if (output)
    std::memcpy(output, text.c_str(), text.size() + 1);
  return output;
}
}
