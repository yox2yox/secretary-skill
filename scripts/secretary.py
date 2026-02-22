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
    tag_schema_set '<json>'               Define a tag's schema
    tag_schema_get <tag>                  Get a tag's schema
    tag_schema_list                       List all tag schemas
    tag_schema_delete <tag>               Delete a tag's schema
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
    cmd_tags_list, cmd_tag_schema_set, cmd_tag_schema_get,
    cmd_tag_schema_list, cmd_tag_schema_delete,
)


def main():
    if len(sys.argv) < 2:
        print("Usage: secretary.py <command> [args...]")
        print("Commands: init,")
        print("         col_create, col_list, col_get, col_update, col_delete,")
        print("         item_add, item_add_batch, item_get, item_update, item_delete,")
        print("         item_list, item_search,")
        print("         tags_list, tag_schema_set, tag_schema_get, tag_schema_list, tag_schema_delete")
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
        # Tag listing & schema commands
        elif command == "tags_list":
            cmd_tags_list()
        elif command == "tag_schema_set":
            cmd_tag_schema_set(sys.argv[2])
        elif command == "tag_schema_get":
            cmd_tag_schema_get(sys.argv[2])
        elif command == "tag_schema_list":
            cmd_tag_schema_list()
        elif command == "tag_schema_delete":
            cmd_tag_schema_delete(sys.argv[2])
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
