#!/usr/bin/env python3
"""Secretary Skill - SQLite storage for personal information management.

All data is stored as items with types. Types support inheritance (parent_type)
and abstract types for polymorphic filtering.

Usage:
    python3 secretary.py <command> [args...]

Commands:
    init                              Initialize the database
    item_add '<json>'                 Add an item
    item_add_batch '<json>'           Add multiple items
    item_get <id>                     Get item details
    item_update <id> '<json>'         Update an item
    item_delete <id>                  Delete an item
    item_list ['<json_filter>']       List items with optional filters
    item_search '<keyword>' [type]    Search items
    type_set '<json>'                 Define a type (with optional parent_type, abstract)
    type_get <name>                   Get a type definition (with inherited fields)
    type_list                         List all types
    type_tree                         List all types as a tree structure
    type_delete <name>                Delete a type
"""

import json
import sys
import os

# Allow imports from the scripts directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from items_mod import (
    cmd_init,
    cmd_item_add, cmd_item_add_batch, cmd_item_get, cmd_item_update,
    cmd_item_delete, cmd_item_list, cmd_item_search,
)
from types_mod import (
    cmd_type_set, cmd_type_get, cmd_type_list, cmd_type_tree, cmd_type_delete,
)


def main():
    if len(sys.argv) < 2:
        print("Usage: secretary.py <command> [args...]")
        print("Commands: init,")
        print("         item_add, item_add_batch, item_get, item_update, item_delete,")
        print("         item_list, item_search,")
        print("         type_set, type_get, type_list, type_tree, type_delete")
        sys.exit(1)

    command = sys.argv[1]

    try:
        if command == "init":
            cmd_init()
        # Item commands
        elif command == "item_add":
            cmd_item_add(sys.argv[2])
        elif command == "item_add_batch":
            cmd_item_add_batch(sys.argv[2])
        elif command == "item_get":
            cmd_item_get(sys.argv[2])
        elif command == "item_update":
            cmd_item_update(sys.argv[2], sys.argv[3])
        elif command == "item_delete":
            cmd_item_delete(sys.argv[2])
        elif command == "item_list":
            cmd_item_list(sys.argv[2] if len(sys.argv) > 2 else None)
        elif command == "item_search":
            cmd_item_search(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        # Type commands
        elif command == "type_set":
            cmd_type_set(sys.argv[2])
        elif command == "type_get":
            cmd_type_get(sys.argv[2])
        elif command == "type_list":
            cmd_type_list()
        elif command == "type_tree":
            cmd_type_tree()
        elif command == "type_delete":
            cmd_type_delete(sys.argv[2])
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
