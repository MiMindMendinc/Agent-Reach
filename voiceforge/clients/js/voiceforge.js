/**
 * Small JavaScript client for a running VoiceForge server.
 *
 * Works in browsers and in Node 18+ (anything with a global fetch).
 *
 *   import { VoiceForge } from "./voiceforge.js";
 *   const vf = new VoiceForge();                 // http://localhost:8000
 *   const wav = await vf.speak("Hello there");   // Blob (audio/wav)
 *   const url = URL.createObjectURL(wav);
 *
 * The timeout covers the whole request, including reading the response body.
 */

export const DEFAULT_URL = "http://localhost:8000";

export class VoiceForgeError extends Error {
  /**
   * @param {string} message
   * @param {number | null} status HTTP status, or null if no response arrived
   */
  constructor(message, status = null) {
    super(message);
    this.name = "VoiceForgeError";
    this.status = status;
  }
}

export class VoiceForge {
  /**
   * @param {object} [options]
   * @param {string} [options.baseUrl=DEFAULT_URL]
   * @param {number} [options.timeoutMs=120000] limit for the whole request
   */
  constructor({ baseUrl = DEFAULT_URL, timeoutMs = 120000 } = {}) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.timeoutMs = timeoutMs;
  }

  /**
   * Send a request and read its body with `readBody`, all under one timeout.
   * @template T
   * @param {string} path
   * @param {RequestInit} init
   * @param {(response: Response) => Promise<T>} readBody
   * @returns {Promise<T>}
   */
  async #request(path, init, readBody) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    const timedOut = () => controller.signal.aborted;

    try {
      let response;
      try {
        response = await fetch(`${this.baseUrl}${path}`, { ...init, signal: controller.signal });
      } catch (err) {
        const reason = timedOut() ? `no response within ${this.timeoutMs} ms` : err.message;
        throw new VoiceForgeError(`Could not reach VoiceForge at ${this.baseUrl}: ${reason}`);
      }

      if (!response.ok) {
        let message = `HTTP ${response.status}`;
        try {
          const body = await response.json();
          if (body && body.error) message = body.error;
        } catch (_) {
          /* body was not JSON, or timed out; keep the status message */
        }
        throw new VoiceForgeError(message, response.status);
      }

      try {
        return await readBody(response);
      } catch (err) {
        const reason = timedOut()
          ? `the response did not finish within ${this.timeoutMs} ms`
          : err.message;
        throw new VoiceForgeError(`Failed to read the VoiceForge response: ${reason}`, response.status);
      }
    } finally {
      clearTimeout(timer);
    }
  }

  /** Server status, including whether the speech model is loaded. */
  async health() {
    return this.#request("/health", {}, (response) => response.json());
  }

  /** Available voice ids, such as "af_bella". */
  async voices() {
    const data = await this.#request("/voices", {}, (response) => response.json());
    return data.voices.map((voice) => voice.id);
  }

  /**
   * Synthesize speech.
   * @param {string} text
   * @param {object} [options]
   * @param {string} [options.voice]
   * @param {number} [options.speed=1.0] between 0.5 and 2.0
   * @returns {Promise<Blob>} WAV audio
   */
  async speak(text, { voice, speed = 1.0 } = {}) {
    const payload = { text, speed };
    if (voice !== undefined) payload.voice = voice;
    return this.#request(
      "/speak",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      (response) => response.blob(),
    );
  }
}
