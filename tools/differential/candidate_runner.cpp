#include "candidate_adapter.hpp"
#include "candidate_canonical_trace.hpp"

#include <cstddef>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <new>
#include <span>
#include <string_view>
#include <system_error>
#include <variant>
#include <vector>

namespace {

constexpr int kSuccess = 0;
constexpr int kMalformedTransport = 10;
constexpr int kSerializerFailure = 20;
constexpr int kQualificationInternalFailure = 30;
constexpr int kIoRuntimeFailure = 40;

void diagnostic(std::string_view message) {
  std::cerr << message << '\n';
}

[[nodiscard]]
bool path_exists(
    const std::filesystem::path& path,
    bool& exists) {
  std::error_code error;
  exists = std::filesystem::exists(path, error);
  return !error;
}

[[nodiscard]]
bool read_binary_file(
    const std::filesystem::path& path,
    std::vector<std::byte>& output) {
  std::ifstream stream{
      path,
      std::ios::binary};

  if (!stream.is_open()) {
    return false;
  }

  const std::vector<char> characters{
      std::istreambuf_iterator<char>{stream},
      std::istreambuf_iterator<char>{}};

  if (stream.bad()) {
    return false;
  }

  output.clear();
  output.reserve(characters.size());

  for (const char character : characters) {
    output.push_back(
        static_cast<std::byte>(
            static_cast<unsigned char>(
                character)));
  }

  return true;
}

[[nodiscard]]
bool write_binary_file_atomically(
    const std::filesystem::path& output_path,
    const std::vector<std::byte>& data) {
  bool output_exists = false;

  if (!path_exists(
          output_path,
          output_exists) ||
      output_exists) {
    return false;
  }

  std::filesystem::path temporary_path =
      output_path;
  temporary_path += ".tmp";

  bool temporary_exists = false;

  if (!path_exists(
          temporary_path,
          temporary_exists) ||
      temporary_exists) {
    return false;
  }

  if (data.size() >
      static_cast<std::size_t>(
          std::numeric_limits<
              std::streamsize>::max())) {
    return false;
  }

  {
    std::ofstream stream{
        temporary_path,
        std::ios::binary |
            std::ios::trunc};

    if (!stream.is_open()) {
      return false;
    }

    if (!data.empty()) {
      stream.write(
          reinterpret_cast<const char*>(
              data.data()),
          static_cast<std::streamsize>(
              data.size()));
    }

    stream.close();

    if (!stream) {
      std::error_code cleanup_error;
      std::filesystem::remove(
          temporary_path,
          cleanup_error);
      return false;
    }
  }

  std::error_code rename_error;
  std::filesystem::rename(
      temporary_path,
      output_path,
      rename_error);

  if (rename_error) {
    std::error_code cleanup_error;
    std::filesystem::remove(
        temporary_path,
        cleanup_error);
    return false;
  }

  return true;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 3) {
    diagnostic(
        "candidate runner requires "
        "<input-file> <trace-file>");
    return kIoRuntimeFailure;
  }

  try {
    const std::filesystem::path input_path{
        argv[1]};
    const std::filesystem::path trace_path{
        argv[2]};

    std::vector<std::byte> input_bytes;

    if (!read_binary_file(
            input_path,
            input_bytes)) {
      diagnostic(
          "candidate runner input read failed");
      return kIoRuntimeFailure;
    }

    const auto parsed =
        lob::qualification::parse_lobq1(
            std::span<const std::byte>{
                input_bytes.data(),
                input_bytes.size()});

    if (std::holds_alternative<
            lob::qualification::ParseFailure>(
            parsed)) {
      diagnostic(
          "candidate runner malformed "
          "qualification transport");
      return kMalformedTransport;
    }

    const auto run =
        lob::qualification::execute_candidate(
            std::get<
                lob::qualification::ParsedStream>(
                parsed));

    const auto canonical =
        lob::qualification::
            serialize_candidate_canonical_trace(
                run);

    if (std::holds_alternative<
            lob::qualification::
                CandidateCanonicalFailure>(
            canonical)) {
      diagnostic(
          "candidate runner canonical "
          "serialization failed");
      return kSerializerFailure;
    }

    const auto& trace =
        std::get<std::vector<std::byte>>(
            canonical);

    if (!write_binary_file_atomically(
            trace_path,
            trace)) {
      diagnostic(
          "candidate runner trace write failed");
      return kIoRuntimeFailure;
    }

    return kSuccess;
  } catch (const std::bad_alloc&) {
    diagnostic(
        "candidate runner resource failure");
    return kIoRuntimeFailure;
  } catch (const std::exception& error) {
    diagnostic(
        "candidate runner internal failure");
    diagnostic(error.what());
    return kQualificationInternalFailure;
  } catch (...) {
    diagnostic(
        "candidate runner unknown "
        "internal failure");
    return kQualificationInternalFailure;
  }
}
