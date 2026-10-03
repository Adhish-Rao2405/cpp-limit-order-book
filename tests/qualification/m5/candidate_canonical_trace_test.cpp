#include "candidate_canonical_trace.hpp"

#include <gtest/gtest.h>

#include <bit>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <optional>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <variant>
#include <vector>

namespace lob::qualification {
namespace {

[[nodiscard]]
Price price(Price::rep ticks) {
  return *Price::from_ticks(ticks);
}

[[nodiscard]]
Quantity quantity(Quantity::rep units) {
  return *Quantity::from_units(units);
}

[[nodiscard]]
SequenceNumber sequence(SequenceNumber::rep value) {
  return *SequenceNumber::from_value(value);
}

[[nodiscard]]
std::optional<SequenceNumber> available(
    SequenceNumber::rep value) {
  return sequence(value);
}

[[nodiscard]]
Trade trade(
    OrderId::rep maker,
    OrderId::rep taker,
    Price::rep price_ticks,
    Quantity::rep quantity_units) {
  return Trade{
      OrderId{maker},
      OrderId{taker},
      price(price_ticks),
      quantity(quantity_units)};
}

[[nodiscard]]
RestingOrderView resting(
    OrderId::rep order_id,
    Side side,
    Price::rep price_ticks,
    Quantity::rep remaining,
    SequenceNumber::rep sequence_value) {
  return RestingOrderView{
      OrderId{order_id},
      side,
      price(price_ticks),
      quantity(remaining),
      sequence(sequence_value)};
}

[[nodiscard]]
EngineSnapshot snapshot(
    std::vector<RestingOrderView> bids = {},
    std::vector<RestingOrderView> asks = {},
    std::optional<SequenceNumber> next_sequence = available(1)) {
  return EngineSnapshot{
      std::move(bids),
      std::move(asks),
      next_sequence};
}

[[nodiscard]]
CandidateObservation accepted(
    std::vector<Trade> trades = {},
    EngineSnapshot state = snapshot()) {
  return CandidateObservation{
      CandidateCommandResult{
          true,
          std::nullopt},
      std::move(trades),
      std::move(state)};
}

[[nodiscard]]
CandidateObservation rejected(
    DomainError error,
    EngineSnapshot state = snapshot()) {
  return CandidateObservation{
      CandidateCommandResult{
          false,
          error},
      {},
      std::move(state)};
}

[[nodiscard]]
CandidateRun make_run(
    std::initializer_list<CandidateEntry> entries) {
  return CandidateRun{
      std::vector<CandidateEntry>{entries}};
}

[[nodiscard]]
std::string byte_text(
    const std::vector<std::byte>& bytes) {
  std::string result;
  result.reserve(bytes.size());

  for (const auto value : bytes) {
    result.push_back(
        static_cast<char>(
            std::to_integer<unsigned char>(value)));
  }

  return result;
}

void expect_bytes(
    const CandidateRun& run,
    std::string_view expected) {
  const auto result =
      serialize_candidate_canonical_trace(run);

  ASSERT_TRUE(
      std::holds_alternative<
          std::vector<std::byte>>(result));

  EXPECT_EQ(
      byte_text(
          std::get<std::vector<std::byte>>(
              result)),
      expected);
}

void expect_failure(
    const CandidateRun& run,
    CandidateCanonicalError error,
    std::size_t command_index) {
  const auto result =
      serialize_candidate_canonical_trace(run);

  ASSERT_TRUE(
      std::holds_alternative<
          CandidateCanonicalFailure>(result));

  EXPECT_EQ(
      std::get<CandidateCanonicalFailure>(
          result),
      (CandidateCanonicalFailure{
          error,
          command_index}));
}

/*
 * Qualification-only invariant fabrication.
 *
 * Production constructors deliberately prevent these states. M5C must
 * nevertheless prove that the serializer itself fails closed if a typed
 * observation carrying an invalid underlying representation reaches this
 * boundary. std::bit_cast is used only in the qualification test binary and
 * does not mutate or bypass production behavior.
 */
template <typename Type, typename Representation>
[[nodiscard]]
Type fabricate_invalid_representation(
    Representation representation) {
  static_assert(std::is_trivially_copyable_v<Type>);
  static_assert(
      std::is_trivially_copyable_v<Representation>);
  static_assert(sizeof(Type) == sizeof(Representation));

  return std::bit_cast<Type>(representation);
}

TEST(
    CandidateCanonicalTraceKnownAnswerTest,
    HeaderOnlyTraceIsExact) {
  expect_bytes(
      CandidateRun{},
      "{\"record_type\":\"trace_header\","
      "\"schema\":\"lob.canonical_trace\","
      "\"version\":\"1\"}\n");
}

TEST(
    CandidateCanonicalTraceKnownAnswerTest,
    AcceptedCommandWithZeroTradesIsExact) {
  const auto run =
      make_run({
          CandidateEntry{
              RawCommand{
                  RawNew{
                      7,
                      0,
                      100,
                      5}},
              accepted()}
      });

  expect_bytes(
      run,
      "{\"record_type\":\"trace_header\","
      "\"schema\":\"lob.canonical_trace\","
      "\"version\":\"1\"}\n"
      "{\"record_type\":\"command\","
      "\"command_index\":\"0\","
      "\"command\":{"
      "\"kind\":\"new\","
      "\"order_id\":\"7\","
      "\"side_code\":\"0\","
      "\"price_ticks\":\"100\","
      "\"quantity_units\":\"5\"},"
      "\"command_result\":{"
      "\"accepted\":true,"
      "\"error\":null},"
      "\"trades\":[],"
      "\"bids\":[],"
      "\"asks\":[],"
      "\"next_sequence\":{"
      "\"state\":\"available\","
      "\"value\":\"1\"}}\n");
}

TEST(
    CandidateCanonicalTraceKnownAnswerTest,
    OneTradeIsExact) {
  const auto run =
      make_run({
          CandidateEntry{
              RawCommand{
                  RawNew{
                      20,
                      0,
                      101,
                      1}},
              accepted(
                  {
                      trade(
                          10,
                          20,
                          101,
                          1)
                  },
                  snapshot(
                      {},
                      {},
                      available(3)))}
      });

  expect_bytes(
      run,
      "{\"record_type\":\"trace_header\","
      "\"schema\":\"lob.canonical_trace\","
      "\"version\":\"1\"}\n"
      "{\"record_type\":\"command\","
      "\"command_index\":\"0\","
      "\"command\":{"
      "\"kind\":\"new\","
      "\"order_id\":\"20\","
      "\"side_code\":\"0\","
      "\"price_ticks\":\"101\","
      "\"quantity_units\":\"1\"},"
      "\"command_result\":{"
      "\"accepted\":true,"
      "\"error\":null},"
      "\"trades\":[{"
      "\"maker_order_id\":\"10\","
      "\"taker_order_id\":\"20\","
      "\"price_ticks\":\"101\","
      "\"quantity_units\":\"1\"}],"
      "\"bids\":[],"
      "\"asks\":[],"
      "\"next_sequence\":{"
      "\"state\":\"available\","
      "\"value\":\"3\"}}\n");
}

TEST(
    CandidateCanonicalTraceKnownAnswerTest,
    MultipleTradesPreserveProducerOrderExactly) {
  const auto run =
      make_run({
          CandidateEntry{
              RawCommand{
                  RawNew{
                      30,
                      0,
                      102,
                      2}},
              accepted(
                  {
                      trade(
                          11,
                          30,
                          100,
                          1),
                      trade(
                          12,
                          30,
                          101,
                          1)
                  },
                  snapshot(
                      {},
                      {},
                      available(4)))}
      });

  expect_bytes(
      run,
      "{\"record_type\":\"trace_header\","
      "\"schema\":\"lob.canonical_trace\","
      "\"version\":\"1\"}\n"
      "{\"record_type\":\"command\","
      "\"command_index\":\"0\","
      "\"command\":{"
      "\"kind\":\"new\","
      "\"order_id\":\"30\","
      "\"side_code\":\"0\","
      "\"price_ticks\":\"102\","
      "\"quantity_units\":\"2\"},"
      "\"command_result\":{"
      "\"accepted\":true,"
      "\"error\":null},"
      "\"trades\":[{"
      "\"maker_order_id\":\"11\","
      "\"taker_order_id\":\"30\","
      "\"price_ticks\":\"100\","
      "\"quantity_units\":\"1\"},{"
      "\"maker_order_id\":\"12\","
      "\"taker_order_id\":\"30\","
      "\"price_ticks\":\"101\","
      "\"quantity_units\":\"1\"}],"
      "\"bids\":[],"
      "\"asks\":[],"
      "\"next_sequence\":{"
      "\"state\":\"available\","
      "\"value\":\"4\"}}\n");
}

TEST(
    CandidateCanonicalTraceKnownAnswerTest,
    RejectedCommandIsExact) {
  const auto run =
      make_run({
          CandidateEntry{
              RawCommand{
                  RawNew{
                      99,
                      2,
                      100,
                      1}},
              rejected(
                  DomainError::InvalidSide)}
      });

  expect_bytes(
      run,
      "{\"record_type\":\"trace_header\","
      "\"schema\":\"lob.canonical_trace\","
      "\"version\":\"1\"}\n"
      "{\"record_type\":\"command\","
      "\"command_index\":\"0\","
      "\"command\":{"
      "\"kind\":\"new\","
      "\"order_id\":\"99\","
      "\"side_code\":\"2\","
      "\"price_ticks\":\"100\","
      "\"quantity_units\":\"1\"},"
      "\"command_result\":{"
      "\"accepted\":false,"
      "\"error\":\"InvalidSide\"},"
      "\"trades\":[],"
      "\"bids\":[],"
      "\"asks\":[],"
      "\"next_sequence\":{"
      "\"state\":\"available\","
      "\"value\":\"1\"}}\n");
}

TEST(
    CandidateCanonicalTraceKnownAnswerTest,
    OrderedBidAndAskBooksAreExact) {
  const auto run =
      make_run({
          CandidateEntry{
              RawCommand{
                  RawCancel{42}},
              accepted(
                  {},
                  snapshot(
                      {
                          resting(
                              2,
                              Side::Buy,
                              101,
                              2,
                              2),
                          resting(
                              1,
                              Side::Buy,
                              99,
                              1,
                              1)
                      },
                      {
                          resting(
                              4,
                              Side::Sell,
                              103,
                              4,
                              4),
                          resting(
                              3,
                              Side::Sell,
                              105,
                              3,
                              3)
                      },
                      available(5)))}
      });

  expect_bytes(
      run,
      "{\"record_type\":\"trace_header\","
      "\"schema\":\"lob.canonical_trace\","
      "\"version\":\"1\"}\n"
      "{\"record_type\":\"command\","
      "\"command_index\":\"0\","
      "\"command\":{"
      "\"kind\":\"cancel\","
      "\"order_id\":\"42\"},"
      "\"command_result\":{"
      "\"accepted\":true,"
      "\"error\":null},"
      "\"trades\":[],"
      "\"bids\":[{"
      "\"order_id\":\"2\","
      "\"side\":\"Buy\","
      "\"price_ticks\":\"101\","
      "\"remaining_quantity_units\":\"2\","
      "\"sequence\":\"2\"},{"
      "\"order_id\":\"1\","
      "\"side\":\"Buy\","
      "\"price_ticks\":\"99\","
      "\"remaining_quantity_units\":\"1\","
      "\"sequence\":\"1\"}],"
      "\"asks\":[{"
      "\"order_id\":\"4\","
      "\"side\":\"Sell\","
      "\"price_ticks\":\"103\","
      "\"remaining_quantity_units\":\"4\","
      "\"sequence\":\"4\"},{"
      "\"order_id\":\"3\","
      "\"side\":\"Sell\","
      "\"price_ticks\":\"105\","
      "\"remaining_quantity_units\":\"3\","
      "\"sequence\":\"3\"}],"
      "\"next_sequence\":{"
      "\"state\":\"available\","
      "\"value\":\"5\"}}\n");
}

TEST(
    CandidateCanonicalTraceKnownAnswerTest,
    Uint64MaxInt64MinAndAvailableAllocatorMaxAreExact) {
  constexpr auto maximum =
      std::numeric_limits<std::uint64_t>::max();
  constexpr auto minimum_price =
      std::numeric_limits<std::int64_t>::min();

  const auto run =
      make_run({
          CandidateEntry{
              RawCommand{
                  RawNew{
                      maximum,
                      255,
                      minimum_price,
                      maximum}},
              rejected(
                  DomainError::InvalidPrice,
                  snapshot(
                      {},
                      {},
                      available(maximum)))}
      });

  expect_bytes(
      run,
      "{\"record_type\":\"trace_header\","
      "\"schema\":\"lob.canonical_trace\","
      "\"version\":\"1\"}\n"
      "{\"record_type\":\"command\","
      "\"command_index\":\"0\","
      "\"command\":{"
      "\"kind\":\"new\","
      "\"order_id\":\"18446744073709551615\","
      "\"side_code\":\"255\","
      "\"price_ticks\":\"-9223372036854775808\","
      "\"quantity_units\":\"18446744073709551615\"},"
      "\"command_result\":{"
      "\"accepted\":false,"
      "\"error\":\"InvalidPrice\"},"
      "\"trades\":[],"
      "\"bids\":[],"
      "\"asks\":[],"
      "\"next_sequence\":{"
      "\"state\":\"available\","
      "\"value\":\"18446744073709551615\"}}\n");
}

TEST(
    CandidateCanonicalTraceKnownAnswerTest,
    Int64MaxAndExhaustedAllocatorAreExact) {
  constexpr auto maximum_price =
      std::numeric_limits<std::int64_t>::max();

  const auto run =
      make_run({
          CandidateEntry{
              RawCommand{
                  RawModify{
                      0,
                      maximum_price,
                      0}},
              rejected(
                  DomainError::InvalidQuantity,
                  snapshot(
                      {},
                      {},
                      std::nullopt))}
      });

  expect_bytes(
      run,
      "{\"record_type\":\"trace_header\","
      "\"schema\":\"lob.canonical_trace\","
      "\"version\":\"1\"}\n"
      "{\"record_type\":\"command\","
      "\"command_index\":\"0\","
      "\"command\":{"
      "\"kind\":\"modify\","
      "\"order_id\":\"0\","
      "\"price_ticks\":\"9223372036854775807\","
      "\"quantity_units\":\"0\"},"
      "\"command_result\":{"
      "\"accepted\":false,"
      "\"error\":\"InvalidQuantity\"},"
      "\"trades\":[],"
      "\"bids\":[],"
      "\"asks\":[],"
      "\"next_sequence\":{"
      "\"state\":\"exhausted\","
      "\"value\":null}}\n");
}

TEST(
    CandidateCanonicalTraceKnownAnswerTest,
    CommandIndexesAdvanceInProcessingOrder) {
  const auto run =
      make_run({
          CandidateEntry{
              RawCommand{
                  RawCancel{7}},
              accepted()},
          CandidateEntry{
              RawCommand{
                  RawCancel{8}},
              accepted()}
      });

  expect_bytes(
      run,
      "{\"record_type\":\"trace_header\","
      "\"schema\":\"lob.canonical_trace\","
      "\"version\":\"1\"}\n"
      "{\"record_type\":\"command\","
      "\"command_index\":\"0\","
      "\"command\":{"
      "\"kind\":\"cancel\","
      "\"order_id\":\"7\"},"
      "\"command_result\":{"
      "\"accepted\":true,"
      "\"error\":null},"
      "\"trades\":[],"
      "\"bids\":[],"
      "\"asks\":[],"
      "\"next_sequence\":{"
      "\"state\":\"available\","
      "\"value\":\"1\"}}\n"
      "{\"record_type\":\"command\","
      "\"command_index\":\"1\","
      "\"command\":{"
      "\"kind\":\"cancel\","
      "\"order_id\":\"8\"},"
      "\"command_result\":{"
      "\"accepted\":true,"
      "\"error\":null},"
      "\"trades\":[],"
      "\"bids\":[],"
      "\"asks\":[],"
      "\"next_sequence\":{"
      "\"state\":\"available\","
      "\"value\":\"1\"}}\n");
}

TEST(
    CandidateCanonicalTraceContractTest,
    OutputUsesCompactAsciiAndLfOnly) {
  const auto result =
      serialize_candidate_canonical_trace(
          make_run({
              CandidateEntry{
                  RawCommand{
                      RawCancel{1}},
                  accepted()}
          }));

  ASSERT_TRUE(
      std::holds_alternative<
          std::vector<std::byte>>(result));

  const auto text =
      byte_text(
          std::get<std::vector<std::byte>>(
              result));

  ASSERT_FALSE(text.empty());
  EXPECT_EQ(text.back(), '\n');

  for (const char character : text) {
    const auto value =
        static_cast<unsigned char>(
            character);

    EXPECT_LE(value, 0x7FU);
    EXPECT_NE(character, '\r');
    EXPECT_NE(character, ' ');
    EXPECT_NE(character, '\t');
  }
}

TEST(
    CandidateCanonicalTraceContractTest,
    EmitsEveryFrozenDomainErrorName) {
  const std::vector<
      std::pair<DomainError, std::string_view>>
      cases{
          {
              DomainError::InvalidPrice,
              "InvalidPrice"},
          {
              DomainError::InvalidQuantity,
              "InvalidQuantity"},
          {
              DomainError::InvalidSide,
              "InvalidSide"},
          {
              DomainError::DuplicateOrderId,
              "DuplicateOrderId"},
          {
              DomainError::UnknownOrderId,
              "UnknownOrderId"},
          {
              DomainError::SequenceExhausted,
              "SequenceExhausted"},
          {
              DomainError::InvalidModification,
              "InvalidModification"}
      };

  for (const auto& [error, expected] : cases) {
    const auto result =
        serialize_candidate_canonical_trace(
            make_run({
                CandidateEntry{
                    RawCommand{
                        RawCancel{1}},
                    rejected(error)}
            }));

    ASSERT_TRUE(
        std::holds_alternative<
            std::vector<std::byte>>(result));

    const auto text =
        byte_text(
            std::get<std::vector<std::byte>>(
                result));

    EXPECT_NE(
        text.find(
            std::string{
                "\"error\":\""} +
            std::string{expected} +
            "\""),
        std::string::npos);
  }
}

TEST(
    CandidateCanonicalTraceFailureTest,
    RejectsInvalidAcceptedErrorCombinations) {
  expect_failure(
      make_run({
          CandidateEntry{
              RawCommand{
                  RawCancel{1}},
              CandidateObservation{
                  CandidateCommandResult{
                      true,
                      DomainError::UnknownOrderId},
                  {},
                  snapshot()}}
      }),
      CandidateCanonicalError::
          InvalidCommandResult,
      0);

  expect_failure(
      make_run({
          CandidateEntry{
              RawCommand{
                  RawCancel{1}},
              CandidateObservation{
                  CandidateCommandResult{
                      false,
                      std::nullopt},
                  {},
                  snapshot()}}
      }),
      CandidateCanonicalError::
          InvalidCommandResult,
      0);
}

TEST(
    CandidateCanonicalTraceFailureTest,
    RejectsDomainErrorOutsideFrozenVocabulary) {
  const auto invalid_error =
      static_cast<DomainError>(255);

  expect_failure(
      make_run({
          CandidateEntry{
              RawCommand{
                  RawCancel{1}},
              CandidateObservation{
                  CandidateCommandResult{
                      false,
                      invalid_error},
                  {},
                  snapshot()}}
      }),
      CandidateCanonicalError::
          InvalidDomainError,
      0);
}

TEST(
    CandidateCanonicalTraceFailureTest,
    RejectsRejectedCommandWithTrades) {
  expect_failure(
      make_run({
          CandidateEntry{
              RawCommand{
                  RawNew{
                      2,
                      0,
                      100,
                      1}},
              CandidateObservation{
                  CandidateCommandResult{
                      false,
                      DomainError::DuplicateOrderId},
                  {
                      trade(
                          1,
                          2,
                          100,
                          1)
                  },
                  snapshot()}}
      }),
      CandidateCanonicalError::
          RejectedCommandHasTrades,
      0);
}

TEST(
    CandidateCanonicalTraceFailureTest,
    RejectsInvalidTrade) {
  const auto invalid_price =
      fabricate_invalid_representation<Price>(
          Price::rep{0});

  const Trade invalid_trade{
      OrderId{1},
      OrderId{2},
      invalid_price,
      quantity(1)};

  expect_failure(
      make_run({
          CandidateEntry{
              RawCommand{
                  RawCancel{1}},
              accepted(
                  {invalid_trade})}
      }),
      CandidateCanonicalError::
          InvalidTrade,
      0);
}

TEST(
    CandidateCanonicalTraceFailureTest,
    RejectsInvalidRestingOrder) {
  const auto invalid_quantity =
      fabricate_invalid_representation<Quantity>(
          Quantity::rep{0});

  const RestingOrderView invalid_order{
      OrderId{1},
      Side::Buy,
      price(100),
      invalid_quantity,
      sequence(1)};

  expect_failure(
      make_run({
          CandidateEntry{
              RawCommand{
                  RawCancel{1}},
              accepted(
                  {},
                  snapshot(
                      {invalid_order},
                      {},
                      available(2)))}
      }),
      CandidateCanonicalError::
          InvalidRestingOrder,
      0);
}

TEST(
    CandidateCanonicalTraceFailureTest,
    RejectsInvalidOrWrongRestingSide) {
  expect_failure(
      make_run({
          CandidateEntry{
              RawCommand{
                  RawCancel{1}},
              accepted(
                  {},
                  snapshot(
                      {
                          resting(
                              1,
                              static_cast<Side>(2),
                              100,
                              1,
                              1)
                      },
                      {},
                      available(2)))}
      }),
      CandidateCanonicalError::
          InvalidRestingSide,
      0);

  expect_failure(
      make_run({
          CandidateEntry{
              RawCommand{
                  RawCancel{1}},
              accepted(
                  {},
                  snapshot(
                      {
                          resting(
                              1,
                              Side::Sell,
                              100,
                              1,
                              1)
                      },
                      {},
                      available(2)))}
      }),
      CandidateCanonicalError::
          InvalidRestingSide,
      0);
}

TEST(
    CandidateCanonicalTraceFailureTest,
    RejectsNonCanonicalBidOrderWithoutSorting) {
  expect_failure(
      make_run({
          CandidateEntry{
              RawCommand{
                  RawCancel{1}},
              accepted(
                  {},
                  snapshot(
                      {
                          resting(
                              1,
                              Side::Buy,
                              100,
                              1,
                              1),
                          resting(
                              2,
                              Side::Buy,
                              101,
                              1,
                              2)
                      },
                      {},
                      available(3)))}
      }),
      CandidateCanonicalError::
          NonCanonicalBidOrder,
      0);
}

TEST(
    CandidateCanonicalTraceFailureTest,
    RejectsNonCanonicalAskOrderWithoutSorting) {
  expect_failure(
      make_run({
          CandidateEntry{
              RawCommand{
                  RawCancel{1}},
              accepted(
                  {},
                  snapshot(
                      {},
                      {
                          resting(
                              1,
                              Side::Sell,
                              105,
                              1,
                              1),
                          resting(
                              2,
                              Side::Sell,
                              103,
                              1,
                              2)
                      },
                      available(3)))}
      }),
      CandidateCanonicalError::
          NonCanonicalAskOrder,
      0);
}

TEST(
    CandidateCanonicalTraceFailureTest,
    RejectsInvalidAllocator) {
  const auto invalid_sequence =
      fabricate_invalid_representation<
          SequenceNumber>(
          SequenceNumber::rep{0});

  expect_failure(
      make_run({
          CandidateEntry{
              RawCommand{
                  RawCancel{1}},
              accepted(
                  {},
                  snapshot(
                      {},
                      {},
                      std::optional<SequenceNumber>{
                          invalid_sequence}))}
      }),
      CandidateCanonicalError::
          InvalidAllocator,
      0);
}

TEST(
    CandidateCanonicalTraceFailureTest,
    ReportsExactFailingCommandIndex) {
  const auto invalid =
      CandidateObservation{
          CandidateCommandResult{
              true,
              DomainError::UnknownOrderId},
          {},
          snapshot()};

  expect_failure(
      make_run({
          CandidateEntry{
              RawCommand{
                  RawCancel{1}},
              accepted()},
          CandidateEntry{
              RawCommand{
                  RawCancel{2}},
              invalid}
      }),
      CandidateCanonicalError::
          InvalidCommandResult,
      1);
}

}  // namespace
}  // namespace lob::qualification
