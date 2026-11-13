cmake_minimum_required(VERSION 3.12)
project(groupctl VERSION 0.1 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include_directories(${CMAKE_CURRENT_SOURCE_DIR}/include)

add_executable(groupctl
    src/main.cpp
    src/groupctl.cpp
)