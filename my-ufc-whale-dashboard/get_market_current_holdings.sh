#!/bin/bash

# Define paths
DATA_DIR="data"
OUTPUT_FILE="$DATA_DIR/all_ufc_volumes.json"
TEMP_DIR="temp_volume_data"

# Ensure data and temp directories exist
mkdir -p "$DATA_DIR"
mkdir -p "$TEMP_DIR"

echo "Fetching active UFC events..."
# Fetch list of active UFC events
# We look for events with tag 'ufc' that are active and not closed
EVENTS_JSON=$(curl -s "https://gamma-api.polymarket.com/events?tag_slug=ufc&active=true&closed=false&archived=false&limit=100")

# Extract IDs
EVENT_IDS=$(echo "$EVENTS_JSON" | jq -r '.[].id')

if [ -z "$EVENT_IDS" ]; then
    echo "No active UFC events found."
    # Create empty array file to prevent errors downstream
    echo "[]" > "$OUTPUT_FILE"
    exit 0
fi

echo "Found events. Starting data collection..."

# Iterate through each event ID
for id in $EVENT_IDS; do
    echo "Fetching volume for Event ID: $id"
    
    # Fetch live volume
    # The API returns an array containing a single object: [{ "total": ..., "markets": [...] }]
    VOL_RES=$(curl -s "https://data-api.polymarket.com/live-volume?id=$id")
    
    # Check if response is valid JSON array and not empty
    # We use jq to verify it's an array and has at least one element
    IS_VALID=$(echo "$VOL_RES" | jq 'if type=="array" then length > 0 else false end' 2>/dev/null)
    
    if [ "$IS_VALID" == "true" ]; then
        # Inject eventId into the object and save to temp file
        # We take the first element (.[0]) and add the eventId field for easier reference in the dashboard
        echo "$VOL_RES" | jq --arg eid "$id" '.[0] + {eventId: $eid}' > "$TEMP_DIR/$id.json"
    else
        echo "Warning: No valid volume data returned for Event ID $id"
    fi
    
    # Polite delay to avoid rate limiting
    sleep 0.1
done

echo "Aggregating data to $OUTPUT_FILE..."
# Combine all temp JSON objects into a single array
# jq -s '.' takes all input objects and wraps them in a single array [obj1, obj2, ...]
if ls "$TEMP_DIR"/*.json 1> /dev/null 2>&1; then
    jq -s '.' "$TEMP_DIR"/*.json > "$OUTPUT_FILE"
    echo "Success! Data saved to $OUTPUT_FILE"
else
    echo "No data collected."
    echo "[]" > "$OUTPUT_FILE"
fi

# Cleanup
rm -rf "$TEMP_DIR"
