// Tests for the JavaScript client. Run with: node --test clients/js/
// Uses a small stub HTTP server, so no VoiceForge server or model is needed.

import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";

import { VoiceForge, VoiceForgeError } from "./voiceforge.js";

const WAV_BYTES = Buffer.from("RIFF\x24\x00\x00\x00WAVEfmt ", "binary");
let server;
let baseUrl;
const openResponses = new Set();

before(async () => {
  server = http.createServer((req, res) => {
    const url = new URL(req.url, "http://localhost");
    if (url.pathname === "/health") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ status: "ok", model_loaded: true }));
    } else if (url.pathname === "/voices") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ default: "af_bella", voices: [{ id: "af_bella" }, { id: "bm_george" }] }));
    } else if (url.pathname === "/speak") {
      let body = "";
      req.on("data", (chunk) => (body += chunk));
      req.on("end", () => {
        const payload = JSON.parse(body);
        if (!payload.text) {
          res.writeHead(400, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: "Text is required." }));
          return;
        }
        res.writeHead(200, { "Content-Type": "audio/wav" });
        res.end(WAV_BYTES);
      });
    } else if (url.pathname.startsWith("/slow-headers/")) {
      openResponses.add(res); // never answers
    } else if (url.pathname.startsWith("/slow-body/")) {
      // Headers arrive at once; the body never finishes.
      res.writeHead(200, { "Content-Type": "application/json" });
      res.write('{"status":');
      openResponses.add(res);
    } else {
      res.writeHead(404, { "Content-Type": "text/plain" });
      res.end("not found");
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  baseUrl = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
  for (const res of openResponses) res.destroy();
  server.closeAllConnections?.();
  await new Promise((resolve) => server.close(resolve));
});

/** A client whose requests go to a stalled route on the stub server. */
function stalledClient(route, timeoutMs) {
  return new VoiceForge({ baseUrl: `${baseUrl}/${route}`, timeoutMs });
}

test("speak returns a WAV blob", async () => {
  const vf = new VoiceForge({ baseUrl: `${baseUrl}/` });
  const blob = await vf.speak("Hello", { voice: "af_bella", speed: 1.2 });
  assert.equal(blob.type, "audio/wav");
  assert.equal(blob.size, WAV_BYTES.length);
});

test("voices returns ids and health returns status", async () => {
  const vf = new VoiceForge({ baseUrl });
  assert.deepEqual(await vf.voices(), ["af_bella", "bm_george"]);
  assert.equal((await vf.health()).status, "ok");
});

test("server errors raise VoiceForgeError with the server message and status", async () => {
  const vf = new VoiceForge({ baseUrl });
  await assert.rejects(vf.speak(""), (err) => {
    assert.ok(err instanceof VoiceForgeError);
    assert.equal(err.status, 400);
    assert.equal(err.message, "Text is required.");
    return true;
  });
});

test("unreachable server raises VoiceForgeError without a status", async () => {
  const vf = new VoiceForge({ baseUrl: "http://127.0.0.1:9", timeoutMs: 2000 });
  await assert.rejects(vf.health(), (err) => {
    assert.ok(err instanceof VoiceForgeError);
    assert.equal(err.status, null);
    assert.match(err.message, /Could not reach VoiceForge/);
    return true;
  });
});

test("timeout applies while waiting for headers", { timeout: 5000 }, async () => {
  const vf = stalledClient("slow-headers", 300);
  const started = Date.now();
  await assert.rejects(vf.health(), (err) => {
    assert.ok(err instanceof VoiceForgeError);
    assert.match(err.message, /no response within 300 ms/);
    return true;
  });
  assert.ok(Date.now() - started < 5000);
});

test("timeout still applies while the body is being read", { timeout: 5000 }, async () => {
  const vf = stalledClient("slow-body", 300);
  const started = Date.now();
  await assert.rejects(vf.health(), (err) => {
    assert.ok(err instanceof VoiceForgeError);
    assert.match(err.message, /did not finish within 300 ms/);
    return true;
  });
  assert.ok(Date.now() - started < 5000);
});
