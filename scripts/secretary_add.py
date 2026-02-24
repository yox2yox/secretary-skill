#!/usr/bin/env python3
"""Secretary Skill (Add) - Data addition, update, deletion, and type management.

Usage:
    python3 secretary_add.py <command> [args...]

Commands:
    init                              Initialize the database
    item_add '<json>'                 Add an item
    item_add_batch '<json>'           Add multiple items
    item_update <id> '<json>'         Update an item
    item_delete <id>                  Delete an item
    type_set '<json>'                 Define a type (with optional parent_type, abstract)
    type_get <name>                   Get a type definition (with inherited fields)
    type_list                         List all types
    type_tree                         List all types as a tree structure
    type_delete <name>                Delete a type
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from items_mod import (
    cmd_init,
    cmd_item_add, cmd_item_add_batch, cmd_item_update, cmd_item_delete,
)
from types_mod import (
    cmd_type_set, cmd_type_get, cmd_type_list, cmd_type_tree, cmd_type_delete,
)


def main():
    if len(sys.argv) < 2:
        print("Usage: secretary_add.py <command> [args...]")
        print("Commands: init,")
        print("         item_add, item_add_batch, item_update, item_delete,")
        print("         type_set, type_get, type_list, type_tree, type_delete")
        sys.exit(1)

    command = sys.argv[1]

    try:
        if command == "init":
            cmd_init()
        elif command == "item_add":
            cmd_item_add(sys.argv[2])
        elif command == "item_add_batch":
            cmd_item_add_batch(sys.argv[2])
        elif command == "item_update":
            cmd_item_update(sys.argv[2], sys.argv[3])
        elif command == "item_delete":
            cmd_item_delete(sys.argv[2])
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
