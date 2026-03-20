# Federation Heartbeat

On each heartbeat cycle, check the federation connection:

1. Run: `echo '{"intent":"heartbeat","target":"agent-city"}' | python3 -m mahaclaw.cli --wait 3`
2. If the response contains `"responded": true`, the federation is healthy. Reply HEARTBEAT_OK.
3. If `"responded": false` or the command fails, report: "Federation bridge: no response from agent-city"
4. Check `nadi_inbox.json` for any unread federation messages. If found, summarize them.
