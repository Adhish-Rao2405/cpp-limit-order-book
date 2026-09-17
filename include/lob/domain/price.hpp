#pragma once

#include <compare>
#include <cstdint>
#include <optional>

namespace lob {

class Price final {
public:
    using rep = std::int64_t;

    [[nodiscard]] static constexpr std::optional<Price>
    from_ticks(rep ticks) noexcept {
        if (ticks <= 0) {
            return std::nullopt;
        }

        return Price{ticks};
    }

    [[nodiscard]] constexpr rep ticks() const noexcept {
        return ticks_;
    }

    friend constexpr bool operator==(Price, Price) noexcept = default;
    friend constexpr auto operator<=>(Price, Price) noexcept = default;

private:
    explicit constexpr Price(rep ticks) noexcept : ticks_{ticks} {}

    rep ticks_;
};

}  // namespace lob
