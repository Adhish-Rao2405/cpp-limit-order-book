#include "lob/matching_engine.hpp"

#include <gtest/gtest.h>

#include <cstdint>
#include <limits>
#include <optional>
#include <type_traits>
#include <variant>
#include <vector>

#if !defined(LOB_ENABLE_MATCHING_ENGINE_QUALIFICATION)
#error "Matching-engine qualification access must be enabled for unit tests"
#endif

namespace lob::detail {

class MatchingEngineQualificationAccess final {
public:
    static void set_next_sequence(
        MatchingEngine& engine,
        std::optional<SequenceNumber> next_sequence) {
        engine.next_sequence_ = next_sequence;
    }

    [[nodiscard]] static bool reverse_price_level(
        MatchingEngine& engine,
        Side side,
        Price price) {
        if (side == Side::Buy) {
            const auto level = engine.bids_.find(price);
            if (level == engine.bids_.end()) {
                return false;
            }

            level->second.reverse();
            return true;
        }

        if (side == Side::Sell) {
            const auto level = engine.asks_.find(price);
            if (level == engine.asks_.end()) {
                return false;
            }

            level->second.reverse();
            return true;
        }

        return false;
    }

    [[nodiscard]] static bool invariants_hold(
        const MatchingEngine& engine) {
        return engine.invariants_hold();
    }
};

}  // namespace lob::detail

namespace {

using lob::CancelOrder;
using lob::DomainError;
using lob::EngineSnapshot;
using lob::ExecutionReport;
using lob::MatchingEngine;
using lob::ModifyOrder;
using lob::NewOrder;
using lob::OrderId;
using lob::Price;
using lob::Quantity;
using lob::RestingOrderView;
using lob::SequenceNumber;
using lob::Side;
using lob::Trade;
using lob::detail::MatchingEngineQualificationAccess;

static_assert(!std::is_copy_constructible_v<MatchingEngine>);
static_assert(!std::is_copy_assignable_v<MatchingEngine>);
static_assert(!std::is_move_constructible_v<MatchingEngine>);
static_assert(!std::is_move_assignable_v<MatchingEngine>);

[[nodiscard]] Price price(Price::rep ticks) {
    return Price::from_ticks(ticks).value();
}

[[nodiscard]] Quantity quantity(Quantity::rep units) {
    return Quantity::from_units(units).value();
}

[[nodiscard]] SequenceNumber sequence(SequenceNumber::rep value) {
    return SequenceNumber::from_value(value).value();
}

[[nodiscard]] ModifyOrder modify_order(
    OrderId::rep order_id,
    Price::rep price_ticks,
    Quantity::rep quantity_units) {
    return std::get<ModifyOrder>(
        ModifyOrder::create(
            OrderId{order_id},
            price_ticks,
            quantity_units));
}

[[nodiscard]] NewOrder new_order(
    OrderId::rep order_id,
    Side side,
    Price::rep price_ticks,
    Quantity::rep quantity_units) {
    return std::get<NewOrder>(
        NewOrder::create(
            OrderId{order_id},
            side,
            price_ticks,
            quantity_units));
}

ExecutionReport accept(
    MatchingEngine& engine,
    const NewOrder& command) {
    return std::get<ExecutionReport>(engine.process(command));
}

TEST(MatchingEngineTest, StartsEmptyWithSequenceOneAvailable) {
    MatchingEngine engine;

    const auto snapshot = engine.snapshot();

    EXPECT_TRUE(snapshot.bids.empty());
    EXPECT_TRUE(snapshot.asks.empty());
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 1U);
}

TEST(MatchingEngineTest, NonCrossingBuyRestsAtLimitAndConsumesOneSequence) {
    MatchingEngine engine;

    const auto report =
        accept(engine, new_order(1, Side::Buy, 100, 5));

    EXPECT_TRUE(report.trades.empty());

    const auto snapshot = engine.snapshot();
    EXPECT_EQ(
        snapshot.bids,
        (std::vector<RestingOrderView>{
            {OrderId{1}, Side::Buy, price(100), quantity(5), sequence(1)}}));
    EXPECT_TRUE(snapshot.asks.empty());
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 2U);
}

TEST(MatchingEngineTest, NonCrossingSellRestsAtLimitAndConsumesOneSequence) {
    MatchingEngine engine;

    const auto report =
        accept(engine, new_order(1, Side::Sell, 101, 4));

    EXPECT_TRUE(report.trades.empty());

    const auto snapshot = engine.snapshot();
    EXPECT_TRUE(snapshot.bids.empty());
    EXPECT_EQ(
        snapshot.asks,
        (std::vector<RestingOrderView>{
            {OrderId{1}, Side::Sell, price(101), quantity(4), sequence(1)}}));
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 2U);
}

TEST(
    MatchingEngineTest,
    IncomingBuyMatchesLowestAskAtMakerPriceAndRetainsPartialMakerPriority) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Sell, 100, 5));

    const auto report =
        accept(engine, new_order(2, Side::Buy, 101, 3));

    EXPECT_EQ(
        report.trades,
        (std::vector<Trade>{
            {OrderId{1}, OrderId{2}, price(100), quantity(3)}}));

    const auto snapshot = engine.snapshot();
    EXPECT_TRUE(snapshot.bids.empty());
    EXPECT_EQ(
        snapshot.asks,
        (std::vector<RestingOrderView>{
            {OrderId{1}, Side::Sell, price(100), quantity(2), sequence(1)}}));
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 3U);
}

