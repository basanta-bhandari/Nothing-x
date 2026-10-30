#pragma once
#include <json-c/json.h>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

class Json {
  std::shared_ptr<json_object> value;
  explicit Json(json_object *raw, bool retain)
      : value(retain && raw ? json_object_get(raw) : raw, json_object_put) {}

public:
  Json() = default;
  Json(const char *text)
      : Json(json_object_new_string(text ? text : ""), false) {}
  Json(const std::string &text) : Json(text.c_str()) {}
  Json(int number) : Json(json_object_new_int(number), false) {}
  Json(unsigned number) : Json(json_object_new_int64(number), false) {}
  Json(double number) : Json(json_object_new_double(number), false) {}
  Json(bool enabled) : Json(json_object_new_boolean(enabled), false) {}
  static Json object() { return Json(json_object_new_object(), false); }
  static Json array() { return Json(json_object_new_array(), false); }
  static Json
  object(std::initializer_list<std::pair<std::string, Json>> fields) {
    auto result = object();
    for (const auto &[key, item] : fields)
      result.set(key, item);
    return result;
  }
  static Json array(std::initializer_list<Json> fields) {
    auto result = array();
    for (const auto &item : fields)
      result.push(item);
    return result;
  }
  static Json parse(const std::string &text) {
    auto *tok = json_tokener_new();
    auto *raw = json_tokener_parse_ex(tok, text.data(), int(text.size()));
    bool valid = json_tokener_get_error(tok) == json_tokener_success;
    json_tokener_free(tok);
    if (!valid) {
      if (raw)
        json_object_put(raw);
      throw std::runtime_error("Invalid JSON request");
    }
    return Json(raw, false);
  }
  json_object *raw() const { return value.get(); }
  bool null() const {
    return !raw() || json_object_get_type(raw()) == json_type_null;
  }
  bool is(json_type type) const {
    return raw() && json_object_get_type(raw()) == type;
  }
  bool has(const std::string &key) const {
    json_object *item = nullptr;
    return is(json_type_object) &&
           json_object_object_get_ex(raw(), key.c_str(), &item);
  }
  Json get(const std::string &key) const {
    json_object *item = nullptr;
    if (is(json_type_object))
      json_object_object_get_ex(raw(), key.c_str(), &item);
    return Json(item, true);
  }
  Json at(size_t index) const {
    return Json(is(json_type_array) ? json_object_array_get_idx(raw(), index)
                                    : nullptr,
                true);
  }
  void set(const std::string &key, const Json &item) {
    json_object_object_add(raw(), key.c_str(),
                           item.raw() ? json_object_get(item.raw()) : nullptr);
  }
  void push(const Json &item) {
    json_object_array_add(raw(),
                          item.raw() ? json_object_get(item.raw()) : nullptr);
  }
  void erase(const std::string &key) {
    json_object_object_del(raw(), key.c_str());
  }
  std::string str(const std::string &fallback = "") const {
    return is(json_type_string) ? json_object_get_string(raw()) : fallback;
  }
  int number(int fallback = 0) const {
    return is(json_type_int) || is(json_type_double)
               ? json_object_get_int(raw())
               : fallback;
  }
  double real(double fallback = 0) const {
    return is(json_type_int) || is(json_type_double)
               ? json_object_get_double(raw())
               : fallback;
  }
  bool boolean(bool fallback = false) const {
    return is(json_type_boolean) ? json_object_get_boolean(raw()) : fallback;
  }
  size_t size() const {
    return is(json_type_array) ? json_object_array_length(raw()) : 0;
  }
  std::vector<Json> items() const {
    std::vector<Json> result;
    for (size_t i = 0; i < size(); ++i)
      result.push_back(at(i));
    return result;
  }
  std::string dump() const {
    return raw() ? json_object_to_json_string_ext(raw(), JSON_C_TO_STRING_PLAIN)
                 : "null";
  }
  Json clone() const { return parse(dump()); }
  bool operator==(const Json &other) const {
    return json_object_equal(raw(), other.raw());
  }
};
