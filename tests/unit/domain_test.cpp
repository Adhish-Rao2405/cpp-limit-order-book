#include "lob/domain/commands.hpp"
#include "lob/domain/error.hpp"
#include "lob/domain/order_id.hpp"
#include "lob/domain/price.hpp"
#include "lob/domain/quantity.hpp"
#include "lob/domain/sequence_number.hpp"
#include "lob/domain/side.hpp"

#include <gtest/gtest.h>

#include <cstdint>
#include <limits>
#include <type_traits>
#include <variant>

namespace {

using lob::CancelOrder;
using lob::DomainError;
using lob::DomainResult;
using lob::ModifyOrder;
using lob::NewOrder;
using lob::OrderId;
using lob::Price;
using lob::Quantity;
using lob::SequenceNumber;
using lob::Side;

static_assert(std::is_same_v<Price::rep, std::int64_t>);
static_assert(std::is_same_v<Quantity::rep, std::uint64_t>);
static_assert(std::is_same_v<OrderId::rep, std::uint64_t>);
static_assert(std::is_same_v<SequenceNumber::rep, std::uint64_t>);
static_assert(std::is_same_v<std::underlying_type_t<Side>, std::uint8_t>);

static_assert(!std::is_same_v<Price, Quantity>);
static_assert(!std::is_same_v<Price, OrderId>);
static_assert(!std::is_same_v<Price, SequenceNumber>);
static_assert(!std::is_same_v<Quantity, OrderId>);
static_assert(!std::is_same_v<Quantity, SequenceNumber>);
static_assert(!std::is_same_v<OrderId, SequenceNumber>);

static_assert(!std::is_default_constructible_v<Price>);
static_assert(!std::is_default_constructible_v<Quantity>);
static_assert(!std::is_default_constructible_v<OrderId>);
static_assert(!std::is_default_constructible_v<SequenceNumber>);
static_assert(!std::is_default_constructible_v<NewOrder>);
static_assert(!std::is_default_constructible_v<CancelOrder>);
static_assert(!std::is_default_constructible_v<ModifyOrder>);

static_assert(!std::is_aggregate_v<Price>);
static_assert(!std::is_aggregate_v<Quantity>);
static_assert(!std::is_aggregate_v<OrderId>);
static_assert(!std::is_aggregate_v<SequenceNumber>);
static_assert(!std::is_aggregate_v<NewOrder>);
static_assert(!std::is_aggregate_v<CancelOrder>);
static_assert(!std::is_aggregate_v<ModifyOrder>);

static_assert(!std::is_convertible_v<Price::rep, Price>);
static_assert(!std::is_convertible_v<Quantity::rep, Quantity>);
static_assert(!std::is_convertible_v<OrderId::rep, OrderId>);
static_assert(!std::is_convertible_v<SequenceNumber::rep, SequenceNumber>);

static_assert(!std::is_convertible_v<Price, Price::rep>);
static_assert(!std::is_convertible_v<Quantity, Quantity::rep>);
static_assert(!std::is_convertible_v<OrderId, OrderId::rep>);
static_assert(!std::is_convertible_v<SequenceNumber, SequenceNumber::rep>);

static_assert(std::is_same_v<
              DomainResult<NewOrder>,
              std::variant<NewOrder, DomainError>>);

static_assert(noexcept(Price::from_ticks(1)));
static_assert(noexcept(Quantity::from_units(1)));
static_assert(noexcept(SequenceNumber::from_value(1)));
static_assert(noexcept(NewOrder::create(OrderId{1}, Side::Buy, 1, 1)));
static_assert(noexcept(ModifyOrder::create(OrderId{1}, 1, 1)));
static_assert(std::is_nothrow_constructible_v<OrderId, OrderId::rep>);
static_assert(std::is_nothrow_constructible_v<CancelOrder, OrderId>);

TEST(PriceTest, AcceptsPositiveTicks) {
    const auto price = Price::from_ticks(125);

    ASSERT_TRUE(price.has_value());
    EXPECT_EQ(price->ticks(), 125);
}

TEST(PriceTest, RejectsZeroAndNegativeTicks) {
    EXPECT_FALSE(Price::from_ticks(0).has_value());
    EXPECT_FALSE(Price::from_ticks(-1).has_value());
    EXPECT_FALSE(
        Price::from_ticks(std::numeric_limits<Price::rep>::min()).has_value());
}

TEST(PriceTest, OrdersByTickValue) {
    const auto lower = Price::from_ticks(100);
    const auto higher = Price::from_ticks(101);

    ASSERT_TRUE(lower.has_value());
    ASSERT_TRUE(higher.has_value());

    EXPECT_LT(*lower, *higher);
    EXPECT_NE(*lower, *higher);
}

TEST(QuantityTest, AcceptsPositiveAndMaximumValues) {
    const auto one = Quantity::from_units(1);
    const auto maximum =
        Quantity::from_units(std::numeric_limits<Quantity::rep>::max());

    ASSERT_TRUE(one.has_value());
    ASSERT_TRUE(maximum.has_value());

    EXPECT_EQ(one->units(), 1U);
    EXPECT_EQ(
        maximum->units(),
        std::numeric_limits<Quantity::rep>::max());
}

TEST(QuantityTest, RejectsZero) {
    EXPECT_FALSE(Quantity::from_units(0).has_value());
}

TEST(QuantityTest, OrdersByUnitValue) {
    const auto lower = Quantity::from_units(10);
    const auto higher = Quantity::from_units(20);

    ASSERT_TRUE(lower.has_value());
    ASSERT_TRUE(higher.has_value());

    EXPECT_LT(*lower, *higher);
}

TEST(OrderIdTest, AcceptsZeroAndMaximumRepresentationalValues) {
    constexpr OrderId zero{0};
    constexpr OrderId maximum{std::numeric_limits<OrderId::rep>::max()};

    EXPECT_EQ(zero.value(), 0U);
    EXPECT_EQ(
        maximum.value(),
        std::numeric_limits<OrderId::rep>::max());
}

TEST(OrderIdTest, EqualityIsValueBased) {
    EXPECT_EQ(OrderId{42}, OrderId{42});
    EXPECT_NE(OrderId{42}, OrderId{43});
}

TEST(SequenceNumberTest, RejectsZero) {
    EXPECT_FALSE(SequenceNumber::from_value(0).has_value());
}

TEST(SequenceNumberTest, AcceptsFirstAndMaximumValues) {
    const auto first = SequenceNumber::from_value(1);
    const auto maximum = SequenceNumber::from_value(
        std::numeric_limits<SequenceNumber::rep>::max());

    ASSERT_TRUE(first.has_value());
    ASSERT_TRUE(maximum.has_value());

    EXPECT_EQ(first->value(), 1U);
    EXPECT_EQ(
        maximum->value(),
        std::numeric_limits<SequenceNumber::rep>::max());
}

TEST(SequenceNumberTest, OrdersBySequenceValue) {
    const auto earlier = SequenceNumber::from_value(7);
    const auto later = SequenceNumber::from_value(8);

    ASSERT_TRUE(earlier.has_value());
    ASSERT_TRUE(later.has_value());

    EXPECT_LT(*earlier, *later);
}

TEST(SideTest, RecognisesOnlyNamedLogicalValues) {
    EXPECT_TRUE(lob::is_valid(Side::Buy));
    EXPECT_TRUE(lob::is_valid(Side::Sell));
    EXPECT_FALSE(lob::is_valid(static_cast<Side>(2)));
    EXPECT_FALSE(lob::is_valid(static_cast<Side>(255)));
}

TEST(NewOrderTest, CreatesValidatedCommandAndExposesTypedValues) {
    const auto result =
        NewOrder::create(OrderId{7}, Side::Buy, 100, 5);

    ASSERT_TRUE(std::holds_alternative<NewOrder>(result));

    const auto& order = std::get<NewOrder>(result);

    EXPECT_EQ(order.order_id(), OrderId{7});
    EXPECT_EQ(order.side(), Side::Buy);
    EXPECT_EQ(order.price().ticks(), 100);
    EXPECT_EQ(order.quantity().units(), 5U);
}

TEST(NewOrderTest, RejectsInvalidPriceBeforeQuantityAndSide) {
    const auto result =
        NewOrder::create(OrderId{7}, static_cast<Side>(2), 0, 0);

    ASSERT_TRUE(std::holds_alternative<DomainError>(result));
    EXPECT_EQ(
        std::get<DomainError>(result),
        DomainError::InvalidPrice);
}

TEST(NewOrderTest, RejectsInvalidQuantityBeforeSide) {
    const auto result =
        NewOrder::create(OrderId{7}, static_cast<Side>(2), 100, 0);

    ASSERT_TRUE(std::holds_alternative<DomainError>(result));
    EXPECT_EQ(
        std::get<DomainError>(result),
        DomainError::InvalidQuantity);
}

TEST(NewOrderTest, RejectsInvalidSideAfterValidPriceAndQuantity) {
    const auto result =
        NewOrder::create(OrderId{7}, static_cast<Side>(2), 100, 5);

    ASSERT_TRUE(std::holds_alternative<DomainError>(result));
    EXPECT_EQ(
        std::get<DomainError>(result),
        DomainError::InvalidSide);
}

TEST(NewOrderTest, AcceptsZeroOrderIdBecauseIdValidityIsStateIndependent) {
    const auto result =
        NewOrder::create(OrderId{0}, Side::Sell, 100, 5);

    ASSERT_TRUE(std::holds_alternative<NewOrder>(result));
    EXPECT_EQ(std::get<NewOrder>(result).order_id(), OrderId{0});
}

TEST(CancelOrderTest, StoresAnyRepresentationallyValidOrderId) {
    constexpr CancelOrder zero_id_cancel{OrderId{0}};
    constexpr CancelOrder maximum_id_cancel{
        OrderId{std::numeric_limits<OrderId::rep>::max()}};

    EXPECT_EQ(zero_id_cancel.order_id(), OrderId{0});
    EXPECT_EQ(
        maximum_id_cancel.order_id(),
        OrderId{std::numeric_limits<OrderId::rep>::max()});
}

TEST(ModifyOrderTest, CreatesValidatedReplacementValues) {
    const auto result =
        ModifyOrder::create(OrderId{9}, 101, 3);

    ASSERT_TRUE(std::holds_alternative<ModifyOrder>(result));

    const auto& modify = std::get<ModifyOrder>(result);

    EXPECT_EQ(modify.order_id(), OrderId{9});
    EXPECT_EQ(modify.price().ticks(), 101);
    EXPECT_EQ(modify.quantity().units(), 3U);
}

TEST(ModifyOrderTest, RejectsInvalidPriceBeforeInvalidQuantity) {
    const auto result =
        ModifyOrder::create(OrderId{9}, 0, 0);

    ASSERT_TRUE(std::holds_alternative<DomainError>(result));
    EXPECT_EQ(
        std::get<DomainError>(result),
        DomainError::InvalidPrice);
}

TEST(ModifyOrderTest, RejectsInvalidQuantityAfterValidPrice) {
    const auto result =
        ModifyOrder::create(OrderId{9}, 101, 0);

    ASSERT_TRUE(std::holds_alternative<DomainError>(result));
    EXPECT_EQ(
        std::get<DomainError>(result),
        DomainError::InvalidQuantity);
}

TEST(DomainResultTest, UsesTypedVariantAlternatives) {
    const DomainResult<int> accepted{42};
    const DomainResult<int> rejected{DomainError::InvalidModification};

    ASSERT_TRUE(std::holds_alternative<int>(accepted));
    EXPECT_EQ(std::get<int>(accepted), 42);

    ASSERT_TRUE(std::holds_alternative<DomainError>(rejected));
    EXPECT_EQ(
        std::get<DomainError>(rejected),
        DomainError::InvalidModification);
}

}  // namespace
