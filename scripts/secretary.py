#!/usr/bin/env python3
"""Secretary Skill - SQLite storage for personal information management.

Usage:
    python3 secretary.py <command> [args...]

Commands:
    init                                  Initialize the database
    store '<json>'                        Store a single entry
    store_batch '<json_array>'            Store multiple entries
    query '<json_filter>'                 Query entries with filters
    search '<keyword>'                    Full-text search entries
    update <id> '<json>'                  Update an entry
    delete <id>                           Delete an entry
    summary '<json>'                      Get a period summary
    list                                  List all active entries
    entry_link <entry_id> '<json>'        Link person(s) to an entry
    entry_unlink <entry_id> <person_id>   Unlink a person from an entry
    person_entries <person_id>            List entries linked to a person
    person_add '<json>'                   Add a new person
    person_update <id> '<json>'           Update a person
    person_delete <id>                    Delete a person
    person_get <id>                       Get a person with attributes
    person_list ['<json_filter>']         List persons
    person_search '<keyword>'             Search persons
    person_tag_add <person_id> <tag>      Add a tag to a person
    person_tag_remove <person_id> <tag>   Remove a tag from a person
    attr_set <person_id> '<json>'         Set attributes
    attr_delete <attr_id>                 Delete an attribute
    attr_list <person_id> [category]      List attributes
    tags_list [source]                    List all tags (entries|persons|items)
    tag_schema_set '<json>'               Define a tag's schema
    tag_schema_get <tag>                  Get a tag's schema
    tag_schema_list                       List all tag schemas
    tag_schema_delete <tag>               Delete a tag's schema
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
    item_relate '<json>'                  Create a relation
    item_unrelate <id>                    Remove a relation
"""

import json
import sys
import os

# Allow imports from the scripts directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from entries import (
    cmd_init, cmd_store, cmd_store_batch, cmd_query, cmd_search,
    cmd_update, cmd_delete, cmd_summary, cmd_list,
    cmd_entry_link, cmd_entry_unlink, cmd_person_entries,
)
from persons import (
    cmd_person_add, cmd_person_update, cmd_person_delete,
    cmd_person_get, cmd_person_list, cmd_person_search,
    cmd_person_tag_add, cmd_person_tag_remove,
    cmd_attr_set, cmd_attr_delete, cmd_attr_list,
)
from tags import (
    cmd_tags_list, cmd_tag_schema_set, cmd_tag_schema_get,
    cmd_tag_schema_list, cmd_tag_schema_delete,
)
from collections_mod import (
    cmd_col_create, cmd_col_list, cmd_col_get, cmd_col_update, cmd_col_delete,
    cmd_item_add, cmd_item_add_batch, cmd_item_get, cmd_item_update,
    cmd_item_delete, cmd_item_list, cmd_item_search,
    cmd_item_relate, cmd_item_unrelate,
)


def main():
    if len(sys.argv) < 2:
        print("Usage: secretary.py <command> [args...]")
        print("Commands: init, store, store_batch, query, search, update, delete, summary, list,")
        print("         entry_link, entry_unlink, person_entries,")
        print("         person_add, person_update, person_delete, person_get, person_list,")
        print("         person_search, person_tag_add, person_tag_remove,")
        print("         attr_set, attr_delete, attr_list,")
        print("         tags_list, tag_schema_set, tag_schema_get, tag_schema_list, tag_schema_delete,")
        print("         col_create, col_list, col_get, col_update, col_delete,")
        print("         item_add, item_add_batch, item_get, item_update, item_delete,")
        print("         item_list, item_search, item_relate, item_unrelate")
        sys.exit(1)

    command = sys.argv[1]

    try:
        if command == "init":
            cmd_init()
        elif command == "store":
            cmd_store(sys.argv[2])
        elif command == "store_batch":
            cmd_store_batch(sys.argv[2])
        elif command == "query":
            cmd_query(sys.argv[2] if len(sys.argv) > 2 else "{}")
        elif command == "search":
            cmd_search(sys.argv[2])
        elif command == "update":
            cmd_update(sys.argv[2], sys.argv[3])
        elif command == "delete":
            cmd_delete(sys.argv[2])
        elif command == "summary":
            cmd_summary(sys.argv[2] if len(sys.argv) > 2 else '{"type": "today"}')
        elif command == "list":
            cmd_list()
        # Entry-person link commands
        elif command == "entry_link":
            cmd_entry_link(sys.argv[2], sys.argv[3])
        elif command == "entry_unlink":
            cmd_entry_unlink(sys.argv[2], sys.argv[3])
        elif command == "person_entries":
            cmd_person_entries(sys.argv[2])
        # Person commands
        elif command == "person_add":
            cmd_person_add(sys.argv[2])
        elif command == "person_update":
            cmd_person_update(sys.argv[2], sys.argv[3])
        elif command == "person_delete":
            cmd_person_delete(sys.argv[2])
        elif command == "person_get":
            cmd_person_get(sys.argv[2])
        elif command == "person_list":
            cmd_person_list(sys.argv[2] if len(sys.argv) > 2 else None)
        elif command == "person_search":
            cmd_person_search(sys.argv[2])
        # Person tag commands
        elif command == "person_tag_add":
            cmd_person_tag_add(sys.argv[2], sys.argv[3])
        elif command == "person_tag_remove":
            cmd_person_tag_remove(sys.argv[2], sys.argv[3])
        # Attribute commands
        elif command == "attr_set":
            cmd_attr_set(sys.argv[2], sys.argv[3])
        elif command == "attr_delete":
            cmd_attr_delete(sys.argv[2])
        elif command == "attr_list":
            cmd_attr_list(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        # Tag listing & schema commands
        elif command == "tags_list":
            cmd_tags_list(sys.argv[2] if len(sys.argv) > 2 else None)
        elif command == "tag_schema_set":
            cmd_tag_schema_set(sys.argv[2])
        elif command == "tag_schema_get":
            cmd_tag_schema_get(sys.argv[2])
        elif command == "tag_schema_list":
            cmd_tag_schema_list()
        elif command == "tag_schema_delete":
            cmd_tag_schema_delete(sys.argv[2])
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
        # Collection item relation commands
        elif command == "item_relate":
            cmd_item_relate(sys.argv[2])
        elif command == "item_unrelate":
            cmd_item_unrelate(sys.argv[2])
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
