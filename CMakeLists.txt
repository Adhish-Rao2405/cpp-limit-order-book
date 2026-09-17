cmake_minimum_required(VERSION 3.25)

project(
  cpp_limit_order_book
  VERSION 0.1.0
  DESCRIPTION "C++20 limit-order-book engineering project"
  LANGUAGES CXX
)

add_library(lob_project_options INTERFACE)
target_compile_features(lob_project_options INTERFACE cxx_std_20)
set_target_properties(lob_project_options PROPERTIES CXX_EXTENSIONS OFF)