TEST(
    MatchingEngineTest,
    IncomingSellMatchesHighestBidAtMakerPriceAndRetainsPartialMakerPriority) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 105, 4));

    const auto report =
        accept(engine, new_order(2, Side::Sell, 100, 2));

    EXPECT_EQ(
        report.trades,
        (std::vector<Trade>{
            {OrderId{1}, OrderId{2}, price(105), quantity(2)}}));

    const auto snapshot = engine.snapshot();
    EXPECT_EQ(
        snapshot.bids,
        (std::vector<RestingOrderView>{
            {OrderId{1}, Side::Buy, price(105), quantity(2), sequence(1)}}));
    EXPECT_TRUE(snapshot.asks.empty());
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 3U);
}

TEST(MatchingEngineTest, EqualPriceMakersExecuteFifo) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Sell, 100, 2));
    accept(engine, new_order(2, Side::Sell, 100, 2));

    const auto report =
        accept(engine, new_order(3, Side::Buy, 100, 3));

    EXPECT_EQ(
        report.trades,
        (std::vector<Trade>{
            {OrderId{1}, OrderId{3}, price(100), quantity(2)},
            {OrderId{2}, OrderId{3}, price(100), quantity(1)}}));

    const auto snapshot = engine.snapshot();
    EXPECT_EQ(
        snapshot.asks,
        (std::vector<RestingOrderView>{
            {OrderId{2}, Side::Sell, price(100), quantity(1), sequence(2)}}));
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 4U);
}

TEST(
    MatchingEngineTest,
    SweepsMultipleAskLevelsThenRestsResidualAtIncomingPrice) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Sell, 100, 2));
    accept(engine, new_order(2, Side::Sell, 101, 2));

    const auto report =
        accept(engine, new_order(3, Side::Buy, 102, 5));

    EXPECT_EQ(
        report.trades,
        (std::vector<Trade>{
            {OrderId{1}, OrderId{3}, price(100), quantity(2)},
            {OrderId{2}, OrderId{3}, price(101), quantity(2)}}));

    const auto snapshot = engine.snapshot();
    EXPECT_EQ(
        snapshot.bids,
        (std::vector<RestingOrderView>{
            {OrderId{3}, Side::Buy, price(102), quantity(1), sequence(3)}}));
    EXPECT_TRUE(snapshot.asks.empty());
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 4U);
}

TEST(MatchingEngineTest, StopsAtLimitAndLeavesBookUncrossed) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Sell, 101, 2));

    const auto report =
        accept(engine, new_order(2, Side::Buy, 100, 2));

    EXPECT_TRUE(report.trades.empty());

    const auto snapshot = engine.snapshot();
    EXPECT_EQ(
        snapshot.bids,
        (std::vector<RestingOrderView>{
            {OrderId{2}, Side::Buy, price(100), quantity(2), sequence(2)}}));
    EXPECT_EQ(
        snapshot.asks,
        (std::vector<RestingOrderView>{
            {OrderId{1}, Side::Sell, price(101), quantity(2), sequence(1)}}));
    EXPECT_LT(snapshot.bids.front().price, snapshot.asks.front().price);
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 3U);
}

TEST(MatchingEngineTest, DuplicateActiveIdIsRejectedAtomically) {
    MatchingEngine engine;

    accept(engine, new_order(7, Side::Buy, 100, 2));
    const EngineSnapshot before = engine.snapshot();

    const auto result =
        engine.process(new_order(7, Side::Sell, 101, 3));

    ASSERT_TRUE(std::holds_alternative<DomainError>(result));
    EXPECT_EQ(
        std::get<DomainError>(result),
        DomainError::DuplicateOrderId);
    EXPECT_EQ(engine.snapshot(), before);
}

TEST(
    MatchingEngineTest,
    FullyFilledMakerIdCanBeReusedAndFullyExecutedTakerConsumesSequence) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Sell, 100, 1));

    const auto fill =
        accept(engine, new_order(2, Side::Buy, 100, 1));

    EXPECT_EQ(
        fill.trades,
        (std::vector<Trade>{
            {OrderId{1}, OrderId{2}, price(100), quantity(1)}}));

    auto snapshot = engine.snapshot();
    EXPECT_TRUE(snapshot.bids.empty());
    EXPECT_TRUE(snapshot.asks.empty());
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 3U);

    const auto reused =
        accept(engine, new_order(1, Side::Buy, 99, 1));

    EXPECT_TRUE(reused.trades.empty());

    snapshot = engine.snapshot();
    EXPECT_EQ(
        snapshot.bids,
        (std::vector<RestingOrderView>{
            {OrderId{1}, Side::Buy, price(99), quantity(1), sequence(3)}}));
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 4U);
}

TEST(MatchingEngineTest, SnapshotOrdersBooksBestToWorstAndFifoWithinLevel) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 100, 1));
    accept(engine, new_order(2, Side::Buy, 102, 1));
    accept(engine, new_order(3, Side::Buy, 100, 1));
    accept(engine, new_order(4, Side::Sell, 105, 1));
    accept(engine, new_order(5, Side::Sell, 104, 1));

    const auto snapshot = engine.snapshot();

    EXPECT_EQ(
        snapshot.bids,
        (std::vector<RestingOrderView>{
            {OrderId{2}, Side::Buy, price(102), quantity(1), sequence(2)},
            {OrderId{1}, Side::Buy, price(100), quantity(1), sequence(1)},
            {OrderId{3}, Side::Buy, price(100), quantity(1), sequence(3)}}));

    EXPECT_EQ(
        snapshot.asks,
        (std::vector<RestingOrderView>{
            {OrderId{5}, Side::Sell, price(104), quantity(1), sequence(5)},
            {OrderId{4}, Side::Sell, price(105), quantity(1), sequence(4)}}));

    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 6U);
}

