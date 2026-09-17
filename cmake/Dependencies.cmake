include(FetchContent)

# Keep the external test dependency deliberately narrow.
set(BUILD_GMOCK OFF CACHE BOOL "Do not build GoogleMock" FORCE)
set(INSTALL_GTEST OFF CACHE BOOL "Do not install GoogleTest" FORCE)

# Match the shared MSVC runtime used by the parent project.
if(MSVC)
  set(gtest_force_shared_crt ON CACHE BOOL "Use shared MSVC runtime for GoogleTest" FORCE)
endif()

FetchContent_Declare(
  googletest
  URL
    https://github.com/google/googletest/releases/download/v1.18.0/googletest-1.18.0.tar.gz
  URL_HASH
    SHA256=6e3191c1455468b3fc35a417fb565c1c5071aee1b7e7f85e30cf48a98d37d8b5
  DOWNLOAD_EXTRACT_TIMESTAMP
    TRUE
)

FetchContent_MakeAvailable(googletest)
