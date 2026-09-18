#pragma once

#include "lob/domain/commands.hpp"
#include "lob/domain/error.hpp"
#include "lob/domain/order_id.hpp"
#include "lob/domain/price.hpp"
#include "lob/domain/quantity.hpp"
#include "lob/domain/sequence_number.hpp"
#include "lob/domain/side.hpp"

#include <cstddef>
#include <functional>
#include <list>
#include <map>
#include <optional>
#include <unordered_map>
#include <variant>
#include <vector>

#if defined(LOB_ENABLE_MATCHING_ENGINE_QUALIFICATION)
namespace lob::detail {
class MatchingEngineQualificationAccess;
}
#endif

namespace lob {

struct Trade final {
    OrderId maker;
    OrderId taker;
    Price price;
    Quantity quantity;

    friend bool operator==(const Trade&, const Trade&) = default;
};

struct ExecutionReport final {
    std::vector<Trade> trades;

    friend bool operator==(const ExecutionReport&, const ExecutionReport&) = default;
};

struct RestingOrderView final {
    OrderId order_id;
    Side side;
    Price price;
    Quantity remaining;
    SequenceNumber sequence;

    friend bool operator==(const RestingOrderView&, const RestingOrderView&) = default;
};

struct EngineSnapshot final {
    std::vector<RestingOrderView> bids;
    std::vector<RestingOrderView> asks;
    std::optional<SequenceNumber> next_sequence;

    friend bool operator==(const EngineSnapshot&, const EngineSnapshot&) = default;
};

class MatchingEngine final {
public:
    MatchingEngine();

    MatchingEngine(const MatchingEngine&) = delete;
    MatchingEngine& operator=(const MatchingEngine&) = delete;
    MatchingEngine(MatchingEngine&&) = delete;
    MatchingEngine& operator=(MatchingEngine&&) = delete;

    [[nodiscard]] DomainResult<ExecutionReport>
    process(const NewOrder& command);

    [[nodiscard]] DomainResult<ExecutionReport>
    process(const CancelOrder& command);

    [[nodiscard]] DomainResult<ExecutionReport>
    process(const ModifyOrder& command);

    [[nodiscard]] EngineSnapshot snapshot() const;

private:
#if defined(LOB_ENABLE_MATCHING_ENGINE_QUALIFICATION)
    friend class detail::MatchingEngineQualificationAccess;
#endif

    struct RestingOrder final {
        OrderId order_id;
        Quantity remaining;
        SequenceNumber sequence;
    };

    using OrderQueue = std::list<RestingOrder>;
    using SideBook = std::map<Price, OrderQueue>;

    struct BidLocator final {
        SideBook::iterator level;
        OrderQueue::iterator order;
    };

    struct AskLocator final {
        SideBook::iterator level;
        OrderQueue::iterator order;
    };

    using Locator = std::variant<BidLocator, AskLocator>;

    struct OrderIdHash final {
        [[nodiscard]] std::size_t operator()(OrderId order_id) const noexcept {
            return std::hash<OrderId::rep>{}(order_id.value());
        }
    };

    [[nodiscard]] bool invariants_hold() const;

    [[nodiscard]] std::optional<SequenceNumber> allocate_sequence();

    [[nodiscard]] ExecutionReport process_incoming(
        OrderId order_id,
        Side side,
        Price limit_price,
        Quantity quantity,
        SequenceNumber sequence);

    SideBook bids_;
    SideBook asks_;
    std::unordered_map<OrderId, Locator, OrderIdHash> active_;
    std::optional<SequenceNumber> next_sequence_{SequenceNumber::from_value(1)};
};

}  // namespace lob
