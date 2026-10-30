#include "protocol.hpp"
#include <chrono>
#include <cstdlib>
#include <cstring>

struct Engine {
  Json state = Json::object();
  std::vector<uint8_t> buffer;
  void apply(const Frame &frame) {
    auto update = parse_frame(frame);
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
  }
  Json call(const Json &request) {
    auto op = request.get("op").str();
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
      } else {
        auto model = state.get("model").str();
        if (model != "B172" && model != "B187")
          throw std::runtime_error("Device model is not configured for writes");
        auto key = request.get("key").str();
        if (key != "find" && !state.has(key))
          throw std::runtime_error("The device has not reported this setting");
        command = write_command(key, request.get("value"));
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
