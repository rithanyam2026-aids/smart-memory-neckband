#pragma once

#include <stdint.h>
#include <string>
#include <vector>
#include <set>
#include <utility>

struct GridCell {
    int row;
    int col;
};

struct NamedZone {
    std::string id;
    std::string name;
    std::vector<GridCell> cells;
};

class HouseGridManager {
public:
    int rows = 8;
    int columns = 10;
    std::vector<GridCell> entrances;
    std::vector<GridCell> exits;
    std::vector<NamedZone> namedZones;

    // Dynamic private area settings saved in flash
    std::set<std::string> privateZones;
    std::set<std::pair<int, int>> privateCells;

    bool isInsideBounds(int r, int c) const {
        return (r >= 0 && r < rows && c >= 0 && c < columns);
    }

    bool isEntrance(int r, int c) const {
        for (const auto& e : entrances) {
            if (e.row == r && e.col == c) return true;
        }
        return false;
    }

    bool isExit(int r, int c) const {
        for (const auto& e : exits) {
            if (e.row == r && e.col == c) return true;
        }
        return false;
    }

    std::string getZoneName(int r, int c) const {
        if (!isInsideBounds(r, c)) return "Outside";
        for (const auto& zone : namedZones) {
            for (const auto& cell : zone.cells) {
                if (cell.row == r && cell.col == c) return zone.name;
            }
        }
        return "General Hallway";
    }

    bool isAreaPrivate(int r, int c) const {
        // 1. Cell override takes precedence
        if (privateCells.count({r, c}) > 0) return true;

        // 2. Zone level privacy
        std::string zone = getZoneName(r, c);
        if (privateZones.count(zone) > 0) return true;

        return false;
    }

    void setZonePrivacy(const std::string& zoneName, bool isPrivate) {
        if (isPrivate) privateZones.insert(zoneName);
        else privateZones.erase(zoneName);
    }

    void setCellPrivacy(int r, int c, bool isPrivate) {
        if (isPrivate) privateCells.insert({r, c});
        else privateCells.erase({r, c});
    }
};
