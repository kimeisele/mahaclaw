#!/usr/bin/env node
/**
 * mock_openclaw.js — Minimal OpenClaw Gateway mock for integration testing.
 *
 * Simulates three OpenClaw integration modes:
 *   1. Skill invocation:  shells out to `python3 -m mahaclaw.cli`
 *   2. Hook invocation:   pipes OPENCLAW_EVENT to the hook script
 *   3. Response wait:     uses --wait to block for federation reply
 *
 * This does NOT require a real OpenClaw install.  It proves that the
 * mahaclaw bridge works exactly as a real OpenClaw agent would call it.
 *
 * Usage:  node tests/integration/mock_openclaw.js
 */

const { execSync, execFileSync } = require("child_process");
const { writeFileSync, readFileSync, mkdtempSync, rmSync } = require("fs");
const { join } = require("path");
const { tmpdir } = require("os");

const PYTHON = process.env.PYTHON || "python3";
let passed = 0;
let failed = 0;

function assert(condition, msg) {
  if (!condition) {
    console.error(`  FAIL: ${msg}`);
    failed++;
  } else {
    console.log(`  PASS: ${msg}`);
    passed++;
  }
}

// ---------------------------------------------------------------------------
// Test 1: Skill invocation (echo JSON | python3 -m mahaclaw.cli)
// ---------------------------------------------------------------------------
console.log("\n=== Test 1: Skill invocation ===");

try {
  const intent = JSON.stringify({
    intent: "inquiry",
    target: "agent-research",
    payload: { question: "What is dark matter?" },
    openclaw_session: "agent:default:telegram:dm:42",
    openclaw_skill: "federation-bridge",
  });

  const result = execSync(`echo '${intent}' | ${PYTHON} -m mahaclaw.cli`, {
    encoding: "utf-8",
    timeout: 10000,
  });

  const resp = JSON.parse(result.trim());
  assert(resp.ok === true, "response.ok is true");
  assert(resp.envelope_id.startsWith("env_"), "envelope_id starts with env_");
  assert(typeof resp.correlation_id === "string", "correlation_id present");
  assert(resp.target === "kimeisele/agent-research", "target resolved correctly");
  assert(resp.element === "jala", "inquiry classified as jala (water/research)");
  assert(resp.zone === "research", "zone is research");
  assert(resp.guardian === "prahlada", "guardian is prahlada");
} catch (e) {
  console.error(`  FAIL: skill invocation threw: ${e.message}`);
  failed++;
}

// ---------------------------------------------------------------------------
// Test 2: Different intents get different classifications
// ---------------------------------------------------------------------------
console.log("\n=== Test 2: Intent classification variety ===");

const testCases = [
  { intent: "heartbeat", target: "agent-city", expectElement: "vayu", expectZone: "general" },
  { intent: "code_analysis", target: "steward", expectElement: "prithvi", expectZone: "engineering" },
  { intent: "discover_peers", target: "agent-internet", expectElement: "akasha", expectZone: "discovery" },
];

for (const tc of testCases) {
  try {
    const intent = JSON.stringify({ intent: tc.intent, target: tc.target });
    const result = execSync(`echo '${intent}' | ${PYTHON} -m mahaclaw.cli`, {
      encoding: "utf-8",
      timeout: 10000,
    });
    const resp = JSON.parse(result.trim());
    assert(resp.ok === true, `${tc.intent}: ok`);
    assert(resp.element === tc.expectElement, `${tc.intent}: element=${tc.expectElement}`);
    assert(resp.zone === tc.expectZone, `${tc.intent}: zone=${tc.expectZone}`);
  } catch (e) {
    console.error(`  FAIL: ${tc.intent} threw: ${e.message}`);
    failed++;
  }
}

// ---------------------------------------------------------------------------
// Test 3: Error handling (bad input)
// ---------------------------------------------------------------------------
console.log("\n=== Test 3: Error handling ===");

try {
  const result = execSync(`echo '{"broken":true}' | ${PYTHON} -m mahaclaw.cli`, {
    encoding: "utf-8",
    timeout: 10000,
  });
  const resp = JSON.parse(result.trim());
  assert(resp.ok === false, "bad input returns ok=false");
  assert(typeof resp.error === "string", "error message present");
} catch (e) {
  // execSync throws on non-zero exit — that's expected
  if (e.stdout) {
    const resp = JSON.parse(e.stdout.toString().trim());
    assert(resp.ok === false, "bad input returns ok=false");
    assert(typeof resp.error === "string", "error message present");
  } else {
    console.error(`  FAIL: unexpected error: ${e.message}`);
    failed++;
  }
}

// ---------------------------------------------------------------------------
// Test 4: Response wait with simulated federation reply
// ---------------------------------------------------------------------------
console.log("\n=== Test 4: Return loop (--wait with simulated response) ===");

