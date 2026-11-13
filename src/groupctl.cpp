#include "groupctl.hpp"
#include <iostream>
#include <fstream>
#include <filesystem>
#include <chrono>
#include <iomanip>
#include <sstream>
#include <random>

namespace fs = std::filesystem;

int GroupController::handle_init(const std::string& group_id, const std::string& person_id, const std::string& display_name) {
    try {
        // 1. 建立 .group 及子目錄結構
        fs::path group_dir = ".group";
        fs::create_directories(group_dir / "assignment");
        fs::create_directories(group_dir / "members");
        fs::create_directories(group_dir / "events");
        fs::create_directories(group_dir / "final");
        fs::create_directories(group_dir / "local");

        // 確保 .group/local/ 裡有一個 .gitkeep
        std::ofstream gitkeep(group_dir / "local" / ".gitkeep");
        
        // 2. 寫入 group.json
        fs::path group_json_path = group_dir / "group.json";
        std::ofstream group_file(group_json_path);
        group_file << "{\n"
                   << "  \"protocol_version\": \"0.1\",\n"
                   << "  \"group_id\": \"" << group_id << "\",\n"
                   << "  \"canonical_branch\": \"main\",\n"
                   << "  \"assignment_file\": \".group/assignment/assignment.md\"\n"
                   << "}\n";

        // 3. 取得目前的 ISO 8601 時間戳記作為 joined_at
        auto now = std::chrono::system_clock::now();
        auto in_time_t = std::chrono::system_clock::to_time_t(now);
        std::stringstream ss;
        ss << std::put_time(std::gmtime(&in_time_t), "%Y-%m-%dT%H:%M:%SZ");

        // 4. 寫入成員描述檔 .group/members/<person_id>.json
        fs::path member_file_path = group_dir / "members" / (person_id + ".json");
        std::ofstream member_file(member_file_path);
        member_file << "{\n"
                    << "  \"protocol_version\": \"0.1\",\n"
                    << "  \"person_id\": \"" << person_id << "\",\n"
                    << "  \"display_name\": \"" << display_name << "\",\n"
                    << "  \"joined_at\": \"" << ss.str() << "\"\n"
                    << "}\n";

        std::cout << "Successfully initialized group environment for group " << group_id 
                  << " with member " << person_id << " (" << display_name << ").\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "Error during initialization: " << e.what() << "\n";
        return 1;
    }
}

int GroupController::handle_event_create(const std::string& event_type, const std::string& person_id, const std::string& group_id, const std::string& summary) {
    try {
        // 確保 .group/events/ 目錄存在
        fs::path events_dir = fs::path(".group") / "events";
        fs::create_directories(events_dir);

        // 1. 取得目前的 UTC 時間戳記
        auto now = std::chrono::system_clock::now();
        auto in_time_t = std::chrono::system_clock::to_time_t(now);
        
        std::stringstream ts_ss, file_ts_ss;
        file_ts_ss << std::put_time(std::gmtime(&in_time_t), "%Y%m%dT%H%M%SZ");
        ts_ss << std::put_time(std::gmtime(&in_time_t), "%Y-%m-%dT%H:%M:%SZ");

        // 2. 產生短隨機後綴 (4 位 hex)
        std::random_device rd;
        std::mt19937 gen(rd());
        std::uniform_int_distribution<> dis(0, 15);
        std::stringstream suffix_ss;
        for (int i = 0; i < 4; ++i) {
            suffix_ss << std::hex << dis(gen);
        }

        // 3. 組合 event_id (格式: E-<UTC timestamp>-<person_id>-<short unique suffix>)
        std::string event_id = "E-" + file_ts_ss.str() + "-" + person_id + "-" + suffix_ss.str();

        // 4. 建立事件 JSON 檔案
        fs::path event_file_path = events_dir / (event_id + ".json");
        std::ofstream event_file(event_file_path);

        // 5. 寫入結構化事件內容
        event_file << "{\n"
                   << "  \"protocol_version\": \"0.1\",\n"
                   << "  \"event_id\": \"" << event_id << "\",\n"
                   << "  \"event_type\": \"" << event_type << "\",\n"
                   << "  \"group_id\": \"" << group_id << "\",\n"
                   << "  \"person_id\": \"" << person_id << "\",\n"
                   << "  \"created_at\": \"" << ts_ss.str() << "\",\n"
                   << "  \"related_events\": [],\n"
                   << "  \"summary\": \"" << summary << "\"\n"
                   << "}\n";

        std::cout << "Successfully created event: " << event_id << " (" << event_type << ")\n"
                  << "Saved to: " << event_file_path.string() << "\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "Error creating event: " << e.what() << "\n";
        return 1;
    }
}