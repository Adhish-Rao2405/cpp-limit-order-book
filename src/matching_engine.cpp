#include "lob/matching_engine.hpp"

#include <algorithm>
#include <iterator>
#include <limits>
#include <stdexcept>
#include <type_traits>
#include <unordered_set>
#include <utility>

namespace lob {
namespace {

[[nodiscard]] Quantity positive_quantity(Quantity::rep units) {
    return Quantity::from_units(units).value();
}

}  // namespace

MatchingEngine::MatchingEngine() = default;

std::optional<SequenceNumber> MatchingEngine::allocate_sequence() {
    if (!next_sequence_.has_value()) {
        return std::nullopt;
    }

    const SequenceNumber allocated = *next_sequence_;
    const auto value = allocated.value();

    if (value == std::numeric_limits<SequenceNumber::rep>::max()) {
        next_sequence_.reset();
    } else {
        next_sequence_ = SequenceNumber::from_value(value + 1);
    }

    return allocated;
}

DomainResult<ExecutionReport>
MatchingEngine::process(const NewOrder& command) {
    if (active_.contains(command.order_id())) {
        return DomainError::DuplicateOrderId;
    }

    const auto sequence = allocate_sequence();
    if (!sequence.has_value()) {
        return DomainError::SequenceExhausted;
    }

    return process_incoming(
        command.order_id(),
        command.side(),
        command.price(),
        command.quantity(),
        *sequence);
}

DomainResult<ExecutionReport>
MatchingEngine::process(const CancelOrder& command) {
    const auto active = active_.find(command.order_id());
    if (active == active_.end()) {
        return DomainError::UnknownOrderId;
    }

    const Locator locator = active->second;

    if (const auto* bid = std::get_if<BidLocator>(&locator)) {
        if (bid->order->order_id != command.order_id()) {
            throw std::logic_error(
                "bid locator points to the wrong active order");
        }

        auto level = bid->level;
        auto order = bid->order;

        active_.erase(active);
        level->second.erase(order);

        if (level->second.empty()) {
            bids_.erase(level);
        }
    } else {
        const auto& ask = std::get<AskLocator>(locator);

        if (ask.order->order_id != command.order_id()) {
            throw std::logic_error(
                "ask locator points to the wrong active order");
        }

        auto level = ask.level;
        auto order = ask.order;

        active_.erase(active);
        level->second.erase(order);

        if (level->second.empty()) {
            asks_.erase(level);
        }
    }

    return ExecutionReport{};
}

DomainResult<ExecutionReport>
MatchingEngine::process(const ModifyOrder& command) {
    const auto active = active_.find(command.order_id());
    if (active == active_.end()) {
        return DomainError::UnknownOrderId;
    }

    const Locator locator = active->second;

    return std::visit(
        [&](const auto& location) -> DomainResult<ExecutionReport> {
            using Located =
                std::remove_cvref_t<decltype(location)>;

            if (location.order->order_id != command.order_id()) {
                throw std::logic_error(
                    "modify locator points to the wrong active order");
            }

            const Price current_price = location.level->first;
            const Quantity current_remaining =
                location.order->remaining;

            if (command.price() == current_price) {
                if (command.quantity() == current_remaining) {
                    return DomainError::InvalidModification;
                }

                if (command.quantity() < current_remaining) {
                    location.order->remaining = command.quantity();
                    return ExecutionReport{};
                }
            }

            const auto fresh_sequence = allocate_sequence();
            if (!fresh_sequence.has_value()) {
                return DomainError::SequenceExhausted;
            }

            constexpr bool is_bid =
                std::is_same_v<Located, BidLocator>;
            const Side side =
                is_bid ? Side::Buy : Side::Sell;

            auto level = location.level;
            auto order = location.order;

            active_.erase(active);
            level->second.erase(order);

            if (level->second.empty()) {
                if constexpr (is_bid) {
                    bids_.erase(level);
                } else {
                    asks_.erase(level);
                }
            }

            return process_incoming(
                command.order_id(),
                side,
                command.price(),
                command.quantity(),
                *fresh_sequence);
        },
        locator);
}

ExecutionReport MatchingEngine::process_incoming(
    OrderId order_id,
    Side side,
    Price limit_price,
    Quantity quantity,
    SequenceNumber sequence) {
    ExecutionReport report;
    auto remaining_units = quantity.units();

    if (side == Side::Buy) {
        while (remaining_units > 0 && !asks_.empty()) {
            auto level = asks_.begin();
            if (level->first > limit_price) {
                break;
            }

            auto& queue = level->second;

            while (remaining_units > 0 && !queue.empty()) {
                auto maker = queue.begin();
                const OrderId maker_id = maker->order_id;
                const auto maker_units = maker->remaining.units();
                const auto trade_units = std::min(remaining_units, maker_units);
                const Quantity trade_quantity = positive_quantity(trade_units);

                report.trades.push_back(
                    Trade{maker_id, order_id, level->first, trade_quantity});

                remaining_units -= trade_units;

                if (trade_units == maker_units) {
                    if (active_.erase(maker_id) != 1) {
                        throw std::logic_error(
                            "active locator missing for fully filled ask");
                    }

                    queue.erase(maker);
                } else {
                    maker->remaining =
                        positive_quantity(maker_units - trade_units);
                }
            }

            if (queue.empty()) {
                asks_.erase(level);
            }
        }
    } else if (side == Side::Sell) {
        while (remaining_units > 0 && !bids_.empty()) {
            auto level = std::prev(bids_.end());
            if (level->first < limit_price) {
                break;
            }

            auto& queue = level->second;

            while (remaining_units > 0 && !queue.empty()) {
                auto maker = queue.begin();
                const OrderId maker_id = maker->order_id;
                const auto maker_units = maker->remaining.units();
                const auto trade_units = std::min(remaining_units, maker_units);
                const Quantity trade_quantity = positive_quantity(trade_units);

                report.trades.push_back(
                    Trade{maker_id, order_id, level->first, trade_quantity});

                remaining_units -= trade_units;

                if (trade_units == maker_units) {
                    if (active_.erase(maker_id) != 1) {
                        throw std::logic_error(
                            "active locator missing for fully filled bid");
                    }

                    queue.erase(maker);
                } else {
                    maker->remaining =
                        positive_quantity(maker_units - trade_units);
                }
            }

            if (queue.empty()) {
                bids_.erase(level);
            }
        }
    } else {
        throw std::logic_error("invalid side reached matching core");
    }

    if (remaining_units == 0) {
        return report;
    }

    RestingOrder resting{
        order_id,
        positive_quantity(remaining_units),
        sequence};

    if (side == Side::Buy) {
        auto [level, inserted_level] =
            bids_.try_emplace(limit_price, OrderQueue{});
        static_cast<void>(inserted_level);

        level->second.push_back(std::move(resting));
        auto order = std::prev(level->second.end());

        const auto [active, inserted] =
            active_.emplace(order_id, BidLocator{level, order});
        static_cast<void>(active);

        if (!inserted) {
            throw std::logic_error(
                "duplicate active ID while resting bid residual");
        }
    } else {
        auto [level, inserted_level] =
            asks_.try_emplace(limit_price, OrderQueue{});
        static_cast<void>(inserted_level);

        level->second.push_back(std::move(resting));
        auto order = std::prev(level->second.end());

        const auto [active, inserted] =
            active_.emplace(order_id, AskLocator{level, order});
        static_cast<void>(active);

        if (!inserted) {
            throw std::logic_error(
                "duplicate active ID while resting ask residual");
        }
    }

    return report;
}

bool MatchingEngine::invariants_hold() const {
    std::size_t canonical_count = 0;
    std::unordered_set<OrderId::rep> order_ids;
    std::unordered_set<SequenceNumber::rep> sequences;

    const auto check_book =
        [&](const SideBook& book, Side expected_side) -> bool {
        for (auto level = book.cbegin(); level != book.cend(); ++level) {
            if (level->second.empty()) {
                return false;
            }

            for (auto order = level->second.cbegin();
                 order != level->second.cend();
                 ++order) {
                ++canonical_count;

                if (order->remaining.units() == 0) {
                    return false;
                }

                if (!order_ids.insert(order->order_id.value()).second) {
                    return false;
                }

                if (!sequences.insert(order->sequence.value()).second) {
                    return false;
                }

                if (next_sequence_.has_value() &&
                    !(order->sequence < *next_sequence_)) {
                    return false;
                }

                const auto active = active_.find(order->order_id);
                if (active == active_.end()) {
                    return false;
                }

                if (expected_side == Side::Buy) {
                    const auto* locator =
                        std::get_if<BidLocator>(&active->second);
                    if (locator == nullptr ||
                        locator->level != level ||
                        locator->order != order) {
                        return false;
                    }
                } else {
                    const auto* locator =
                        std::get_if<AskLocator>(&active->second);
                    if (locator == nullptr ||
                        locator->level != level ||
                        locator->order != order) {
                        return false;
                    }
                }
            }
        }

        return true;
    };

    if (!check_book(bids_, Side::Buy) ||
        !check_book(asks_, Side::Sell)) {
        return false;
    }

    if (canonical_count != active_.size()) {
        return false;
    }

    if (!bids_.empty() && !asks_.empty()) {
        const Price best_bid = std::prev(bids_.end())->first;
        const Price best_ask = asks_.begin()->first;

        if (!(best_bid < best_ask)) {
            return false;
        }
    }

    return true;
}

EngineSnapshot MatchingEngine::snapshot() const {
    EngineSnapshot result;

    for (auto level = bids_.crbegin(); level != bids_.crend(); ++level) {
        for (const auto& order : level->second) {
            result.bids.push_back(
                RestingOrderView{
                    order.order_id,
                    Side::Buy,
                    level->first,
                    order.remaining,
                    order.sequence});
        }
    }

    for (const auto& [price, queue] : asks_) {
        for (const auto& order : queue) {
            result.asks.push_back(
                RestingOrderView{
                    order.order_id,
                    Side::Sell,
                    price,
                    order.remaining,
                    order.sequence});
        }
    }

    result.next_sequence = next_sequence_;
    return result;
}

}  // namespace lob
