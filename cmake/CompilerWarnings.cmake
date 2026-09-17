function(lob_set_project_warnings target_name)
  if(MSVC)
    target_compile_options(
      ${target_name}
      INTERFACE
        /W4
        /permissive-
    )

    if(LOB_WARNINGS_AS_ERRORS)
      target_compile_options(${target_name} INTERFACE /WX)
    endif()
  elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(
      ${target_name}
      INTERFACE
        -Wall
        -Wextra
        -Wpedantic
    )

    if(LOB_WARNINGS_AS_ERRORS)
      target_compile_options(${target_name} INTERFACE -Werror)
    endif()
  else()
    message(
      WARNING
      "No project warning profile is defined for compiler "
      "${CMAKE_CXX_COMPILER_ID}"
    )
  endif()
endfunction()
