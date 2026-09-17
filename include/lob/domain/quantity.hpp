#pragma once

#include <compare>
#include <cstdint>
#include <optional>

namespace lob {

class Quantity final {
public:
    using rep = std::uint64_t;

    [[nodiscard]] static constexpr std::optional<Quantity>
    from_units(rep units) noexcept {
        if (units == 0) {
            return std::nullopt;
        }

        return Quantity{units};
    }

    [[nodiscard]] constexpr rep units() const noexcept {
        return units_;
    }

    friend constexpr bool operator==(Quantity, Quantity) noexcept = default;
    friend constexpr auto operator<=>(Quantity, Quantity) noexcept = default;

private:
    explicit constexpr Quantity(rep units) noexcept : units_{units} {}

    rep units_;
};

}  // namespace lob
