#pragma once

#include <cstdint>

namespace lob {

class OrderId final {
public:
    using rep = std::uint64_t;

    explicit constexpr OrderId(rep value) noexcept : value_{value} {}

    [[nodiscard]] constexpr rep value() const noexcept {
        return value_;
    }

    friend constexpr bool operator==(OrderId, OrderId) noexcept = default;

private:
    rep value_;
};

}  // namespace lob
