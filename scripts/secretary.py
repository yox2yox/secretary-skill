#!/usr/bin/env python3
"""Secretary Skill - SQLite storage for personal information management.

All data is stored as items with types and tags. Relationships between
items are expressed via IDs in each item's JSON data field.

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
    tag_create '<json>'               Create a tag (with optional parent_id)
    tag_update <id> '<json>'          Update a tag
    tag_delete <id>                   Delete a tag
    tag_get <id>                      Get tag details with children
    tags_list                         List all tags with hierarchy info
    tags_list_level <level>           List tags at a specific hierarchy level
    tags_tree                         List all tags as a tree structure
    type_set '<json>'                 Define a type
    type_get <name>                   Get a type definition
    type_list                         List all types
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
from tags import (
    cmd_tag_create, cmd_tag_update, cmd_tag_delete, cmd_tag_get,
    cmd_tags_list, cmd_tags_list_level, cmd_tags_tree,
    cmd_type_set, cmd_type_get, cmd_type_list, cmd_type_delete,
)


def main():
    if len(sys.argv) < 2:
        print("Usage: secretary.py <command> [args...]")
        print("Commands: init,")
        print("         item_add, item_add_batch, item_get, item_update, item_delete,")
        print("         item_list, item_search,")
        print("         tag_create, tag_update, tag_delete, tag_get,")
        print("         tags_list, tags_list_level, tags_tree,")
        print("         type_set, type_get, type_list, type_delete")
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
        # Tag commands
        elif command == "tag_create":
            cmd_tag_create(sys.argv[2])
        elif command == "tag_update":
            cmd_tag_update(sys.argv[2], sys.argv[3])
        elif command == "tag_delete":
            cmd_tag_delete(sys.argv[2])
        elif command == "tag_get":
            cmd_tag_get(sys.argv[2])
        elif command == "tags_list":
            cmd_tags_list()
        elif command == "tags_list_level":
            cmd_tags_list_level(sys.argv[2])
        elif command == "tags_tree":
            cmd_tags_tree()
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
