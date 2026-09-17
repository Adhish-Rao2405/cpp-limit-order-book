#pragma once

#include <variant>

namespace lob {

enum class DomainError {
    InvalidPrice,
    InvalidQuantity,
    InvalidSide,
    DuplicateOrderId,
    UnknownOrderId,
    SequenceExhausted,
    InvalidModification
};

template <typename T>
using DomainResult = std::variant<T, DomainError>;

}  // namespace lob
