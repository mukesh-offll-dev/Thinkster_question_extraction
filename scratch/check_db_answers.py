import os
import sys
from pymongo import MongoClient
import json

# Add parent directory to path so we can import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

print("Connecting to MongoDB...")
client = MongoClient(config.MONGO_URI)
db = client[config.MONGO_DB]
coll = db[config.MONGO_ANSWERS_COLLECTION]

# Print count of documents
count = coll.count_documents({})
print(f"Total worksheet answer documents: {count}")

# Print first 5 documents
print("\nFirst 5 documents:")
for doc in coll.find().limit(5):
    # Convert ObjectId to string for printing
    doc["_id"] = str(doc["_id"])
    print(json.dumps(doc, indent=2))
