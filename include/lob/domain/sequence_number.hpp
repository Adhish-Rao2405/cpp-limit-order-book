#pragma once

#include <compare>
#include <cstdint>
#include <optional>

namespace lob {

class SequenceNumber final {
public:
    using rep = std::uint64_t;

    [[nodiscard]] static constexpr std::optional<SequenceNumber>
    from_value(rep value) noexcept {
        if (value == 0) {
            return std::nullopt;
        }

        return SequenceNumber{value};
    }

    [[nodiscard]] constexpr rep value() const noexcept {
        return value_;
    }

    friend constexpr bool operator==(SequenceNumber, SequenceNumber) noexcept = default;
    friend constexpr auto operator<=>(SequenceNumber, SequenceNumber) noexcept = default;

private:
    explicit constexpr SequenceNumber(rep value) noexcept : value_{value} {}

    rep value_;
};

}  // namespace lob
