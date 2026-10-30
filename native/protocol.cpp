#include "protocol.hpp"
#include <algorithm>
#include <cmath>

uint16_t crc16(const std::vector<uint8_t> &bytes, size_t length) {
  uint16_t crc = 0xffff;
  for (size_t i = 0; i < length; ++i) {
    crc ^= bytes[i];
    for (int bit = 0; bit < 8; ++bit)
      crc = (crc >> 1) ^ ((crc & 1) ? 0xa001 : 0);
  }
  return crc;
}
std::vector<uint8_t> encode(const Command &command, uint8_t sequence) {
  if (command.payload.size() > 4096)
    throw std::runtime_error("Payload too large");
  const auto size = command.payload.size();
  std::vector<uint8_t> result{0x55,
                              0x60,
                              0x01,
                              uint8_t(command.command),
                              uint8_t(command.command >> 8),
                              uint8_t(size),
                              uint8_t(size >> 8),
                              sequence};
  result.insert(result.end(), command.payload.begin(), command.payload.end());
  auto crc = crc16(result, result.size());
  result.push_back(uint8_t(crc));
  result.push_back(uint8_t(crc >> 8));
  return result;
}
std::vector<Frame> decode(std::vector<uint8_t> &buffer) {
  std::vector<Frame> result;
  while (!buffer.empty()) {
    if (buffer[0] != 0x55) {
      buffer.erase(buffer.begin());
      continue;
    }
    if (buffer.size() < 8)
      break;
    uint16_t control = buffer[1] | (buffer[2] << 8),
             length = buffer[5] | (buffer[6] << 8);
    if (length > 4096 || (control & 0xff00) > 0x0100) {
      buffer.erase(buffer.begin());
      continue;
    }
    size_t end = 8 + length, total = end + ((control & 0x20) ? 2 : 0);
    if (buffer.size() < total)
      break;
    if ((control & 0x20) &&
        crc16(buffer, end) != (buffer[end] | (buffer[end + 1] << 8))) {
      buffer.erase(buffer.begin());
      continue;
    }
    result.push_back({uint16_t((buffer[3] | (buffer[4] << 8)) | 0x8000),
                      buffer[7],
                      {buffer.begin() + 8, buffer.begin() + end}});
    buffer.erase(buffer.begin(), buffer.begin() + total);
  }
  return result;
}
Json parse_frame(const Frame &frame) {
  auto result = Json::object();
  const auto &p = frame.payload;
  auto cmd = frame.command;
  if (cmd == 0xC007 || cmd == 0xE001) {
    auto battery = Json::object();
    if (p.empty() || p.size() < size_t(1 + 2 * p[0]))
      return result;
    for (size_t i = 1; i < size_t(1 + 2 * p[0]); i += 2) {
      std::string part = p[i] == 2   ? "left"
                         : p[i] == 3 ? "right"
                         : p[i] == 4 ? "case"
                         : p[i] == 6 ? "headphone"
                                     : "";
      if (part.empty())
        continue;
      int level = p[i + 1] & 0x7f;
      battery.set(part,
                  level <= 100
                      ? Json::object({{"level", level},
                                      {"charging", bool(p[i + 1] & 0x80)}})
                      : Json());
    }
    result.set("battery", battery);
  } else if (cmd == 0xC01E || cmd == 0xE003) {
    std::map<int, int> entries;
    for (size_t i = 0; i + 2 < p.size(); i += 3)
      entries[p[i]] = p[i + 1];
    int mode = entries[1];
    if (mode >= 1 && mode <= 4 && entries[2] >= 1 && entries[2] <= 4)
      mode = entries[2];
    for (const auto &[name, id] : anc_modes)
      if (id == mode)
        result.set("anc", name);
  } else if (cmd == 0xC050 && !p.empty()) {
    int value = p.size() > 1 ? p[1] : p[0];
    std::string name = "Device preset " + std::to_string(value);
    for (const auto &[title, id] : eq_modes)
      if (id == value)
        name = title;
    result.set("eq", name);
  } else if (cmd == 0xC00E && !p.empty() && p.size() >= size_t(1 + 2 * p[0])) {
    for (size_t i = 1; i < size_t(1 + 2 * p[0]); i += 2)
      if (p[i] == 1 && p[i + 1] <= 1)
        result.set("in_ear", bool(p[i + 1]));
  } else if (cmd == 0xC041 && !p.empty() && (p[0] == 1 || p[0] == 2))
    result.set("low_latency", p[0] == 1);
  else if (cmd == 0xC04F && !p.empty() && p[0] <= 1)
    result.set("spatial", bool(p[0]));
  else if (cmd == 0xC04E && p.size() >= 2 && p[0] <= 1 && p[1] <= 10)
    result.set("bass", Json::array({bool(p[0]), p[1] / 2.0}));
  else if (cmd == 0xC029 && !p.empty() && p[0] <= 2)
    result.set("codec", int(p[0]));
  else if (cmd == 0xC027 && !p.empty() && p[0] <= 1)
    result.set("dual", bool(p[0]));
  else if (cmd == 0xC042 && !p.empty()) {
    std::string firmware(p.begin(), p.end());
    firmware.erase(std::find(firmware.begin(), firmware.end(), '\0'),
                   firmware.end());
    result.set("firmware", firmware);
  } else if (cmd == 0xC01C && !p.empty()) {
    if (p == std::vector<uint8_t>{0x72, 0xb1})
      result.set("model", "B172");
    else if (p == std::vector<uint8_t>{0x87, 0xb1})
      result.set("model", "B187");
    else {
      std::string model(p.begin(), p.end());
      if (model.find("B172") != std::string::npos)
        model = "B172";
      else if (model.find("B187") != std::string::npos)
        model = "B187";
      result.set("model", model);
    }
  }
  return result;
}
Command write_command(const std::string &key, const Json &value) {
  if (key == "anc" && anc_modes.count(value.str()))
    return {0xF00F, {1, uint8_t(anc_modes.at(value.str())), 0}};
  if (key == "eq" && eq_modes.count(value.str()))
    return {0xF01D, {uint8_t(eq_modes.at(value.str())), 0}};
  if (value.is(json_type_boolean)) {
    uint8_t b = value.boolean();
    if (key == "spatial")
      return {0xF052, {b, 0}};
    if (key == "in_ear")
      return {0xF004, {1, 1, b}};
    if (key == "low_latency")
      return {0xF040, {uint8_t(b ? 1 : 2), 0}};
    if (key == "dual")
      return {0xF01A, {b}};
  }
  if (key == "bass" && value.size() == 2 && value.at(0).is(json_type_boolean) &&
      (value.at(1).is(json_type_int) || value.at(1).is(json_type_double))) {
    double level = value.at(1).real();
    if (level >= 0 && level <= 5 && std::floor(level * 2) == level * 2)
      return {0xF051, {uint8_t(value.at(0).boolean()), uint8_t(level * 2)}};
  }
  if (key == "codec" && value.is(json_type_int) &&
      (value.number() == 0 || value.number() == 2))
    return {0xF01C, {uint8_t(value.number())}};
  if (key == "find" && value.size() == 2 && value.at(0).is(json_type_int) &&
      (value.at(0).number() == 2 || value.at(0).number() == 3) &&
      value.at(1).is(json_type_boolean))
    return {0xF002,
            {uint8_t(value.at(0).number()), uint8_t(value.at(1).boolean())}};
  throw std::runtime_error("Invalid value for " + key);
}
