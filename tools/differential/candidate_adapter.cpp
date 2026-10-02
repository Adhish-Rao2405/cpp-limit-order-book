#include "candidate_adapter.hpp"

#include "tests/support/matching_engine_qualification_access.hpp"

#include <charconv>
#include <limits>
#include <stdexcept>
#include <string_view>
#include <system_error>
#include <utility>

namespace lob::qualification {
namespace {

constexpr std::size_t kMaximumRecordContent = 128;

[[nodiscard]] ParseResult fail(ParseError error) {
    return ParseFailure{error};
}

[[nodiscard]] bool
is_ascii_edge_whitespace(char value) noexcept {
    return value == ' ' ||
           value == '\t' ||
           value == '\v' ||
           value == '\f';
}

[[nodiscard]] bool
has_canonical_unsigned_grammar(
    std::string_view text) noexcept {
    if (text == "0") {
        return true;
    }

    if (text.empty() ||
        text.front() < '1' ||
        text.front() > '9') {
        return false;
    }

    for (const char value : text.substr(1)) {
        if (value < '0' || value > '9') {
            return false;
        }
    }

    return true;
}

[[nodiscard]] bool
has_canonical_signed_grammar(
    std::string_view text) noexcept {
    if (has_canonical_unsigned_grammar(text)) {
        return true;
    }

    if (text.size() < 2 || text.front() != '-') {
        return false;
    }

    const std::string_view magnitude = text.substr(1);

    return magnitude != "0" &&
           has_canonical_unsigned_grammar(magnitude);
}

template <typename Integer>
[[nodiscard]]
std::variant<Integer, ParseError> parse_integer(
    std::string_view text,
    bool signed_grammar,
    Integer minimum,
    Integer maximum) {
    const bool grammar_ok =
        signed_grammar
            ? has_canonical_signed_grammar(text)
            : has_canonical_unsigned_grammar(text);

    if (!grammar_ok) {
        return ParseError::InvalidNumericGrammar;
    }

    Integer value{};

    const char* const first = text.data();
    const char* const last = first + text.size();

    const auto parsed =
        std::from_chars(first, last, value, 10);

    if (parsed.ec == std::errc::result_out_of_range) {
        return ParseError::ScalarOutOfRange;
    }

    if (parsed.ec != std::errc{} ||
        parsed.ptr != last) {
        return ParseError::InvalidNumericGrammar;
    }

    if (value < minimum || value > maximum) {
        return ParseError::ScalarOutOfRange;
    }

    return value;
}

[[nodiscard]]
std::vector<std::string_view>
split_fields(std::string_view record) {
    std::vector<std::string_view> fields;

    std::size_t start = 0;

    while (true) {
        const std::size_t separator =
            record.find('|', start);

        if (separator == std::string_view::npos) {
            fields.push_back(record.substr(start));
            break;
        }

        fields.push_back(
            record.substr(
                start,
                separator - start));

        start = separator + 1;
    }

    return fields;
}

[[nodiscard]]
std::variant<SequenceNumber::rep, ParseError>
parse_allocator(std::string_view text) {
    return parse_integer<SequenceNumber::rep>(
        text,
        false,
        1,
        std::numeric_limits<
            SequenceNumber::rep>::max());
}

[[nodiscard]]
std::variant<OrderId::rep, ParseError>
parse_order_id(std::string_view text) {
    return parse_integer<OrderId::rep>(
        text,
        false,
        0,
        std::numeric_limits<
            OrderId::rep>::max());
}

[[nodiscard]]
std::variant<std::uint8_t, ParseError>
parse_side_code(std::string_view text) {
    const auto parsed =
        parse_integer<std::uint64_t>(
            text,
            false,
            0,
            std::numeric_limits<
                std::uint64_t>::max());

    if (std::holds_alternative<ParseError>(
            parsed)) {
        return std::get<ParseError>(parsed);
    }

    const auto value =
        std::get<std::uint64_t>(parsed);

    if (value >
        std::numeric_limits<
            std::uint8_t>::max()) {
        return ParseError::ScalarOutOfRange;
    }

    return static_cast<std::uint8_t>(value);
}

[[nodiscard]]
std::variant<Price::rep, ParseError>
parse_price_ticks(std::string_view text) {
    return parse_integer<Price::rep>(
        text,
        true,
        std::numeric_limits<Price::rep>::min(),
        std::numeric_limits<Price::rep>::max());
}

[[nodiscard]]
std::variant<Quantity::rep, ParseError>
parse_quantity_units(std::string_view text) {
    return parse_integer<Quantity::rep>(
        text,
        false,
        0,
        std::numeric_limits<
            Quantity::rep>::max());
}

template <typename T>
[[nodiscard]]
bool failed(
    const std::variant<T, ParseError>& result) {
    return std::holds_alternative<
        ParseError>(result);
}

template <typename T>
[[nodiscard]]
ParseError error_of(
    const std::variant<T, ParseError>& result) {
    return std::get<ParseError>(result);
}

[[nodiscard]]
CandidateObservation rejected(
    DomainError error,
    const MatchingEngine& engine) {
    return CandidateObservation{
        {false, error},
        {},
        engine.snapshot()};
}

[[nodiscard]]
CandidateObservation from_engine_result(
    DomainResult<ExecutionReport> result,
    const MatchingEngine& engine) {
    if (std::holds_alternative<DomainError>(
            result)) {
        return rejected(
            std::get<DomainError>(result),
            engine);
    }

    return CandidateObservation{
        {true, std::nullopt},
        std::get<ExecutionReport>(
            std::move(result)).trades,
        engine.snapshot()};
}

[[nodiscard]]
CandidateObservation execute_one(
    MatchingEngine& engine,
    const RawNew& raw) {
    auto command =
        NewOrder::create(
            OrderId{raw.order_id},
            static_cast<Side>(raw.side_code),
            raw.price_ticks,
            raw.quantity_units);

    if (std::holds_alternative<DomainError>(
            command)) {
        return rejected(
            std::get<DomainError>(command),
            engine);
    }

    return from_engine_result(
        engine.process(
            std::get<NewOrder>(command)),
        engine);
}

[[nodiscard]]
CandidateObservation execute_one(
    MatchingEngine& engine,
    const RawCancel& raw) {
    return from_engine_result(
        engine.process(
            CancelOrder{
                OrderId{raw.order_id}}),
        engine);
}

[[nodiscard]]
CandidateObservation execute_one(
    MatchingEngine& engine,
    const RawModify& raw) {
    auto command =
        ModifyOrder::create(
            OrderId{raw.order_id},
            raw.price_ticks,
            raw.quantity_units);

    if (std::holds_alternative<DomainError>(
            command)) {
        return rejected(
            std::get<DomainError>(command),
            engine);
    }

    return from_engine_result(
        engine.process(
            std::get<ModifyOrder>(command)),
        engine);
}

}  // namespace

ParseResult
parse_lobq1(
    std::span<const std::byte> bytes) {
    if (bytes.empty()) {
        return fail(ParseError::EmptyInput);
    }

    if (bytes.size() >= 3 &&
        std::to_integer<unsigned int>(
            bytes[0]) == 0xEFU &&
        std::to_integer<unsigned int>(
            bytes[1]) == 0xBBU &&
        std::to_integer<unsigned int>(
            bytes[2]) == 0xBFU) {
        return fail(ParseError::Utf8Bom);
    }

    if (std::to_integer<unsigned int>(
            bytes.back()) != 0x0AU) {
        return fail(
            ParseError::MissingFinalLf);
    }

    for (const std::byte value : bytes) {
        const auto octet =
            std::to_integer<unsigned int>(
                value);

        if (octet == 0x0DU) {
            return fail(
                ParseError::CarriageReturn);
        }

        if (octet == 0x00U) {
            return fail(
                ParseError::EmbeddedNul);
        }

        if (octet > 0x7FU) {
            return fail(
                ParseError::NonAsciiByte);
        }
    }

    const std::string_view input{
        reinterpret_cast<const char*>(
            bytes.data()),
        bytes.size()};

    std::vector<std::string_view> records;

    std::size_t record_start = 0;

    while (record_start < input.size()) {
        const std::size_t newline =
            input.find(
                '\n',
                record_start);

        if (newline ==
            std::string_view::npos) {
            return fail(
                ParseError::MissingFinalLf);
        }

        const std::string_view record =
            input.substr(
                record_start,
                newline - record_start);

        if (record.empty()) {
            return fail(
                ParseError::BlankRecord);
        }

        if (record.size() >
            kMaximumRecordContent) {
            return fail(
                ParseError::RecordTooLong);
        }

        if (is_ascii_edge_whitespace(
                record.front()) ||
            is_ascii_edge_whitespace(
                record.back())) {
            return fail(
                ParseError::
                    InvalidNumericGrammar);
        }

        records.push_back(record);
        record_start = newline + 1;
    }

    if (records.empty()) {
        return fail(
            ParseError::InvalidHeader);
    }

    const auto header =
        split_fields(records.front());

    if (header.size() != 2 ||
        header[0] != "LOBQ1") {
        return fail(
            ParseError::InvalidHeader);
    }

    ParsedStream stream;

    if (header[1] == "EXHAUSTED") {
        stream.next_sequence =
            std::nullopt;
    } else {
        const auto allocator =
            parse_allocator(header[1]);

        if (failed(allocator)) {
            return fail(
                error_of(allocator));
        }

        stream.next_sequence =
            std::get<SequenceNumber::rep>(
                allocator);
    }

    stream.commands.reserve(
        records.size() - 1);

    for (std::size_t index = 1;
         index < records.size();
         ++index) {
        const auto fields =
            split_fields(records[index]);

        if (!fields.empty() &&
            fields[0] == "LOBQ1") {
            return fail(
                ParseError::DuplicateHeader);
        }

        if (fields.empty()) {
            return fail(
                ParseError::
                    UnknownCommandKind);
        }

        if (fields[0] == "N") {
            if (fields.size() != 5) {
                return fail(
                    ParseError::
                        WrongFieldCount);
            }

            const auto order_id =
                parse_order_id(fields[1]);

            const auto side_code =
                parse_side_code(fields[2]);

            const auto price_ticks =
                parse_price_ticks(fields[3]);

            const auto quantity_units =
                parse_quantity_units(
                    fields[4]);

            if (failed(order_id)) {
                return fail(
                    error_of(order_id));
            }

            if (failed(side_code)) {
                return fail(
                    error_of(side_code));
            }

            if (failed(price_ticks)) {
                return fail(
                    error_of(price_ticks));
            }

            if (failed(quantity_units)) {
                return fail(
                    error_of(
                        quantity_units));
            }

            stream.commands.emplace_back(
                RawNew{
                    std::get<OrderId::rep>(
                        order_id),
                    std::get<std::uint8_t>(
                        side_code),
                    std::get<Price::rep>(
                        price_ticks),
                    std::get<Quantity::rep>(
                        quantity_units)});

            continue;
        }

        if (fields[0] == "C") {
            if (fields.size() != 2) {
                return fail(
                    ParseError::
                        WrongFieldCount);
            }

            const auto order_id =
                parse_order_id(fields[1]);

            if (failed(order_id)) {
                return fail(
                    error_of(order_id));
            }

            stream.commands.emplace_back(
                RawCancel{
                    std::get<OrderId::rep>(
                        order_id)});

            continue;
        }

        if (fields[0] == "M") {
            if (fields.size() != 4) {
                return fail(
                    ParseError::
                        WrongFieldCount);
            }

            const auto order_id =
                parse_order_id(fields[1]);

            const auto price_ticks =
                parse_price_ticks(fields[2]);

            const auto quantity_units =
                parse_quantity_units(
                    fields[3]);

            if (failed(order_id)) {
                return fail(
                    error_of(order_id));
            }

            if (failed(price_ticks)) {
                return fail(
                    error_of(price_ticks));
            }

            if (failed(quantity_units)) {
                return fail(
                    error_of(
                        quantity_units));
            }

            stream.commands.emplace_back(
                RawModify{
                    std::get<OrderId::rep>(
                        order_id),
                    std::get<Price::rep>(
                        price_ticks),
                    std::get<Quantity::rep>(
                        quantity_units)});

            continue;
        }

        return fail(
            ParseError::UnknownCommandKind);
    }

    return stream;
}

CandidateRun
execute_candidate(
    const ParsedStream& stream) {
    MatchingEngine engine;

    std::optional<SequenceNumber>
        next_sequence;

    if (stream.next_sequence.has_value()) {
        const auto validated =
            SequenceNumber::from_value(
                *stream.next_sequence);

        if (!validated.has_value()) {
            throw std::logic_error(
                "ParsedStream contains invalid "
                "allocator seed");
        }

        next_sequence = *validated;
    }

    detail::
        MatchingEngineQualificationAccess::
            set_next_sequence(
                engine,
                next_sequence);

    CandidateRun run;

    run.entries.reserve(
        stream.commands.size());

    for (const RawCommand& raw :
         stream.commands) {
        CandidateObservation observation =
            std::visit(
                [&engine](
                    const auto& command) {
                    return execute_one(
                        engine,
                        command);
                },
                raw);

        run.entries.push_back(
            CandidateEntry{
                raw,
                std::move(observation)});
    }

    return run;
}

}  // namespace lob::qualification
