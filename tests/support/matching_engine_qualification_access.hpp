#pragma once

#include "lob/matching_engine.hpp"

#include <optional>

#if !defined(LOB_ENABLE_MATCHING_ENGINE_QUALIFICATION)
#error "Matching-engine qualification access must be enabled"
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
