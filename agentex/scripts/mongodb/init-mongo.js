// Initialize the agentex database
db = db.getSiblingDB('agentex');

// Check if collection exists before creating it
const collections = db.getCollectionNames();
if (!collections.includes('messages')) {
  db.createCollection('messages');
  print('Created messages collection');
} else {
  print('Messages collection already exists');
}

if (!collections.includes('task_states')) {
  db.createCollection('task_states');
  print('Created task_states collection');
} else {
  print('Task states collection already exists');
}

// Creating an index is already idempotent in MongoDB

db.task_states.createIndex({ task_id: 1, agent_id: 1 }, { unique: true });

print('MongoDB initialization completed successfully');
