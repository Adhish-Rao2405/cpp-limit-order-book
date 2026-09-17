#include "lob/version.hpp"

#include <gtest/gtest.h>

#include <string_view>

namespace {

TEST(VersionTest, ReportsProjectVersion) {
  EXPECT_EQ(lob::version(), std::string_view{"0.1.0"});
}

TEST(VersionTest, VersionQueryIsNoexcept) {
  static_assert(noexcept(lob::version()));
  SUCCEED();
}

}  // namespace
