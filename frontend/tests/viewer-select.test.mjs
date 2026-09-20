import assert from "node:assert/strict";
import test from "node:test";

/**
 * Must match {@link shouldUseKitWebRtcAdapter} in lib/viewer/select.ts.
 * Kept here so Node can run the test without a TS loader.
 */
function shouldUseKitWebRtcAdapter(config) {
  return config.status === "available" && Boolean(config.signaling_url);
}

test("selects kit adapter when session is available with signaling URL", () => {
  assert.equal(
    shouldUseKitWebRtcAdapter({
      status: "available",
      signaling_url: "wss://127.0.0.1:49100",
    }),
    true,
  );
});

test("uses mock adapter path when offline or signaling URL missing", () => {
  assert.equal(
    shouldUseKitWebRtcAdapter({ status: "offline", signaling_url: null }),
    false,
  );
  assert.equal(
    shouldUseKitWebRtcAdapter({
      status: "available",
      signaling_url: null,
    }),
    false,
  );
});
