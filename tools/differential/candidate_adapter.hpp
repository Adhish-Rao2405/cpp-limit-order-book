#pragma once

#include "lob/matching_engine.hpp"

#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <variant>
#include <vector>

namespace lob::qualification {

struct RawNew final {
    OrderId::rep order_id;
    std::uint8_t side_code;
    Price::rep price_ticks;
    Quantity::rep quantity_units;

    friend bool operator==(const RawNew&, const RawNew&) = default;
};

struct RawCancel final {
    OrderId::rep order_id;

    friend bool operator==(const RawCancel&, const RawCancel&) = default;
};

struct RawModify final {
    OrderId::rep order_id;
    Price::rep price_ticks;
    Quantity::rep quantity_units;

    friend bool operator==(const RawModify&, const RawModify&) = default;
};

using RawCommand = std::variant<RawNew, RawCancel, RawModify>;

struct ParsedStream final {
    std::optional<SequenceNumber::rep> next_sequence;
    std::vector<RawCommand> commands;

    friend bool operator==(const ParsedStream&, const ParsedStream&) = default;
};

enum class ParseError {
    EmptyInput,
    Utf8Bom,
    MissingFinalLf,
    CarriageReturn,
    EmbeddedNul,
    NonAsciiByte,
    RecordTooLong,
    BlankRecord,
    InvalidHeader,
    DuplicateHeader,
    UnknownCommandKind,
    WrongFieldCount,
    InvalidNumericGrammar,
    ScalarOutOfRange
};

struct ParseFailure final {
    ParseError error;

    friend bool operator==(const ParseFailure&, const ParseFailure&) = default;
};

using ParseResult = std::variant<ParsedStream, ParseFailure>;

struct CandidateCommandResult final {
    bool accepted;
    std::optional<DomainError> error;

    friend bool operator==(
        const CandidateCommandResult&,
        const CandidateCommandResult&) = default;
};

struct CandidateObservation final {
    CandidateCommandResult command_result;
    std::vector<Trade> trades;
    EngineSnapshot snapshot;

    friend bool operator==(
        const CandidateObservation&,
        const CandidateObservation&) = default;
};

struct CandidateEntry final {
    RawCommand command;
    CandidateObservation observation;

    friend bool operator==(
        const CandidateEntry&,
        const CandidateEntry&) = default;
};

struct CandidateRun final {
    std::vector<CandidateEntry> entries;

    friend bool operator==(
        const CandidateRun&,
        const CandidateRun&) = default;
};

[[nodiscard]]
ParseResult parse_lobq1(std::span<const std::byte> bytes);

[[nodiscard]]
CandidateRun execute_candidate(const ParsedStream& stream);

}  // namespace lob::qualification
