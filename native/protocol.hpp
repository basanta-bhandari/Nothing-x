#pragma once
#include "json.hpp"
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>

struct Frame {
  uint16_t command;
  uint8_t sequence;
  std::vector<uint8_t> payload;
};
struct Command {
  uint16_t command;
  std::vector<uint8_t> payload;
};
inline const std::map<std::string, int> anc_modes{
    {"High", 1},     {"Mid", 2}, {"Low", 3},
    {"Adaptive", 4}, {"Off", 5}, {"Transparency", 7}};
inline const std::map<std::string, int> eq_modes{
    {"Dirac Opteo", 0}, {"Rock", 1},           {"Electronic", 2},
    {"Pop", 3},         {"Enhance vocals", 4}, {"Classical", 5}};
inline const std::map<std::string, Command> reads{
    {"model", {0xC01C, {}}},   {"battery", {0xC007, {}}},
    {"anc", {0xC01E, {3}}},    {"eq", {0xC050, {}}},
    {"in_ear", {0xC00E, {}}},  {"low_latency", {0xC041, {}}},
    {"spatial", {0xC04F, {}}}, {"bass", {0xC04E, {}}},
    {"dual", {0xC027, {}}},    {"codec", {0xC029, {}}},
    {"firmware", {0xC042, {}}}};
uint16_t crc16(const std::vector<uint8_t> &bytes, size_t length);
std::vector<uint8_t> encode(const Command &command, uint8_t sequence);
std::vector<Frame> decode(std::vector<uint8_t> &buffer);
Json parse_frame(const Frame &frame);
Command write_command(const std::string &key, const Json &value);
