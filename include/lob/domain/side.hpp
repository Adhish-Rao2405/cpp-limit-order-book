#pragma once

#include <cstdint>

namespace lob {

enum class Side : std::uint8_t {
    Buy = 0,
    Sell = 1
};

[[nodiscard]] constexpr bool is_valid(Side side) noexcept {
    return side == Side::Buy || side == Side::Sell;
}

}  // namespace lob
