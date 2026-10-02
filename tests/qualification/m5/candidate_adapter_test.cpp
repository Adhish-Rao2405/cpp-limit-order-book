#include "candidate_adapter.hpp"

#include <gtest/gtest.h>

#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <variant>
#include <vector>

#if !defined(LOB_ENABLE_MATCHING_ENGINE_QUALIFICATION)
#error "M5 candidate adapter tests require matching-engine qualification access"
#endif

namespace {

using lob::DomainError;
using lob::OrderId;
using lob::Price;
using lob::Quantity;
using lob::SequenceNumber;
using lob::Side;

using lob::qualification::CandidateEntry;
using lob::qualification::CandidateRun;
using lob::qualification::ParseError;
using lob::qualification::ParseFailure;
using lob::qualification::ParseResult;
using lob::qualification::ParsedStream;
using lob::qualification::RawCancel;
using lob::qualification::RawModify;
using lob::qualification::RawNew;
using lob::qualification::execute_candidate;
using lob::qualification::parse_lobq1;

[[nodiscard]]
std::vector<std::byte>
to_bytes(std::string_view text) {
    std::vector<std::byte> result;

    result.reserve(text.size());

    for (const char value : text) {
        result.push_back(
            static_cast<std::byte>(
                static_cast<unsigned char>(
                    value)));
    }

    return result;
}

[[nodiscard]]
ParseResult parse_text(
    std::string_view text) {
    const auto data = to_bytes(text);

    return parse_lobq1(
        std::span<const std::byte>{data});
}

void expect_error(
    std::string_view text,
    ParseError expected) {
    const auto result = parse_text(text);

    ASSERT_TRUE(
        std::holds_alternative<
            ParseFailure>(result));

    EXPECT_EQ(
        std::get<ParseFailure>(
            result).error,
        expected);
}

void expect_error(
    const std::vector<std::byte>& data,
    ParseError expected) {
    const auto result =
        parse_lobq1(
            std::span<
                const std::byte>{data});

    ASSERT_TRUE(
        std::holds_alternative<
            ParseFailure>(result));

    EXPECT_EQ(
        std::get<ParseFailure>(
            result).error,
        expected);
}

[[nodiscard]]
ParsedStream require_stream(
    std::string_view text) {
    auto result = parse_text(text);

    if (!std::holds_alternative<
            ParsedStream>(result)) {
        ADD_FAILURE()
            << "expected transport-valid "
               "LOBQ1 stream";

        return {};
    }

    return std::get<ParsedStream>(
        std::move(result));
}

[[nodiscard]]
const CandidateEntry&
entry(
    const CandidateRun& run,
    std::size_t index) {
    return run.entries.at(index);
}

void expect_accepted(
    const CandidateEntry& value) {
    EXPECT_TRUE(
        value.observation
            .command_result.accepted);

    EXPECT_FALSE(
        value.observation
            .command_result.error
            .has_value());
}

void expect_rejected(
    const CandidateEntry& value,
    DomainError error) {
    EXPECT_FALSE(
        value.observation
            .command_result.accepted);

    ASSERT_TRUE(
        value.observation
            .command_result.error
            .has_value());

    EXPECT_EQ(
        *value.observation
             .command_result.error,
        error);

    EXPECT_TRUE(
        value.observation
            .trades.empty());
}

TEST(
    CandidateAdapterTransportTest,
    ParsesNormalAndExhaustedHeaderOnlyStreams) {
    const auto normal =
        require_stream(
            "LOBQ1|1\n");

    ASSERT_TRUE(
        normal.next_sequence
            .has_value());

    EXPECT_EQ(
        *normal.next_sequence,
        1U);

    EXPECT_TRUE(
        normal.commands.empty());

    const auto exhausted =
        require_stream(
            "LOBQ1|EXHAUSTED\n");

    EXPECT_FALSE(
        exhausted.next_sequence
            .has_value());

    EXPECT_TRUE(
        exhausted.commands.empty());
}

TEST(
    CandidateAdapterTransportTest,
    ParsesAllocatorBoundariesAndRejectsZero) {
    constexpr auto maximum =
        std::numeric_limits<
            SequenceNumber::rep>::max();

    const auto stream =
        require_stream(
            "LOBQ1|18446744073709551615\n");

    ASSERT_TRUE(
        stream.next_sequence
            .has_value());

    EXPECT_EQ(
        *stream.next_sequence,
        maximum);

    expect_error(
        "LOBQ1|0\n",
        ParseError::ScalarOutOfRange);
}

TEST(
    CandidateAdapterTransportTest,
    RejectsInvalidByteFraming) {
    expect_error(
        "",
        ParseError::EmptyInput);

    expect_error(
        "LOBQ1|1",
        ParseError::MissingFinalLf);

    expect_error(
        "LOBQ1|1\r\n",
        ParseError::CarriageReturn);

    auto bom =
        to_bytes("LOBQ1|1\n");

    bom.insert(
        bom.begin(),
        {
            static_cast<std::byte>(
                0xEF),
            static_cast<std::byte>(
                0xBB),
            static_cast<std::byte>(
                0xBF)
        });

    expect_error(
        bom,
        ParseError::Utf8Bom);

    auto nul =
        to_bytes("LOBQ1|1\nC|1");

    nul.push_back(
        static_cast<std::byte>(0));

    nul.push_back(
        static_cast<std::byte>('\n'));

    expect_error(
        nul,
        ParseError::EmbeddedNul);

    auto non_ascii =
        to_bytes("LOBQ1|1\nC|1");

    non_ascii.push_back(
        static_cast<std::byte>(
            0x80));

    non_ascii.push_back(
        static_cast<std::byte>('\n'));

    expect_error(
        non_ascii,
        ParseError::NonAsciiByte);
}

TEST(
    CandidateAdapterTransportTest,
    RejectsRecordAndHeaderShapeDefects) {
    expect_error(
        "LOBQ1|1\n\n",
        ParseError::BlankRecord);

    expect_error(
        "C|1\n",
        ParseError::InvalidHeader);

    expect_error(
        "LOBQ2|1\n",
        ParseError::InvalidHeader);

    expect_error(
        "LOBQ1\n",
        ParseError::InvalidHeader);

    expect_error(
        "LOBQ1|1\nLOBQ1|2\n",
        ParseError::DuplicateHeader);

    expect_error(
        "LOBQ1|1\nX|1\n",
        ParseError::UnknownCommandKind);

    expect_error(
        "LOBQ1|1\nN|1|0|100\n",
        ParseError::WrongFieldCount);

    expect_error(
        "LOBQ1|1\n"
        "N|1|0|100|1|extra\n",
        ParseError::WrongFieldCount);

    expect_error(
        "LOBQ1|1\nC|1|extra\n",
        ParseError::WrongFieldCount);

    expect_error(
        "LOBQ1|1\nM|1|100\n",
        ParseError::WrongFieldCount);

    expect_error(
        "LOBQ1|1\n"
        "M|1|100|1|extra\n",
        ParseError::WrongFieldCount);

    std::string too_long =
        "LOBQ1|1\nC|";

    too_long.append(
        129,
        '1');

    too_long.push_back('\n');

    expect_error(
        too_long,
        ParseError::RecordTooLong);
}

TEST(
    CandidateAdapterTransportTest,
    RejectsLeadingAndTrailingWhitespace) {
    const auto leading =
        parse_text(
            "LOBQ1|1\n"
            " N|1|0|100|1\n");

    EXPECT_TRUE(
        std::holds_alternative<
            ParseFailure>(leading));

    const auto trailing =
        parse_text(
            "LOBQ1|1\n"
            "N|1|0|100|1 \n");

    EXPECT_TRUE(
        std::holds_alternative<
            ParseFailure>(trailing));
}

TEST(
    CandidateAdapterTransportTest,
    RejectsNonCanonicalAndOverflowingScalars) {
    expect_error(
        "LOBQ1|1\nC|-1\n",
        ParseError::
            InvalidNumericGrammar);

    expect_error(
        "LOBQ1|1\nC|+1\n",
        ParseError::
            InvalidNumericGrammar);

    expect_error(
        "LOBQ1|1\nC|01\n",
        ParseError::
            InvalidNumericGrammar);

    expect_error(
        "LOBQ1|1\nM|1|-0|1\n",
        ParseError::
            InvalidNumericGrammar);

    expect_error(
        "LOBQ1|1\nC|abc\n",
        ParseError::
            InvalidNumericGrammar);

    expect_error(
        "LOBQ1|1\n"
        "C|18446744073709551616\n",
        ParseError::ScalarOutOfRange);

    expect_error(
        "LOBQ1|1\n"
        "M|1|9223372036854775808|1\n",
        ParseError::ScalarOutOfRange);

    expect_error(
        "LOBQ1|1\n"
        "N|1|256|100|1\n",
        ParseError::ScalarOutOfRange);
}

TEST(
    CandidateAdapterTransportTest,
    PreservesRepresentationBoundaryValues) {
    const auto stream =
        require_stream(
            "LOBQ1|1\n"
            "N|18446744073709551615|255|"
            "-9223372036854775808|0\n"
            "M|0|9223372036854775807|"
            "18446744073709551615\n"
            "C|0\n");

    ASSERT_EQ(
        stream.commands.size(),
        3U);

    const auto& raw_new =
        std::get<RawNew>(
            stream.commands[0]);

    EXPECT_EQ(
        raw_new.order_id,
        std::numeric_limits<
            OrderId::rep>::max());

    EXPECT_EQ(
        raw_new.side_code,
        std::numeric_limits<
            std::uint8_t>::max());

    EXPECT_EQ(
        raw_new.price_ticks,
        std::numeric_limits<
            Price::rep>::min());

    EXPECT_EQ(
        raw_new.quantity_units,
        0U);

    const auto& raw_modify =
        std::get<RawModify>(
            stream.commands[1]);

    EXPECT_EQ(
        raw_modify.order_id,
        0U);

    EXPECT_EQ(
        raw_modify.price_ticks,
        std::numeric_limits<
            Price::rep>::max());

    EXPECT_EQ(
        raw_modify.quantity_units,
        std::numeric_limits<
            Quantity::rep>::max());

    EXPECT_EQ(
        std::get<RawCancel>(
            stream.commands[2])
            .order_id,
        0U);
}

TEST(
    CandidateAdapterTransportTest,
    MalformedSuffixPreventsParsedStreamCreation) {
    const auto result =
        parse_text(
            "LOBQ1|1\n"
            "N|1|0|100|1\n"
            "C|01\n");

    ASSERT_TRUE(
        std::holds_alternative<
            ParseFailure>(result));

    EXPECT_EQ(
        std::get<ParseFailure>(
            result).error,
        ParseError::
            InvalidNumericGrammar);
}

TEST(
    CandidateAdapterDomainTest,
    RoutesFactoryValidationAndPreservesPrecedence) {
    const auto run =
        execute_candidate(
            require_stream(
                "LOBQ1|1\n"
                "N|1|2|0|0\n"
                "N|2|2|100|0\n"
                "N|3|2|100|1\n"
                "N|4|255|100|1\n"));

    ASSERT_EQ(
        run.entries.size(),
        4U);

    expect_rejected(
        entry(run, 0),
        DomainError::InvalidPrice);

    expect_rejected(
        entry(run, 1),
        DomainError::InvalidQuantity);

    expect_rejected(
        entry(run, 2),
        DomainError::InvalidSide);

    expect_rejected(
        entry(run, 3),
        DomainError::InvalidSide);

    for (const auto& item :
         run.entries) {
        EXPECT_TRUE(
            item.observation
                .snapshot.bids.empty());

        EXPECT_TRUE(
            item.observation
                .snapshot.asks.empty());

        ASSERT_TRUE(
            item.observation
                .snapshot.next_sequence
                .has_value());

        EXPECT_EQ(
            item.observation
                .snapshot.next_sequence
                ->value(),
            1U);
    }
}

TEST(
    CandidateAdapterDomainTest,
    RoutesEngineStateErrorsWithoutAdapterReimplementation) {
    const auto run =
        execute_candidate(
            require_stream(
                "LOBQ1|1\n"
                "N|1|0|100|1\n"
                "N|1|1|101|1\n"
                "C|99\n"
                "M|99|100|1\n"
                "M|1|100|1\n"));

    ASSERT_EQ(
        run.entries.size(),
        5U);

    expect_accepted(
        entry(run, 0));

    expect_rejected(
        entry(run, 1),
        DomainError::DuplicateOrderId);

    expect_rejected(
        entry(run, 2),
        DomainError::UnknownOrderId);

    expect_rejected(
        entry(run, 3),
        DomainError::UnknownOrderId);

    expect_rejected(
        entry(run, 4),
        DomainError::
            InvalidModification);
}

TEST(
    CandidateAdapterObservationTest,
    RetainsRawCommandAndPostCommandSnapshot) {
    const auto run =
        execute_candidate(
            require_stream(
                "LOBQ1|1\n"
                "N|7|0|100|5\n"));

    ASSERT_EQ(
        run.entries.size(),
        1U);

    const auto& value =
        entry(run, 0);

    expect_accepted(value);

    ASSERT_TRUE(
        std::holds_alternative<
            RawNew>(value.command));

    EXPECT_EQ(
        std::get<RawNew>(
            value.command),
        (RawNew{7, 0, 100, 5}));

    ASSERT_EQ(
        value.observation
            .snapshot.bids.size(),
        1U);

    const auto& bid =
        value.observation
            .snapshot.bids.front();

    EXPECT_EQ(
        bid.order_id,
        OrderId{7});

    EXPECT_EQ(
        bid.side,
        Side::Buy);

    EXPECT_EQ(
        bid.price.ticks(),
        100);

    EXPECT_EQ(
        bid.remaining.units(),
        5U);

    EXPECT_EQ(
        bid.sequence.value(),
        1U);

    ASSERT_TRUE(
        value.observation
            .snapshot.next_sequence
            .has_value());

    EXPECT_EQ(
        value.observation
            .snapshot.next_sequence
            ->value(),
        2U);
}

TEST(
    CandidateAdapterAllocatorTest,
    AllocatesUint64MaximumExactlyOnce) {
    const auto run =
        execute_candidate(
            require_stream(
                "LOBQ1|18446744073709551615\n"
                "N|1|0|100|1\n"
                "N|2|0|101|1\n"));

    ASSERT_EQ(
        run.entries.size(),
        2U);

    expect_accepted(
        entry(run, 0));

    EXPECT_FALSE(
        entry(run, 0)
            .observation.snapshot
            .next_sequence.has_value());

    expect_rejected(
        entry(run, 1),
        DomainError::
            SequenceExhausted);

    EXPECT_FALSE(
        entry(run, 1)
            .observation.snapshot
            .next_sequence.has_value());

    EXPECT_EQ(
        entry(run, 1)
            .observation.snapshot,
        entry(run, 0)
            .observation.snapshot);
}

TEST(
    CandidateAdapterAllocatorTest,
    ExplicitExhaustionRejectsFreshSequenceOperation) {
    const auto run =
        execute_candidate(
            require_stream(
                "LOBQ1|EXHAUSTED\n"
                "N|1|0|100|1\n"));

    ASSERT_EQ(
        run.entries.size(),
        1U);

    expect_rejected(
        entry(run, 0),
        DomainError::
            SequenceExhausted);

    EXPECT_TRUE(
        entry(run, 0)
            .observation.snapshot
            .bids.empty());

    EXPECT_TRUE(
        entry(run, 0)
            .observation.snapshot
            .asks.empty());

    EXPECT_FALSE(
        entry(run, 0)
            .observation.snapshot
            .next_sequence.has_value());
}

TEST(
    CandidateAdapterAllocatorTest,
    CancelRemainsAvailableAfterExhaustion) {
    const auto run =
        execute_candidate(
            require_stream(
                "LOBQ1|18446744073709551615\n"
                "N|1|1|101|2\n"
                "C|1\n"));

    ASSERT_EQ(
        run.entries.size(),
        2U);

    expect_accepted(
        entry(run, 0));

    expect_accepted(
        entry(run, 1));

    EXPECT_TRUE(
        entry(run, 1)
            .observation.snapshot
            .bids.empty());

    EXPECT_TRUE(
        entry(run, 1)
            .observation.snapshot
            .asks.empty());

    EXPECT_FALSE(
        entry(run, 1)
            .observation.snapshot
            .next_sequence.has_value());
}

TEST(
    CandidateAdapterAllocatorTest,
    PriorityRetainingReductionWorksAfterExhaustion) {
    const auto run =
        execute_candidate(
            require_stream(
                "LOBQ1|18446744073709551615\n"
                "N|1|0|100|2\n"
                "M|1|100|1\n"));

    ASSERT_EQ(
        run.entries.size(),
        2U);

    expect_accepted(
        entry(run, 0));

    expect_accepted(
        entry(run, 1));

    const auto& snapshot =
        entry(run, 1)
            .observation.snapshot;

    ASSERT_EQ(
        snapshot.bids.size(),
        1U);

    EXPECT_EQ(
        snapshot.bids.front()
            .order_id,
        OrderId{1});

    EXPECT_EQ(
        snapshot.bids.front()
            .remaining.units(),
        1U);

    EXPECT_EQ(
        snapshot.bids.front()
            .sequence.value(),
        std::numeric_limits<
            SequenceNumber::rep>::max());

    EXPECT_FALSE(
        snapshot.next_sequence
            .has_value());
}

TEST(
    CandidateAdapterAllocatorTest,
    PriorityLosingModifyRejectsAfterExhaustion) {
    const auto run =
        execute_candidate(
            require_stream(
                "LOBQ1|18446744073709551615\n"
                "N|1|0|100|1\n"
                "M|1|100|2\n"));

    ASSERT_EQ(
        run.entries.size(),
        2U);

    expect_accepted(
        entry(run, 0));

    expect_rejected(
        entry(run, 1),
        DomainError::
            SequenceExhausted);

    EXPECT_EQ(
        entry(run, 1)
            .observation.snapshot,
        entry(run, 0)
            .observation.snapshot);
}

TEST(
    CandidateAdapterObservationTest,
    PreservesExactTradeEmissionOrder) {
    const auto run =
        execute_candidate(
            require_stream(
                "LOBQ1|1\n"
                "N|1|1|100|1\n"
                "N|2|1|101|1\n"
                "N|3|0|101|2\n"));

    ASSERT_EQ(
        run.entries.size(),
        3U);

    const auto& final =
        entry(run, 2);

    expect_accepted(final);

    ASSERT_EQ(
        final.observation
            .trades.size(),
        2U);

    EXPECT_EQ(
        final.observation
            .trades[0].maker,
        OrderId{1});

    EXPECT_EQ(
        final.observation
            .trades[0].taker,
        OrderId{3});

    EXPECT_EQ(
        final.observation
            .trades[0].price.ticks(),
        100);

    EXPECT_EQ(
        final.observation
            .trades[0].quantity.units(),
        1U);

    EXPECT_EQ(
        final.observation
            .trades[1].maker,
        OrderId{2});

    EXPECT_EQ(
        final.observation
            .trades[1].taker,
        OrderId{3});

    EXPECT_EQ(
        final.observation
            .trades[1].price.ticks(),
        101);

    EXPECT_EQ(
        final.observation
            .trades[1].quantity.units(),
        1U);

    EXPECT_TRUE(
        final.observation
            .snapshot.bids.empty());

    EXPECT_TRUE(
        final.observation
            .snapshot.asks.empty());
}

TEST(
    CandidateAdapterObservationTest,
    PreservesEngineSnapshotBookOrdering) {
    const auto run =
        execute_candidate(
            require_stream(
                "LOBQ1|1\n"
                "N|1|0|99|1\n"
                "N|2|0|101|1\n"
                "N|3|1|105|1\n"
                "N|4|1|103|1\n"));

    ASSERT_EQ(
        run.entries.size(),
        4U);

    const auto& snapshot =
        entry(run, 3)
            .observation.snapshot;

    ASSERT_EQ(
        snapshot.bids.size(),
        2U);

    EXPECT_EQ(
        snapshot.bids[0]
            .order_id,
        OrderId{2});

    EXPECT_EQ(
        snapshot.bids[0]
            .price.ticks(),
        101);

    EXPECT_EQ(
        snapshot.bids[1]
            .order_id,
        OrderId{1});

    EXPECT_EQ(
        snapshot.bids[1]
            .price.ticks(),
        99);

    ASSERT_EQ(
        snapshot.asks.size(),
        2U);

    EXPECT_EQ(
        snapshot.asks[0]
            .order_id,
        OrderId{4});

    EXPECT_EQ(
        snapshot.asks[0]
            .price.ticks(),
        103);

    EXPECT_EQ(
        snapshot.asks[1]
            .order_id,
        OrderId{3});

    EXPECT_EQ(
        snapshot.asks[1]
            .price.ticks(),
        105);
}

TEST(
    CandidateAdapterObservationTest,
    RejectionIsAtomicAndCarriesEmptyTrades) {
    const auto run =
        execute_candidate(
            require_stream(
                "LOBQ1|1\n"
                "N|1|0|100|2\n"
                "N|1|1|101|3\n"));

    ASSERT_EQ(
        run.entries.size(),
        2U);

    expect_accepted(
        entry(run, 0));

    expect_rejected(
        entry(run, 1),
        DomainError::
            DuplicateOrderId);

    EXPECT_EQ(
        entry(run, 1)
            .observation.snapshot,
        entry(run, 0)
            .observation.snapshot);
}

TEST(
    CandidateAdapterDomainTest,
    RoutesModifyFactoryValidationAndPreservesPrecedence) {
    const auto run =
        execute_candidate(
            require_stream(
                "LOBQ1|1\n"
                "M|91|0|0\n"
                "M|92|100|0\n"));

    ASSERT_EQ(
        run.entries.size(),
        2U);

    expect_rejected(
        entry(run, 0),
        DomainError::InvalidPrice);

    expect_rejected(
        entry(run, 1),
        DomainError::InvalidQuantity);

    for (const auto& item :
         run.entries) {
        EXPECT_TRUE(
            item.observation
                .snapshot.bids.empty());

        EXPECT_TRUE(
            item.observation
                .snapshot.asks.empty());

        ASSERT_TRUE(
            item.observation
                .snapshot.next_sequence
                .has_value());

        EXPECT_EQ(
            item.observation
                .snapshot.next_sequence
                ->value(),
            1U);
    }
}

}  // namespace