TEST(MatchingEngineTest, UnknownCancelIsRejectedAtomicallyAndConsumesNoSequence) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 100, 2));
    const EngineSnapshot before = engine.snapshot();

    const auto result =
        engine.process(CancelOrder{OrderId{99}});

    ASSERT_TRUE(std::holds_alternative<DomainError>(result));
    EXPECT_EQ(
        std::get<DomainError>(result),
        DomainError::UnknownOrderId);
    EXPECT_EQ(engine.snapshot(), before);
}

TEST(
    MatchingEngineTest,
    CancelBidRemovesOnlyTargetFromFifoLevelAndConsumesNoSequence) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 100, 1));
    accept(engine, new_order(2, Side::Buy, 100, 1));
    accept(engine, new_order(3, Side::Buy, 100, 1));

    const auto result =
        engine.process(CancelOrder{OrderId{2}});

    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(result));
    EXPECT_TRUE(std::get<ExecutionReport>(result).trades.empty());

    const auto snapshot = engine.snapshot();
    EXPECT_EQ(
        snapshot.bids,
        (std::vector<RestingOrderView>{
            {OrderId{1}, Side::Buy, price(100), quantity(1), sequence(1)},
            {OrderId{3}, Side::Buy, price(100), quantity(1), sequence(3)}}));
    EXPECT_TRUE(snapshot.asks.empty());
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 4U);
}

TEST(
    MatchingEngineTest,
    CancelAskRemovesEmptyPriceLevelWithoutDisturbingOtherLevel) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Sell, 100, 1));
    accept(engine, new_order(2, Side::Sell, 101, 2));

    const auto result =
        engine.process(CancelOrder{OrderId{1}});

    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(result));
    EXPECT_TRUE(std::get<ExecutionReport>(result).trades.empty());

    const auto snapshot = engine.snapshot();
    EXPECT_TRUE(snapshot.bids.empty());
    EXPECT_EQ(
        snapshot.asks,
        (std::vector<RestingOrderView>{
            {OrderId{2}, Side::Sell, price(101), quantity(2), sequence(2)}}));
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 3U);
}

TEST(MatchingEngineTest, CancelledOrderIdCanBeReusedWithFreshSequence) {
    MatchingEngine engine;

    accept(engine, new_order(5, Side::Buy, 99, 2));

    const auto cancelled =
        engine.process(CancelOrder{OrderId{5}});

    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(cancelled));
    EXPECT_TRUE(std::get<ExecutionReport>(cancelled).trades.empty());

    const auto reused =
        accept(engine, new_order(5, Side::Sell, 101, 3));

    EXPECT_TRUE(reused.trades.empty());

    const auto snapshot = engine.snapshot();
    EXPECT_TRUE(snapshot.bids.empty());
    EXPECT_EQ(
        snapshot.asks,
        (std::vector<RestingOrderView>{
            {OrderId{5}, Side::Sell, price(101), quantity(3), sequence(2)}}));
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 3U);
}
TEST(MatchingEngineTest, UnknownModifyIsRejectedAtomicallyAndConsumesNoSequence) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 100, 2));
    const EngineSnapshot before = engine.snapshot();

    const auto result =
        engine.process(modify_order(99, 101, 3));

    ASSERT_TRUE(std::holds_alternative<DomainError>(result));
    EXPECT_EQ(
        std::get<DomainError>(result),
        DomainError::UnknownOrderId);
    EXPECT_EQ(engine.snapshot(), before);
}

TEST(MatchingEngineTest, UnchangedModifyIsRejectedAtomically) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 100, 5));
    const EngineSnapshot before = engine.snapshot();

    const auto result =
        engine.process(modify_order(1, 100, 5));

    ASSERT_TRUE(std::holds_alternative<DomainError>(result));
    EXPECT_EQ(
        std::get<DomainError>(result),
        DomainError::InvalidModification);
    EXPECT_EQ(engine.snapshot(), before);
}

TEST(
    MatchingEngineTest,
    SamePriceReductionRetainsSequenceQueuePositionAndConsumesNoSequence) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 100, 5));
    accept(engine, new_order(2, Side::Buy, 100, 5));

    const auto result =
        engine.process(modify_order(1, 100, 3));

    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(result));
    EXPECT_TRUE(std::get<ExecutionReport>(result).trades.empty());

    auto snapshot = engine.snapshot();
    EXPECT_EQ(
        snapshot.bids,
        (std::vector<RestingOrderView>{
            {OrderId{1}, Side::Buy, price(100), quantity(3), sequence(1)},
            {OrderId{2}, Side::Buy, price(100), quantity(5), sequence(2)}}));
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 3U);

    const auto sweep =
        accept(engine, new_order(3, Side::Sell, 100, 4));

    EXPECT_EQ(
        sweep.trades,
        (std::vector<Trade>{
            {OrderId{1}, OrderId{3}, price(100), quantity(3)},
            {OrderId{2}, OrderId{3}, price(100), quantity(1)}}));
}

