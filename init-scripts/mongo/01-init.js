// MongoDB Initialization Script
// Creates the safeops database with required collections

db = db.getSiblingDB('safeops');

// Create collections with schema validation
db.createCollection('raw_logs', {
    validator: {
        $jsonSchema: {
            bsonType: 'object',
            required: ['source', 'payload', 'received_at'],
            properties: {
                source: {
                    bsonType: 'string',
                    description: 'CI/CD provider (github_actions, gitlab_ci)'
                },
                payload: {
                    bsonType: 'object',
                    description: 'Raw webhook payload'
                },
                received_at: {
                    bsonType: 'date',
                    description: 'Timestamp when log was received'
                },
                signature_valid: {
                    bsonType: 'bool',
                    description: 'HMAC signature validation result'
                }
            }
        }
    }
});

db.createCollection('parsed_logs', {
    validator: {
        $jsonSchema: {
            bsonType: 'object',
            required: ['raw_log_id', 'templates', 'parsed_at'],
            properties: {
                raw_log_id: {
                    bsonType: 'objectId',
                    description: 'Reference to raw_logs collection'
                },
                templates: {
                    bsonType: 'array',
                    description: 'Drain-parsed log templates'
                },
                event_ids: {
                    bsonType: 'array',
                    description: 'Event ID mapping'
                },
                parsed_at: {
                    bsonType: 'date',
                    description: 'Timestamp when parsing completed'
                }
            }
        }
    }
});

// Create indexes for efficient querying
db.raw_logs.createIndex({ 'received_at': -1 });
db.raw_logs.createIndex({ 'source': 1 });
db.parsed_logs.createIndex({ 'raw_log_id': 1 });
db.parsed_logs.createIndex({ 'parsed_at': -1 });

print('SafeOps MongoDB initialization complete!');
