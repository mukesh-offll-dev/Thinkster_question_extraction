"""
One-shot script to remove duplicate Worksheet_Report documents.
Keeps the latest entry (highest _id) for each (worksheet_id, question_number) pair.
"""
from pymongo import MongoClient
import config

client = MongoClient(config.MONGO_URI)
db = client[config.MONGO_DB]
coll = db["Worksheet_Report"]

pipeline = [
    {"$sort": {"_id": -1}},
    {"$group": {
        "_id": {"worksheet_id": "$worksheet_id", "question_number": "$question_number"},
        "keep_id": {"$first": "$_id"},
        "count": {"$sum": 1}
    }},
    {"$match": {"count": {"$gt": 1}}}
]

dupes = list(coll.aggregate(pipeline))
print(f"Found {len(dupes)} question(s) with duplicates.")

removed = 0
for d in dupes:
    ws_id = d["_id"]["worksheet_id"]
    q_num = d["_id"]["question_number"]
    keep_id = d["keep_id"]
    result = coll.delete_many({
        "worksheet_id": ws_id,
        "question_number": q_num,
        "_id": {"$ne": keep_id}
    })
    removed += result.deleted_count
    print(f"  Worksheet {ws_id} Q{q_num}: removed {result.deleted_count} duplicate(s)")

print(f"\nDone. Total duplicates removed: {removed}")