TEST(
    MatchingEngineTest,
    SamePriceBidQuantityIncreaseLosesPriorityAndConsumesFreshSequence) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 100, 2));
    accept(engine, new_order(2, Side::Buy, 100, 2));

    const auto result =
        engine.process(modify_order(1, 100, 3));

    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(result));
    EXPECT_TRUE(std::get<ExecutionReport>(result).trades.empty());

    const auto snapshot = engine.snapshot();
    EXPECT_EQ(
        snapshot.bids,
        (std::vector<RestingOrderView>{
            {OrderId{2}, Side::Buy, price(100), quantity(2), sequence(2)},
            {OrderId{1}, Side::Buy, price(100), quantity(3), sequence(3)}}));
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 4U);
}

TEST(
    MatchingEngineTest,
    SamePriceAskQuantityIncreaseLosesPriorityAndConsumesFreshSequence) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Sell, 105, 2));
    accept(engine, new_order(2, Side::Sell, 105, 2));

    const auto result =
        engine.process(modify_order(1, 105, 4));

    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(result));
    EXPECT_TRUE(std::get<ExecutionReport>(result).trades.empty());

    const auto snapshot = engine.snapshot();
    EXPECT_EQ(
        snapshot.asks,
        (std::vector<RestingOrderView>{
            {OrderId{2}, Side::Sell, price(105), quantity(2), sequence(2)},
            {OrderId{1}, Side::Sell, price(105), quantity(4), sequence(3)}}));
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 4U);
}

TEST(
    MatchingEngineTest,
    BuyPriceChangeUsesFreshSequenceAndCanExecuteAtRestingAskPrice) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 99, 2));
    accept(engine, new_order(2, Side::Sell, 101, 1));

    const auto result =
        engine.process(modify_order(1, 101, 1));

    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(result));
    EXPECT_EQ(
        std::get<ExecutionReport>(result).trades,
        (std::vector<Trade>{
            {OrderId{2}, OrderId{1}, price(101), quantity(1)}}));

    const auto snapshot = engine.snapshot();
    EXPECT_TRUE(snapshot.bids.empty());
    EXPECT_TRUE(snapshot.asks.empty());
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 4U);
}

TEST(
    MatchingEngineTest,
    SellPriceChangeUsesFreshSequenceAndCanExecuteAtRestingBidPrice) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Sell, 106, 2));
    accept(engine, new_order(2, Side::Buy, 104, 1));

    const auto result =
        engine.process(modify_order(1, 104, 1));

    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(result));
    EXPECT_EQ(
        std::get<ExecutionReport>(result).trades,
        (std::vector<Trade>{
            {OrderId{2}, OrderId{1}, price(104), quantity(1)}}));

    const auto snapshot = engine.snapshot();
    EXPECT_TRUE(snapshot.bids.empty());
    EXPECT_TRUE(snapshot.asks.empty());
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 4U);
}

