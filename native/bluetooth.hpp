#pragma once
#include "protocol.hpp"
#include <chrono>
#include <deque>
#include <functional>
#include <gio/gio.h>
#include <map>
#include <set>

using Clock = std::chrono::steady_clock;
using Emit = std::function<void(const Json &)>;
class Bluetooth {
  struct Request {
    Command command;
    double timeout;
    std::function<void(std::optional<Frame>)> done;
    uint8_t sequence = 0;
    Clock::time_point deadline;
    bool urgent = false;
  };
  Emit emit;
  int fd = -1;
  guint input_watch = 0, output_watch = 0, connect_watch = 0, timer = 0;
  bool opening = false, linked = false, demo = false, dispatching = false;
  std::string address;
  std::vector<int> candidates;
  size_t candidate_index = 0;
  std::map<std::string, int> channels;
  Clock::time_point connect_deadline, last_poll = Clock::now();
  uint8_t sequence = 0;
  std::vector<uint8_t> buffer, output;
  std::deque<Request> requests;
  std::optional<Request> active;
  std::set<std::string> refresh_keys;
  std::set<std::string> pending_keys;
  std::map<int, Clock::time_point> ringing;
  Json state = Json::object();
  void status(const char *phase, const std::string &detail);
  void message(const std::string &detail, bool error = false);
  void close_socket();
  void next_channel();
  void established();
  void failed(const std::string &detail);
  void enqueue(Command command, double timeout,
               std::function<void(std::optional<Frame>)> done = {},
               bool priority = false);
  void pump();
  void flush();
  void complete(std::optional<Frame> response);
  void receive();
  void apply(const Frame &frame);
  void verify(const std::string &key, const Json &value, int attempt);
  void finish_write(const std::string &key, const Json &value, bool confirmed);

public:
  explicit Bluetooth(Emit output);
  ~Bluetooth();
  bool connected() const { return linked; }
  bool connecting() const { return opening; }
  std::string current_address() const { return address; }
  void connect(const std::string &mac, int channel = 0);
  void disconnect(bool notify = true);
  void refresh();
  void write(const std::string &key, const Json &value);
  void start_demo();
};