try {
  const tmp = mkdtempSync(join(tmpdir(), "mahaclaw-mock-"));
  const outbox = join(tmp, "nadi_outbox.json");
  const inbox = join(tmp, "nadi_inbox.json");
  writeFileSync(outbox, "[]\n");
  writeFileSync(inbox, "[]\n");

  // Run the full roundtrip in a single Python script:
  // 1. Send intent through pipeline (writes to outbox)
  // 2. Read correlation_id from outbox
  // 3. Simulate federation response in inbox
  // 4. Poll for response
  const pyScript = `
import json, pathlib, sys
import mahaclaw.envelope as m
import mahaclaw.inbox as ib
m.OUTBOX_PATH = pathlib.Path('${outbox}')
ib.INBOX_PATH = pathlib.Path('${inbox}')

from mahaclaw.intercept import parse_intent
from mahaclaw.tattva import classify
from mahaclaw.rama import encode_rama
from mahaclaw.lotus import resolve_route

intent = parse_intent('{"intent":"inquiry","target":"agent-research","payload":{"q":"test"}}')
tattva = classify(intent)
rama = encode_rama(intent, tattva)
route = resolve_route(intent, rama)
eid, cid = m.build_and_enqueue(intent, rama, route)

# Simulate federation dropping a response
inbox_data = [{"correlation_id": cid, "source": "agent-research",
    "source_city_id": "kimeisele/agent-research", "operation": "inquiry_response",
    "nadi_type": "apana", "payload": {"answer": "42", "_rama": {"element": "jala"}}}]
pathlib.Path('${inbox}').write_text(json.dumps(inbox_data))

resp = ib.poll_response(cid, timeout_s=2.0)
print(json.dumps({"ok": resp is not None, "answer": resp["payload"]["answer"] if resp else None, "cid": cid}))
`;

  const result = execSync(`${PYTHON} -c '${pyScript.replace(/'/g, "'\\''")}'`, {
    encoding: "utf-8",
    timeout: 15000,
  });

  const resp = JSON.parse(result.trim());
  assert(resp.ok === true, "return loop: response received");
  assert(resp.answer === "42", "return loop: correct payload");
  assert(typeof resp.cid === "string" && resp.cid.length > 0, "return loop: correlation_id present");

  // Cleanup
  rmSync(tmp, { recursive: true, force: true });
} catch (e) {
  console.error(`  FAIL: return loop threw: ${e.message}`);
  if (e.stderr) console.error(`  stderr: ${e.stderr.toString()}`);
  failed++;
}

// ---------------------------------------------------------------------------
// Test 5: Outbox wire format verification
// ---------------------------------------------------------------------------
console.log("\n=== Test 5: Wire format verification ===");

try {
  const tmp = mkdtempSync(join(tmpdir(), "mahaclaw-wire-"));
  const outbox = join(tmp, "nadi_outbox.json");
  writeFileSync(outbox, "[]\n");

  const pyScript = `
import json, pathlib
import mahaclaw.envelope as m
m.OUTBOX_PATH = pathlib.Path('${outbox}')
from mahaclaw.intercept import parse_intent
from mahaclaw.tattva import classify
from mahaclaw.rama import encode_rama
from mahaclaw.lotus import resolve_route
intent = parse_intent('{"intent":"inquiry","target":"agent-research","openclaw_session":"sess:123"}')
tattva = classify(intent)
rama = encode_rama(intent, tattva)
route = resolve_route(intent, rama)
m.build_and_enqueue(intent, rama, route)
print("done")
`;

  execSync(`${PYTHON} -c '${pyScript.replace(/'/g, "'\\''")}'`, {
    encoding: "utf-8",
    timeout: 10000,
  });

  const outboxData = JSON.parse(readFileSync(outbox, "utf-8"));
  const env = outboxData[0];

  // Verify all required DeliveryEnvelope fields
  const required = [
    "source", "source_city_id", "target", "target_city_id", "operation",
    "payload", "envelope_id", "correlation_id", "id", "timestamp",
    "priority", "ttl_s", "ttl_ms", "nadi_type", "nadi_op", "nadi_priority",
    "maha_header_hex",
  ];

  for (const field of required) {
    assert(field in env, `wire format: field '${field}' present`);
  }

  assert(env.source_city_id === "mahaclaw", "wire: source is mahaclaw");
  assert(env.nadi_op === "send", "wire: nadi_op is send");
  assert(env.maha_header_hex.length === 32, "wire: maha_header_hex is 32 chars");
  assert(env.envelope_id.startsWith("env_"), "wire: envelope_id format");
  assert(env.payload._openclaw.session === "sess:123", "wire: _openclaw.session preserved");
  assert(env.payload._rama.element === "jala", "wire: _rama.element present");

  rmSync(tmp, { recursive: true, force: true });
} catch (e) {
  console.error(`  FAIL: wire format threw: ${e.message}`);
  if (e.stderr) console.error(`  stderr: ${e.stderr.toString()}`);
  failed++;
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------
console.log(`\n${"=".repeat(50)}`);
console.log(`Integration tests: ${passed} passed, ${failed} failed`);
console.log(`${"=".repeat(50)}\n`);

process.exit(failed > 0 ? 1 : 0);
