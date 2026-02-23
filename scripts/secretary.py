#!/usr/bin/env python3
"""Secretary Skill - SQLite storage for personal information management.

All data is stored as items within dynamic collections. Relationships between
items are expressed via IDs in each item's JSON data field.

Usage:
    python3 secretary.py <command> [args...]

Commands:
    init                                  Initialize the database
    col_create '<json>'                   Create a new collection
    col_list                              List all collections
    col_get <id>                          Get collection details
    col_update <id> '<json>'              Update a collection
    col_delete <id>                       Delete a collection
    item_add <col_id> '<json>'            Add item to a collection
    item_add_batch <col_id> '<json>'      Add multiple items
    item_get <id>                         Get item details
    item_update <id> '<json>'             Update an item
    item_delete <id>                      Delete an item
    item_list <col_id> ['<json_filter>']  List items in a collection
    item_search '<keyword>' [col_id]      Search items
    tags_list                             List all tags
    type_set '<json>'                     Define a type
    type_get <name>                       Get a type definition
    type_list                             List all types
    type_delete <name>                    Delete a type
"""

import json
import sys
import os

# Allow imports from the scripts directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collections_mod import (
    cmd_init,
    cmd_col_create, cmd_col_list, cmd_col_get, cmd_col_update, cmd_col_delete,
    cmd_item_add, cmd_item_add_batch, cmd_item_get, cmd_item_update,
    cmd_item_delete, cmd_item_list, cmd_item_search,
)
from tags import (
    cmd_tags_list, cmd_type_set, cmd_type_get,
    cmd_type_list, cmd_type_delete,
)


def main():
    if len(sys.argv) < 2:
        print("Usage: secretary.py <command> [args...]")
        print("Commands: init,")
        print("         col_create, col_list, col_get, col_update, col_delete,")
        print("         item_add, item_add_batch, item_get, item_update, item_delete,")
        print("         item_list, item_search,")
        print("         tags_list, type_set, type_get, type_list, type_delete")
        sys.exit(1)

    command = sys.argv[1]

    try:
        if command == "init":
            cmd_init()
        # Collection commands
        elif command == "col_create":
            cmd_col_create(sys.argv[2])
        elif command == "col_list":
            cmd_col_list()
        elif command == "col_get":
            cmd_col_get(sys.argv[2])
        elif command == "col_update":
            cmd_col_update(sys.argv[2], sys.argv[3])
        elif command == "col_delete":
            cmd_col_delete(sys.argv[2])
        # Collection item commands
        elif command == "item_add":
            cmd_item_add(sys.argv[2], sys.argv[3])
        elif command == "item_add_batch":
            cmd_item_add_batch(sys.argv[2], sys.argv[3])
        elif command == "item_get":
            cmd_item_get(sys.argv[2])
        elif command == "item_update":
            cmd_item_update(sys.argv[2], sys.argv[3])
        elif command == "item_delete":
            cmd_item_delete(sys.argv[2])
        elif command == "item_list":
            cmd_item_list(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        elif command == "item_search":
            cmd_item_search(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        # Tag listing
        elif command == "tags_list":
            cmd_tags_list()
        # Type commands
        elif command == "type_set":
            cmd_type_set(sys.argv[2])
        elif command == "type_get":
            cmd_type_get(sys.argv[2])
        elif command == "type_list":
            cmd_type_list()
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
