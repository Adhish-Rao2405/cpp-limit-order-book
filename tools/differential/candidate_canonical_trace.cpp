#include "candidate_canonical_trace.hpp"

#include <array>
#include <charconv>
#include <cstddef>
#include <optional>
#include <string>
#include <string_view>
#include <type_traits>
#include <variant>
#include <vector>

namespace lob::qualification {
namespace {

constexpr std::string_view kHeader =
    "{\"record_type\":\"trace_header\","
    "\"schema\":\"lob.canonical_trace\","
    "\"version\":\"1\"}\n";

[[nodiscard]]
std::optional<std::string_view> domain_error_text(DomainError error) {
  switch (error) {
    case DomainError::InvalidPrice:
      return "InvalidPrice";
    case DomainError::InvalidQuantity:
      return "InvalidQuantity";
    case DomainError::InvalidSide:
      return "InvalidSide";
    case DomainError::DuplicateOrderId:
      return "DuplicateOrderId";
    case DomainError::UnknownOrderId:
      return "UnknownOrderId";
    case DomainError::SequenceExhausted:
      return "SequenceExhausted";
    case DomainError::InvalidModification:
      return "InvalidModification";
  }

  return std::nullopt;
}

template <typename Integer>
void append_decimal(std::string& output, Integer value) {
  static_assert(std::is_integral_v<Integer>);
  static_assert(!std::is_same_v<Integer, bool>);

  std::array<char, 32> buffer{};
  const auto result =
      std::to_chars(buffer.data(), buffer.data() + buffer.size(), value);

  output.append(buffer.data(), result.ptr);
}

template <typename Integer>
void append_quoted_decimal(std::string& output, Integer value) {
  output.push_back('"');
  append_decimal(output, value);
  output.push_back('"');
}

[[nodiscard]]
std::optional<CandidateCanonicalError> validate_command_result(
    const CandidateCommandResult& result) {
  if (result.accepted) {
    if (result.error.has_value()) {
      return CandidateCanonicalError::InvalidCommandResult;
    }

    return std::nullopt;
  }

  if (!result.error.has_value()) {
    return CandidateCanonicalError::InvalidCommandResult;
  }

  if (!domain_error_text(*result.error).has_value()) {
    return CandidateCanonicalError::InvalidDomainError;
  }

  return std::nullopt;
}

[[nodiscard]]
bool valid_trade(const Trade& trade) {
  return trade.price.ticks() > 0 && trade.quantity.units() > 0;
}

[[nodiscard]]
std::optional<CandidateCanonicalError> validate_book(
    const std::vector<RestingOrderView>& orders,
    Side expected_side,
    CandidateCanonicalError ordering_error) {
  for (std::size_t index = 0; index < orders.size(); ++index) {
    const auto& order = orders[index];

    if (!is_valid(order.side) || order.side != expected_side) {
      return CandidateCanonicalError::InvalidRestingSide;
    }

    if (order.price.ticks() <= 0 ||
        order.remaining.units() == 0 ||
        order.sequence.value() == 0) {
      return CandidateCanonicalError::InvalidRestingOrder;
    }

    if (index == 0) {
      continue;
    }

    const auto& previous = orders[index - 1];

    const auto previous_price = previous.price.ticks();
    const auto current_price = order.price.ticks();
    const auto previous_sequence = previous.sequence.value();
    const auto current_sequence = order.sequence.value();

    if (expected_side == Side::Buy) {
      if (current_price > previous_price ||
          (current_price == previous_price &&
           current_sequence < previous_sequence)) {
        return ordering_error;
      }
    } else {
      if (current_price < previous_price ||
          (current_price == previous_price &&
           current_sequence < previous_sequence)) {
        return ordering_error;
      }
    }
  }

  return std::nullopt;
}

[[nodiscard]]
std::optional<CandidateCanonicalError> validate_observation(
    const CandidateObservation& observation) {
  if (const auto result_error =
          validate_command_result(observation.command_result);
      result_error.has_value()) {
    return result_error;
  }

  if (!observation.command_result.accepted &&
      !observation.trades.empty()) {
    return CandidateCanonicalError::RejectedCommandHasTrades;
  }

  for (const auto& trade : observation.trades) {
    if (!valid_trade(trade)) {
      return CandidateCanonicalError::InvalidTrade;
    }
  }

  if (const auto bid_error =
          validate_book(
              observation.snapshot.bids,
              Side::Buy,
              CandidateCanonicalError::NonCanonicalBidOrder);
      bid_error.has_value()) {
    return bid_error;
  }

  if (const auto ask_error =
          validate_book(
              observation.snapshot.asks,
              Side::Sell,
              CandidateCanonicalError::NonCanonicalAskOrder);
      ask_error.has_value()) {
    return ask_error;
  }

  if (observation.snapshot.next_sequence.has_value() &&
      observation.snapshot.next_sequence->value() == 0) {
    return CandidateCanonicalError::InvalidAllocator;
  }

  return std::nullopt;
}

void append_command(std::string& output, const RawCommand& raw_command) {
  std::visit(
      [&output](const auto& command) {
        using Command = std::decay_t<decltype(command)>;

        if constexpr (std::is_same_v<Command, RawNew>) {
          output += "{\"kind\":\"new\",\"order_id\":";
          append_quoted_decimal(output, command.order_id);
          output += ",\"side_code\":";
          append_quoted_decimal(
              output,
              static_cast<unsigned int>(command.side_code));
          output += ",\"price_ticks\":";
          append_quoted_decimal(output, command.price_ticks);
          output += ",\"quantity_units\":";
          append_quoted_decimal(output, command.quantity_units);
          output.push_back('}');
        } else if constexpr (std::is_same_v<Command, RawCancel>) {
          output += "{\"kind\":\"cancel\",\"order_id\":";
          append_quoted_decimal(output, command.order_id);
          output.push_back('}');
        } else if constexpr (std::is_same_v<Command, RawModify>) {
          output += "{\"kind\":\"modify\",\"order_id\":";
          append_quoted_decimal(output, command.order_id);
          output += ",\"price_ticks\":";
          append_quoted_decimal(output, command.price_ticks);
          output += ",\"quantity_units\":";
          append_quoted_decimal(output, command.quantity_units);
          output.push_back('}');
        }
      },
      raw_command);
}

void append_command_result(
    std::string& output,
    const CandidateCommandResult& result) {
  output += "{\"accepted\":";

  if (result.accepted) {
    output += "true,\"error\":null}";
    return;
  }

  output += "false,\"error\":\"";
  output += *domain_error_text(*result.error);
  output += "\"}";
}

void append_trade(std::string& output, const Trade& trade) {
  output += "{\"maker_order_id\":";
  append_quoted_decimal(output, trade.maker.value());
  output += ",\"taker_order_id\":";
  append_quoted_decimal(output, trade.taker.value());
  output += ",\"price_ticks\":";
  append_quoted_decimal(output, trade.price.ticks());
  output += ",\"quantity_units\":";
  append_quoted_decimal(output, trade.quantity.units());
  output.push_back('}');
}

void append_resting_order(
    std::string& output,
    const RestingOrderView& order,
    std::string_view side_text) {
  output += "{\"order_id\":";
  append_quoted_decimal(output, order.order_id.value());
  output += ",\"side\":\"";
  output += side_text;
  output += "\",\"price_ticks\":";
  append_quoted_decimal(output, order.price.ticks());
  output += ",\"remaining_quantity_units\":";
  append_quoted_decimal(output, order.remaining.units());
  output += ",\"sequence\":";
  append_quoted_decimal(output, order.sequence.value());
  output.push_back('}');
}

void append_allocator(
    std::string& output,
    const std::optional<SequenceNumber>& next_sequence) {
  if (!next_sequence.has_value()) {
    output += "{\"state\":\"exhausted\",\"value\":null}";
    return;
  }

  output += "{\"state\":\"available\",\"value\":";
  append_quoted_decimal(output, next_sequence->value());
  output.push_back('}');
}

void append_command_record(
    std::string& output,
    std::size_t command_index,
    const CandidateEntry& entry) {
  output += "{\"record_type\":\"command\",\"command_index\":";
  append_quoted_decimal(output, command_index);

  output += ",\"command\":";
  append_command(output, entry.command);

  output += ",\"command_result\":";
  append_command_result(output, entry.observation.command_result);

  output += ",\"trades\":[";
  for (std::size_t index = 0;
       index < entry.observation.trades.size();
       ++index) {
    if (index != 0) {
      output.push_back(',');
    }

    append_trade(output, entry.observation.trades[index]);
  }
  output.push_back(']');

  output += ",\"bids\":[";
  for (std::size_t index = 0;
       index < entry.observation.snapshot.bids.size();
       ++index) {
    if (index != 0) {
      output.push_back(',');
    }

    append_resting_order(
        output,
        entry.observation.snapshot.bids[index],
        "Buy");
  }
  output.push_back(']');

  output += ",\"asks\":[";
  for (std::size_t index = 0;
       index < entry.observation.snapshot.asks.size();
       ++index) {
    if (index != 0) {
      output.push_back(',');
    }

    append_resting_order(
        output,
        entry.observation.snapshot.asks[index],
        "Sell");
  }
  output.push_back(']');

  output += ",\"next_sequence\":";
  append_allocator(output, entry.observation.snapshot.next_sequence);
  output += "}\n";
}

[[nodiscard]]
std::vector<std::byte> to_bytes(const std::string& text) {
  std::vector<std::byte> bytes;
  bytes.reserve(text.size());

  for (const char character : text) {
    bytes.push_back(
        static_cast<std::byte>(
            static_cast<unsigned char>(character)));
  }

  return bytes;
}

}  // namespace

CandidateCanonicalResult serialize_candidate_canonical_trace(
    const CandidateRun& run) {
  std::string output{kHeader};

  for (std::size_t command_index = 0;
       command_index < run.entries.size();
       ++command_index) {
    const auto& entry = run.entries[command_index];

    if (const auto error =
            validate_observation(entry.observation);
        error.has_value()) {
      return CandidateCanonicalFailure{
          *error,
          command_index};
    }

    append_command_record(
        output,
        command_index,
        entry);
  }

  return to_bytes(output);
}

}  // namespace lob::qualification
