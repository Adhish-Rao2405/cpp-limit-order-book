#pragma once

#include "candidate_adapter.hpp"

#include <cstddef>
#include <variant>
#include <vector>

namespace lob::qualification {

enum class CandidateCanonicalError {
  InvalidCommandResult,
  InvalidDomainError,
  RejectedCommandHasTrades,
  InvalidTrade,
  InvalidRestingOrder,
  InvalidRestingSide,
  NonCanonicalBidOrder,
  NonCanonicalAskOrder,
  InvalidAllocator
};

struct CandidateCanonicalFailure final {
  CandidateCanonicalError error;
  std::size_t command_index;

  friend bool operator==(
      const CandidateCanonicalFailure&,
      const CandidateCanonicalFailure&) = default;
};

using CandidateCanonicalResult =
    std::variant<std::vector<std::byte>, CandidateCanonicalFailure>;

[[nodiscard]]
CandidateCanonicalResult serialize_candidate_canonical_trace(
    const CandidateRun& run);

}  // namespace lob::qualification
