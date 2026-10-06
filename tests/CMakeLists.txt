add_executable(
  lob_unit_tests
  unit/version_test.cpp
  unit/domain_test.cpp
  unit/matching_engine_test.cpp
)

target_link_libraries(
  lob_unit_tests
  PRIVATE
    lob::core
    GTest::gtest_main
    lob_project_warnings
)

set_target_properties(
  lob_unit_tests
  PROPERTIES
    CXX_EXTENSIONS OFF
)

include(GoogleTest)

gtest_discover_tests(
  lob_unit_tests
  DISCOVERY_TIMEOUT 30
)

add_library(
  lob_candidate_adapter
  STATIC
    ${PROJECT_SOURCE_DIR}/tools/differential/candidate_adapter.cpp
)

target_include_directories(
  lob_candidate_adapter
  PUBLIC
    ${PROJECT_SOURCE_DIR}/tools/differential
  PRIVATE
    ${PROJECT_SOURCE_DIR}
)

target_link_libraries(
  lob_candidate_adapter
  PUBLIC
    lob::core
  PRIVATE
    lob_project_warnings
)

set_target_properties(
  lob_candidate_adapter
  PROPERTIES
    CXX_EXTENSIONS OFF
)

add_executable(
  lob_m5_candidate_adapter_tests
  qualification/m5/candidate_adapter_test.cpp
)

target_include_directories(
  lob_m5_candidate_adapter_tests
  PRIVATE
    ${PROJECT_SOURCE_DIR}
)

target_link_libraries(
  lob_m5_candidate_adapter_tests
  PRIVATE
    lob_candidate_adapter
    GTest::gtest_main
    lob_project_warnings
)

set_target_properties(
  lob_m5_candidate_adapter_tests
  PROPERTIES
    CXX_EXTENSIONS OFF
)

gtest_discover_tests(
  lob_m5_candidate_adapter_tests
  DISCOVERY_TIMEOUT 30
)

add_library(
  lob_candidate_canonical_trace
  STATIC
    ${PROJECT_SOURCE_DIR}/tools/differential/candidate_canonical_trace.cpp
)

target_include_directories(
  lob_candidate_canonical_trace
  PUBLIC
    ${PROJECT_SOURCE_DIR}/tools/differential
)

target_link_libraries(
  lob_candidate_canonical_trace
  PUBLIC
    lob::core
  PRIVATE
    lob_project_warnings
)

set_target_properties(
  lob_candidate_canonical_trace
  PROPERTIES
    CXX_EXTENSIONS OFF
)

add_executable(
  lob_m5_candidate_canonical_trace_tests
  qualification/m5/candidate_canonical_trace_test.cpp
)

target_link_libraries(
  lob_m5_candidate_canonical_trace_tests
  PRIVATE
    lob_candidate_canonical_trace
    GTest::gtest_main
    lob_project_warnings
)

set_target_properties(
  lob_m5_candidate_canonical_trace_tests
  PROPERTIES
    CXX_EXTENSIONS OFF
)

gtest_discover_tests(
  lob_m5_candidate_canonical_trace_tests
  DISCOVERY_TIMEOUT 30
)

add_executable(
  lob_m5_candidate_runner
  ${PROJECT_SOURCE_DIR}/tools/differential/candidate_runner.cpp
)

target_link_libraries(
  lob_m5_candidate_runner
  PRIVATE
    lob_candidate_adapter
    lob_candidate_canonical_trace
    lob_project_warnings
)

set_target_properties(
  lob_m5_candidate_runner
  PROPERTIES
    CXX_EXTENSIONS OFF
)
