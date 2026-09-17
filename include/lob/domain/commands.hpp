#pragma once

#include "lob/domain/error.hpp"
#include "lob/domain/order_id.hpp"
#include "lob/domain/price.hpp"
#include "lob/domain/quantity.hpp"
#include "lob/domain/side.hpp"

namespace lob {

class NewOrder final {
public:
    [[nodiscard]] static constexpr DomainResult<NewOrder> create(
        OrderId order_id,
        Side side,
        Price::rep price_ticks,
        Quantity::rep quantity_units) noexcept {
        const auto price = Price::from_ticks(price_ticks);
        if (!price.has_value()) {
            return DomainError::InvalidPrice;
        }

        const auto quantity = Quantity::from_units(quantity_units);
        if (!quantity.has_value()) {
            return DomainError::InvalidQuantity;
        }

        if (!is_valid(side)) {
            return DomainError::InvalidSide;
        }

        return NewOrder{order_id, side, *price, *quantity};
    }

    [[nodiscard]] constexpr OrderId order_id() const noexcept {
        return order_id_;
    }

    [[nodiscard]] constexpr Side side() const noexcept {
        return side_;
    }

    [[nodiscard]] constexpr Price price() const noexcept {
        return price_;
    }

    [[nodiscard]] constexpr Quantity quantity() const noexcept {
        return quantity_;
    }

private:
    constexpr NewOrder(
        OrderId order_id,
        Side side,
        Price price,
        Quantity quantity) noexcept
        : order_id_{order_id},
          side_{side},
          price_{price},
          quantity_{quantity} {}

    OrderId order_id_;
    Side side_;
    Price price_;
    Quantity quantity_;
};

class CancelOrder final {
public:
    explicit constexpr CancelOrder(OrderId order_id) noexcept
        : order_id_{order_id} {}

    [[nodiscard]] constexpr OrderId order_id() const noexcept {
        return order_id_;
    }

private:
    OrderId order_id_;
};

class ModifyOrder final {
public:
    [[nodiscard]] static constexpr DomainResult<ModifyOrder> create(
        OrderId order_id,
        Price::rep new_price_ticks,
        Quantity::rep new_quantity_units) noexcept {
        const auto price = Price::from_ticks(new_price_ticks);
        if (!price.has_value()) {
            return DomainError::InvalidPrice;
        }

        const auto quantity = Quantity::from_units(new_quantity_units);
        if (!quantity.has_value()) {
            return DomainError::InvalidQuantity;
        }

        return ModifyOrder{order_id, *price, *quantity};
    }

    [[nodiscard]] constexpr OrderId order_id() const noexcept {
        return order_id_;
    }

    [[nodiscard]] constexpr Price price() const noexcept {
        return price_;
    }

    [[nodiscard]] constexpr Quantity quantity() const noexcept {
        return quantity_;
    }

private:
    constexpr ModifyOrder(
        OrderId order_id,
        Price price,
        Quantity quantity) noexcept
        : order_id_{order_id},
          price_{price},
          quantity_{quantity} {}

    OrderId order_id_;
    Price price_;
    Quantity quantity_;
};

}  // namespace lob
