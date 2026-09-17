cmake_minimum_required(VERSION 3.25)

project(
  cpp_limit_order_book
  VERSION 0.1.0
  DESCRIPTION "C++20 limit-order-book engineering project"
  LANGUAGES CXX
)

option(
  LOB_WARNINGS_AS_ERRORS
  "Treat warnings in first-party project code as errors"
  ON
)

add_library(lob_project_options INTERFACE)
target_compile_features(lob_project_options INTERFACE cxx_std_20)

include(cmake/CompilerWarnings.cmake)

add_library(lob_project_warnings INTERFACE)
lob_set_project_warnings(lob_project_warnings)

add_library(
  lob_core
  STATIC
  src/version.cpp
)

add_library(lob::core ALIAS lob_core)

target_include_directories(
  lob_core
  PUBLIC
    $<BUILD_INTERFACE:${PROJECT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

target_link_libraries(
  lob_core
  PUBLIC
    lob_project_options
  PRIVATE
    lob_project_warnings
)

set_target_properties(
  lob_core
  PROPERTIES
    CXX_EXTENSIONS OFF
)

include(CTest)

if(BUILD_TESTING)
  include(cmake/Dependencies.cmake)
  add_subdirectory(tests)
endif()
