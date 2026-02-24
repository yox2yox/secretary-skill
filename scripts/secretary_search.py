#!/usr/bin/env python3
"""Secretary Skill (Search) - Data search, listing, and retrieval.

Usage:
    python3 secretary_search.py <command> [args...]

Commands:
    init                              Initialize the database
    item_get <id>                     Get item details
    item_list ['<json_filter>']       List items with optional filters
    item_search '<keyword>' [type]    Search items
    type_tree                         List all types as a tree structure
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from items_mod import (
    cmd_init,
    cmd_item_get, cmd_item_list, cmd_item_search,
)
from types_mod import cmd_type_tree


def main():
    if len(sys.argv) < 2:
        print("Usage: secretary_search.py <command> [args...]")
        print("Commands: init,")
        print("         item_get, item_list, item_search,")
        print("         type_tree")
        sys.exit(1)

    command = sys.argv[1]

    try:
        if command == "init":
            cmd_init()
        elif command == "item_get":
            cmd_item_get(sys.argv[2])
        elif command == "item_list":
            cmd_item_list(sys.argv[2] if len(sys.argv) > 2 else None)
        elif command == "item_search":
            cmd_item_search(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        elif command == "type_tree":
            cmd_type_tree()
        else:
            print(json.dumps({"status": "error", "message": f"Unknown command: {command}"}))
            sys.exit(1)
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "message": f"Invalid JSON: {e}"}))
        sys.exit(1)
    except KeyError as e:
        print(json.dumps({"status": "error", "message": f"Missing required field: {e}"}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
