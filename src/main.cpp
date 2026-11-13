#include <iostream>
#include <string>
#include "groupctl.hpp"

void print_usage(const char* program_name) {
    std::cout << "Usage:\n"
              << "  " << program_name << " init <group_id> <person_id> <display_name>\n"
              << "  " << program_name << " event <event_type> <person_id> <group_id> <summary>\n";
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        print_usage(argv[0]);
        return 1;
    }

    std::string command = argv[1];

    if (command == "init") {
        if (argc < 5) {
            std::cerr << "Error: 'init' requires <group_id>, <person_id>, and <display_name>.\n";
            print_usage(argv[0]);
            return 1;
        }
        return GroupController::handle_init(argv[2], argv[3], argv[4]);

    } else if (command == "event") {
        if (argc < 6) {
            std::cerr << "Error: 'event' requires <event_type>, <person_id>, <group_id>, and <summary>.\n";
            print_usage(argv[0]);
            return 1;
        }
        return GroupController::handle_event_create(argv[2], argv[3], argv[4], argv[5]);

    } else {
        std::cerr << "Unknown command: " << command << "\n";
        print_usage(argv[0]);
        return 1;
    }
}