TEST(
    MatchingEngineTest,
    ModifyClassificationUsesCurrentRemainingQuantityAfterPartialFill) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Sell, 100, 5));
    accept(engine, new_order(2, Side::Buy, 100, 2));

    const EngineSnapshot before = engine.snapshot();

    const auto result =
        engine.process(modify_order(1, 100, 3));

    ASSERT_TRUE(std::holds_alternative<DomainError>(result));
    EXPECT_EQ(
        std::get<DomainError>(result),
        DomainError::InvalidModification);
    EXPECT_EQ(engine.snapshot(), before);
}
TEST(MatchingEngineTest, InvariantCheckerAcceptsEmptyAndMixedReachableStates) {
    MatchingEngine engine;

    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));

    accept(engine, new_order(1, Side::Sell, 101, 5));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));

    accept(engine, new_order(2, Side::Buy, 100, 4));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));

    const auto reduced =
        engine.process(modify_order(2, 100, 2));
    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(reduced));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));

    accept(engine, new_order(3, Side::Buy, 101, 3));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));

    const auto cancelled =
        engine.process(CancelOrder{OrderId{2}});
    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(cancelled));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    InvariantCheckerRejectsDecreasingBidFifoSequenceOrder) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 100, 3));
    accept(engine, new_order(2, Side::Buy, 100, 5));

    const auto before = engine.snapshot();
    ASSERT_EQ(
        before.bids,
        (std::vector<RestingOrderView>{
            {OrderId{1}, Side::Buy, price(100), quantity(3), sequence(1)},
            {OrderId{2}, Side::Buy, price(100), quantity(5), sequence(2)}}));
    ASSERT_TRUE(before.asks.empty());
    ASSERT_EQ(before.next_sequence, SequenceNumber::from_value(3));
    ASSERT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));

    ASSERT_TRUE(MatchingEngineQualificationAccess::reverse_price_level(
        engine, Side::Buy, price(100)));

    auto expected = before;
    expected.bids = {before.bids[1], before.bids[0]};
    const auto after = engine.snapshot();
    ASSERT_EQ(after, expected);
    ASSERT_EQ(after.bids[0].sequence, sequence(2));
    ASSERT_EQ(after.bids[1].sequence, sequence(1));

    EXPECT_FALSE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    InvariantCheckerRejectsDecreasingAskFifoSequenceOrderWhenAllocatorExhausted) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Sell, 101, 3));
    accept(engine, new_order(2, Side::Sell, 101, 5));

    const auto before = engine.snapshot();
    ASSERT_TRUE(before.bids.empty());
    ASSERT_EQ(
        before.asks,
        (std::vector<RestingOrderView>{
            {OrderId{1}, Side::Sell, price(101), quantity(3), sequence(1)},
            {OrderId{2}, Side::Sell, price(101), quantity(5), sequence(2)}}));
    ASSERT_EQ(before.next_sequence, SequenceNumber::from_value(3));
    ASSERT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));

    MatchingEngineQualificationAccess::set_next_sequence(engine, std::nullopt);
    auto expected = before;
    expected.next_sequence.reset();
    ASSERT_EQ(engine.snapshot(), expected);
    ASSERT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));

    ASSERT_TRUE(MatchingEngineQualificationAccess::reverse_price_level(
        engine, Side::Sell, price(101)));

    expected.asks = {before.asks[1], before.asks[0]};
    const auto after = engine.snapshot();
    ASSERT_EQ(after, expected);
    ASSERT_EQ(after.asks[0].sequence, sequence(2));
    ASSERT_EQ(after.asks[1].sequence, sequence(1));

    EXPECT_FALSE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    InvariantCheckerAcceptsStrictlyIncreasingNonContiguousFifoSequences) {
    MatchingEngine engine;

    MatchingEngineQualificationAccess::set_next_sequence(engine, sequence(2));
    accept(engine, new_order(1, Side::Buy, 100, 3));
    MatchingEngineQualificationAccess::set_next_sequence(engine, sequence(7));
    accept(engine, new_order(2, Side::Buy, 100, 5));
    MatchingEngineQualificationAccess::set_next_sequence(engine, sequence(20));
    accept(engine, new_order(3, Side::Sell, 101, 4));
    MatchingEngineQualificationAccess::set_next_sequence(engine, sequence(30));
    accept(engine, new_order(4, Side::Sell, 101, 6));

    const auto snapshot = engine.snapshot();
    ASSERT_EQ(
        snapshot.bids,
        (std::vector<RestingOrderView>{
            {OrderId{1}, Side::Buy, price(100), quantity(3), sequence(2)},
            {OrderId{2}, Side::Buy, price(100), quantity(5), sequence(7)}}));
    ASSERT_EQ(
        snapshot.asks,
        (std::vector<RestingOrderView>{
            {OrderId{3}, Side::Sell, price(101), quantity(4), sequence(20)},
            {OrderId{4}, Side::Sell, price(101), quantity(6), sequence(30)}}));
    ASSERT_EQ(snapshot.next_sequence, SequenceNumber::from_value(31));

    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(MatchingEngineTest, InvariantCheckerDetectsAllocatorOrderingViolation) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 100, 1));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));

    MatchingEngineQualificationAccess::set_next_sequence(
        engine,
        SequenceNumber::from_value(1));

    EXPECT_FALSE(MatchingEngineQualificationAccess::invariants_hold(engine));

    MatchingEngineQualificationAccess::set_next_sequence(
        engine,
        SequenceNumber::from_value(2));

    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    MaximumSequenceAllocatesExactlyOnceForRestingOrderThenDoesNotWrap) {
    MatchingEngine engine;

    MatchingEngineQualificationAccess::set_next_sequence(
        engine,
        SequenceNumber::from_value(
            std::numeric_limits<SequenceNumber::rep>::max()));

    const auto result =
        engine.process(new_order(1, Side::Buy, 100, 1));

    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(result));
    EXPECT_TRUE(std::get<ExecutionReport>(result).trades.empty());

    const auto snapshot = engine.snapshot();
    ASSERT_EQ(snapshot.bids.size(), 1U);
    EXPECT_EQ(
        snapshot.bids.front().sequence.value(),
        std::numeric_limits<SequenceNumber::rep>::max());
    EXPECT_FALSE(snapshot.next_sequence.has_value());
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    MaximumSequenceIsConsumedEvenWhenAcceptedNewOrderFullyExecutes) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Sell, 100, 1));

    MatchingEngineQualificationAccess::set_next_sequence(
        engine,
        SequenceNumber::from_value(
            std::numeric_limits<SequenceNumber::rep>::max()));

    const auto result =
        engine.process(new_order(2, Side::Buy, 100, 1));

    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(result));
    EXPECT_EQ(
        std::get<ExecutionReport>(result).trades,
        (std::vector<Trade>{
            {OrderId{1}, OrderId{2}, price(100), quantity(1)}}));

    const auto snapshot = engine.snapshot();
    EXPECT_TRUE(snapshot.bids.empty());
    EXPECT_TRUE(snapshot.asks.empty());
    EXPECT_FALSE(snapshot.next_sequence.has_value());
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(MatchingEngineTest, ExhaustedNewOrderIsRejectedAtomically) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 99, 1));

    MatchingEngineQualificationAccess::set_next_sequence(
        engine,
        std::nullopt);

    const EngineSnapshot before = engine.snapshot();

    const auto result =
        engine.process(new_order(2, Side::Sell, 101, 1));

    ASSERT_TRUE(std::holds_alternative<DomainError>(result));
    EXPECT_EQ(
        std::get<DomainError>(result),
        DomainError::SequenceExhausted);
    EXPECT_EQ(engine.snapshot(), before);
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    DuplicateActiveIdPrecedesSequenceExhaustionForNewOrder) {
    MatchingEngine engine;

    accept(engine, new_order(7, Side::Buy, 100, 2));

    MatchingEngineQualificationAccess::set_next_sequence(
        engine,
        std::nullopt);

    const EngineSnapshot before = engine.snapshot();

    const auto result =
        engine.process(new_order(7, Side::Sell, 101, 3));

    ASSERT_TRUE(std::holds_alternative<DomainError>(result));
    EXPECT_EQ(
        std::get<DomainError>(result),
        DomainError::DuplicateOrderId);
    EXPECT_EQ(engine.snapshot(), before);
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    PriorityLosingModifyRejectsBeforeDestructionWhenSequenceExhausted) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 100, 2));

    MatchingEngineQualificationAccess::set_next_sequence(
        engine,
        std::nullopt);

    const EngineSnapshot before = engine.snapshot();

    const auto result =
        engine.process(modify_order(1, 100, 3));

    ASSERT_TRUE(std::holds_alternative<DomainError>(result));
    EXPECT_EQ(
        std::get<DomainError>(result),
        DomainError::SequenceExhausted);
    EXPECT_EQ(engine.snapshot(), before);
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    SamePriceReductionStillSucceedsAfterSequenceExhaustion) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 100, 2));

    MatchingEngineQualificationAccess::set_next_sequence(
        engine,
        std::nullopt);

    const auto result =
        engine.process(modify_order(1, 100, 1));

    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(result));
    EXPECT_TRUE(std::get<ExecutionReport>(result).trades.empty());

    const auto snapshot = engine.snapshot();
    EXPECT_EQ(
        snapshot.bids,
        (std::vector<RestingOrderView>{
            {OrderId{1}, Side::Buy, price(100), quantity(1), sequence(1)}}));
    EXPECT_FALSE(snapshot.next_sequence.has_value());
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(MatchingEngineTest, CancelStillSucceedsAfterSequenceExhaustion) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Sell, 101, 2));

    MatchingEngineQualificationAccess::set_next_sequence(
        engine,
        std::nullopt);

    const auto result =
        engine.process(CancelOrder{OrderId{1}});

    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(result));
    EXPECT_TRUE(std::get<ExecutionReport>(result).trades.empty());

    const auto snapshot = engine.snapshot();
    EXPECT_TRUE(snapshot.bids.empty());
    EXPECT_TRUE(snapshot.asks.empty());
    EXPECT_FALSE(snapshot.next_sequence.has_value());
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    UnknownModifyPrecedesSequenceExhaustion) {
    MatchingEngine engine;

    MatchingEngineQualificationAccess::set_next_sequence(
        engine,
        std::nullopt);

    const EngineSnapshot before = engine.snapshot();

    const auto result =
        engine.process(modify_order(99, 100, 1));

    ASSERT_TRUE(std::holds_alternative<DomainError>(result));
    EXPECT_EQ(
        std::get<DomainError>(result),
        DomainError::UnknownOrderId);
    EXPECT_EQ(engine.snapshot(), before);
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    InvalidModificationPrecedesSequenceExhaustion) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 100, 2));

    MatchingEngineQualificationAccess::set_next_sequence(
        engine,
        std::nullopt);

    const EngineSnapshot before = engine.snapshot();

    const auto result =
        engine.process(modify_order(1, 100, 2));

    ASSERT_TRUE(std::holds_alternative<DomainError>(result));
    EXPECT_EQ(
        std::get<DomainError>(result),
        DomainError::InvalidModification);
    EXPECT_EQ(engine.snapshot(), before);
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    PriorityLosingModifyCanAllocateMaximumOnceAndFullyExecute) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 99, 1));
    accept(engine, new_order(2, Side::Sell, 101, 1));

    MatchingEngineQualificationAccess::set_next_sequence(
        engine,
        SequenceNumber::from_value(
            std::numeric_limits<SequenceNumber::rep>::max()));

    const auto result =
        engine.process(modify_order(1, 101, 1));

    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(result));
    EXPECT_EQ(
        std::get<ExecutionReport>(result).trades,
        (std::vector<Trade>{
            {OrderId{2}, OrderId{1}, price(101), quantity(1)}}));

    const auto snapshot = engine.snapshot();
    EXPECT_TRUE(snapshot.bids.empty());
    EXPECT_TRUE(snapshot.asks.empty());
    EXPECT_FALSE(snapshot.next_sequence.has_value());
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}
TEST(
    MatchingEngineTest,
    IncomingSellSweepsMultipleBidLevelsHighestFirstAtMakerPrices) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 103, 2));
    accept(engine, new_order(2, Side::Buy, 102, 2));
    accept(engine, new_order(3, Side::Buy, 101, 2));

    const auto report =
        accept(engine, new_order(4, Side::Sell, 101, 5));

    EXPECT_EQ(
        report.trades,
        (std::vector<Trade>{
            {OrderId{1}, OrderId{4}, price(103), quantity(2)},
            {OrderId{2}, OrderId{4}, price(102), quantity(2)},
            {OrderId{3}, OrderId{4}, price(101), quantity(1)}}));

    const auto snapshot = engine.snapshot();
    EXPECT_EQ(
        snapshot.bids,
        (std::vector<RestingOrderView>{
            {OrderId{3}, Side::Buy, price(101), quantity(1), sequence(3)}}));
    EXPECT_TRUE(snapshot.asks.empty());
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    PartialMakerFillRetainsPriorityAheadOfLaterSamePriceOrder) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Sell, 100, 5));
    accept(engine, new_order(2, Side::Buy, 100, 2));
    accept(engine, new_order(3, Side::Sell, 100, 2));

    const auto report =
        accept(engine, new_order(4, Side::Buy, 100, 4));

    EXPECT_EQ(
        report.trades,
        (std::vector<Trade>{
            {OrderId{1}, OrderId{4}, price(100), quantity(3)},
            {OrderId{3}, OrderId{4}, price(100), quantity(1)}}));

    const auto snapshot = engine.snapshot();
    EXPECT_EQ(
        snapshot.asks,
        (std::vector<RestingOrderView>{
            {OrderId{3}, Side::Sell, price(100), quantity(1), sequence(3)}}));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    CancelAfterPartialFillRemovesOnlyRemainingMakerState) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Sell, 100, 5));
    accept(engine, new_order(2, Side::Buy, 100, 2));

    const auto cancelled =
        engine.process(CancelOrder{OrderId{1}});

    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(cancelled));
    EXPECT_TRUE(std::get<ExecutionReport>(cancelled).trades.empty());

    const auto snapshot = engine.snapshot();
    EXPECT_TRUE(snapshot.bids.empty());
    EXPECT_TRUE(snapshot.asks.empty());
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 3U);
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(MatchingEngineTest, CancelMiddleOrderPreservesSurvivorFifo) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Sell, 100, 1));
    accept(engine, new_order(2, Side::Sell, 100, 1));
    accept(engine, new_order(3, Side::Sell, 100, 1));

    const auto cancelled =
        engine.process(CancelOrder{OrderId{2}});
    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(cancelled));

    const auto report =
        accept(engine, new_order(4, Side::Buy, 100, 2));

    EXPECT_EQ(
        report.trades,
        (std::vector<Trade>{
            {OrderId{1}, OrderId{4}, price(100), quantity(1)},
            {OrderId{3}, OrderId{4}, price(100), quantity(1)}}));

    EXPECT_TRUE(engine.snapshot().asks.empty());
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    SamePriceAskReductionRetainsPriorityAndConsumesNoSequence) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Sell, 105, 5));
    accept(engine, new_order(2, Side::Sell, 105, 5));

    const auto reduced =
        engine.process(modify_order(1, 105, 3));

    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(reduced));
    EXPECT_TRUE(std::get<ExecutionReport>(reduced).trades.empty());

    auto snapshot = engine.snapshot();
    EXPECT_EQ(
        snapshot.asks,
        (std::vector<RestingOrderView>{
            {OrderId{1}, Side::Sell, price(105), quantity(3), sequence(1)},
            {OrderId{2}, Side::Sell, price(105), quantity(5), sequence(2)}}));
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 3U);

    const auto report =
        accept(engine, new_order(3, Side::Buy, 105, 4));

    EXPECT_EQ(
        report.trades,
        (std::vector<Trade>{
            {OrderId{1}, OrderId{3}, price(105), quantity(3)},
            {OrderId{2}, OrderId{3}, price(105), quantity(1)}}));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    PriceChangePartialExecutionRestsResidualAtNewPriceWithFreshSequence) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 99, 5));
    accept(engine, new_order(2, Side::Sell, 101, 2));

    const auto result =
        engine.process(modify_order(1, 101, 4));

    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(result));
    EXPECT_EQ(
        std::get<ExecutionReport>(result).trades,
        (std::vector<Trade>{
            {OrderId{2}, OrderId{1}, price(101), quantity(2)}}));

    const auto snapshot = engine.snapshot();
    EXPECT_EQ(
        snapshot.bids,
        (std::vector<RestingOrderView>{
            {OrderId{1}, Side::Buy, price(101), quantity(2), sequence(3)}}));
    EXPECT_TRUE(snapshot.asks.empty());
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 4U);
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    FullyExecutedModifyRemovesIdAndAllowsLaterReuse) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 99, 1));
    accept(engine, new_order(2, Side::Sell, 101, 1));

    const auto modified =
        engine.process(modify_order(1, 101, 1));

    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(modified));
    ASSERT_EQ(std::get<ExecutionReport>(modified).trades.size(), 1U);
    EXPECT_TRUE(engine.snapshot().bids.empty());
    EXPECT_TRUE(engine.snapshot().asks.empty());

    const auto reused =
        accept(engine, new_order(1, Side::Sell, 105, 2));

    EXPECT_TRUE(reused.trades.empty());
    const auto snapshot = engine.snapshot();
    ASSERT_EQ(snapshot.asks.size(), 1U);
    EXPECT_EQ(snapshot.asks.front().order_id, OrderId{1});
    EXPECT_EQ(snapshot.asks.front().sequence, sequence(4));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(MatchingEngineTest, ZeroOrderIdSupportsLifecycleAndReuse) {
    MatchingEngine engine;

    accept(engine, new_order(0, Side::Buy, 100, 3));

    const auto reduced =
        engine.process(modify_order(0, 100, 2));
    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(reduced));

    const auto cancelled =
        engine.process(CancelOrder{OrderId{0}});
    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(cancelled));

    const auto reused =
        accept(engine, new_order(0, Side::Sell, 102, 1));
    EXPECT_TRUE(reused.trades.empty());

    const auto snapshot = engine.snapshot();
    ASSERT_EQ(snapshot.asks.size(), 1U);
    EXPECT_EQ(snapshot.asks.front().order_id, OrderId{0});
    EXPECT_EQ(snapshot.asks.front().sequence, sequence(2));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(MatchingEngineTest, MaximumOrderIdSupportsLifecycle) {
    MatchingEngine engine;

    constexpr auto maximum_id =
        std::numeric_limits<OrderId::rep>::max();

    accept(engine, new_order(maximum_id, Side::Sell, 110, 2));

    const auto modified =
        engine.process(modify_order(maximum_id, 109, 3));
    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(modified));

    const auto cancelled =
        engine.process(CancelOrder{OrderId{maximum_id}});
    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(cancelled));

    EXPECT_TRUE(engine.snapshot().asks.empty());
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    MaximumQuantityPartialFillUsesSubtractionWithoutOverflow) {
    MatchingEngine engine;

    constexpr auto maximum_quantity =
        std::numeric_limits<Quantity::rep>::max();

    accept(
        engine,
        new_order(1, Side::Sell, 100, maximum_quantity));

    const auto report =
        accept(engine, new_order(2, Side::Buy, 100, 1));

    EXPECT_EQ(
        report.trades,
        (std::vector<Trade>{
            {OrderId{1}, OrderId{2}, price(100), quantity(1)}}));

    const auto snapshot = engine.snapshot();
    ASSERT_EQ(snapshot.asks.size(), 1U);
    EXPECT_EQ(
        snapshot.asks.front().remaining.units(),
        maximum_quantity - 1);
    EXPECT_EQ(snapshot.asks.front().sequence, sequence(1));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    UnknownCancelAfterSequenceExhaustionRemainsUnknownOrderIdAndAtomic) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 100, 1));

    MatchingEngineQualificationAccess::set_next_sequence(
        engine,
        std::nullopt);

    const EngineSnapshot before = engine.snapshot();

    const auto result =
        engine.process(CancelOrder{OrderId{99}});

    ASSERT_TRUE(std::holds_alternative<DomainError>(result));
    EXPECT_EQ(
        std::get<DomainError>(result),
        DomainError::UnknownOrderId);
    EXPECT_EQ(engine.snapshot(), before);
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(MatchingEngineTest, DeterministicReplayProducesIdenticalObservableState) {
    MatchingEngine left;
    MatchingEngine right;

    const auto compare_new =
        [&](OrderId::rep id,
            Side side,
            Price::rep ticks,
            Quantity::rep units) {
            const auto left_result =
                left.process(new_order(id, side, ticks, units));
            const auto right_result =
                right.process(new_order(id, side, ticks, units));

            EXPECT_EQ(left_result, right_result);
            EXPECT_EQ(left.snapshot(), right.snapshot());
        };

    compare_new(1, Side::Buy, 100, 5);
    compare_new(2, Side::Sell, 103, 4);
    compare_new(3, Side::Sell, 101, 2);
    compare_new(4, Side::Buy, 102, 3);

    const auto left_reduce =
        left.process(modify_order(1, 100, 3));
    const auto right_reduce =
        right.process(modify_order(1, 100, 3));
    EXPECT_EQ(left_reduce, right_reduce);
    EXPECT_EQ(left.snapshot(), right.snapshot());

    const auto left_cancel =
        left.process(CancelOrder{OrderId{2}});
    const auto right_cancel =
        right.process(CancelOrder{OrderId{2}});
    EXPECT_EQ(left_cancel, right_cancel);
    EXPECT_EQ(left.snapshot(), right.snapshot());

    compare_new(5, Side::Sell, 100, 5);

    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(left));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(right));
}

