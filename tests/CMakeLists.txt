add_executable(
  lob_unit_tests
  unit/version_test.cpp
  unit/domain_test.cpp
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
