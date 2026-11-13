#pragma once
#include <string>

class GroupController {
public:
    static int handle_init(const std::string& group_id, const std::string& person_id, const std::string& display_name);
    static int handle_event_create(const std::string& event_type, const std::string& person_id, const std::string& group_id, const std::string& summary);
};