TEST(
    MatchingEngineTest,
    MixedLifecycleMaintainsInvariantsAfterEveryCommandBoundary) {
    MatchingEngine engine;

    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));

    accept(engine, new_order(1, Side::Buy, 100, 5));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));

    accept(engine, new_order(2, Side::Buy, 99, 3));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));

    accept(engine, new_order(3, Side::Sell, 102, 4));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));

    accept(engine, new_order(4, Side::Sell, 100, 2));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));

    const auto reduced =
        engine.process(modify_order(1, 100, 2));
    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(reduced));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));

    const auto repriced =
        engine.process(modify_order(3, 99, 2));
    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(repriced));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));

    const auto cancelled =
        engine.process(CancelOrder{OrderId{2}});
    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(cancelled));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));

    accept(engine, new_order(5, Side::Buy, 105, 5));
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    SellLimitMatchesEqualBidButStopsBeforeLowerBid) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 100, 1));
    accept(engine, new_order(2, Side::Buy, 99, 1));

    const auto report =
        accept(engine, new_order(3, Side::Sell, 100, 2));

    EXPECT_EQ(
        report.trades,
        (std::vector<Trade>{
            {OrderId{1}, OrderId{3}, price(100), quantity(1)}}));

    const auto snapshot = engine.snapshot();
    EXPECT_EQ(
        snapshot.bids,
        (std::vector<RestingOrderView>{
            {OrderId{2}, Side::Buy, price(99), quantity(1), sequence(2)}}));
    EXPECT_EQ(
        snapshot.asks,
        (std::vector<RestingOrderView>{
            {OrderId{3}, Side::Sell, price(100), quantity(1), sequence(3)}}));
    EXPECT_LT(snapshot.bids.front().price, snapshot.asks.front().price);
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}

TEST(
    MatchingEngineTest,
    RemovingAndRecreatingPriceLevelPreservesOrderingAndFreshSequence) {
    MatchingEngine engine;

    accept(engine, new_order(1, Side::Buy, 100, 1));
    const auto cancelled =
        engine.process(CancelOrder{OrderId{1}});
    ASSERT_TRUE(std::holds_alternative<ExecutionReport>(cancelled));

    accept(engine, new_order(2, Side::Buy, 99, 1));
    accept(engine, new_order(3, Side::Buy, 100, 1));

    const auto snapshot = engine.snapshot();
    EXPECT_EQ(
        snapshot.bids,
        (std::vector<RestingOrderView>{
            {OrderId{3}, Side::Buy, price(100), quantity(1), sequence(3)},
            {OrderId{2}, Side::Buy, price(99), quantity(1), sequence(2)}}));
    ASSERT_TRUE(snapshot.next_sequence.has_value());
    EXPECT_EQ(snapshot.next_sequence->value(), 4U);
    EXPECT_TRUE(MatchingEngineQualificationAccess::invariants_hold(engine));
}
}  // namespace
