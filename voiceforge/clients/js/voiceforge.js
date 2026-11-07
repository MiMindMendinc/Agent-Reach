/**
 * Small JavaScript client for a running VoiceForge server.
 *
 * Works in browsers and in Node 18+ (anything with a global fetch).
 *
 *   import { VoiceForge } from "./voiceforge.js";
 *   const vf = new VoiceForge();                 // http://localhost:8000
 *   const wav = await vf.speak("Hello there");   // Blob (audio/wav)
 *   const url = URL.createObjectURL(wav);
 */

export const DEFAULT_URL = "http://localhost:8000";

export class VoiceForgeError extends Error {
  /**
   * @param {string} message
   * @param {number | null} status HTTP status, or null if the server was unreachable
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
   * @param {number} [options.timeoutMs=120000]
   */
  constructor({ baseUrl = DEFAULT_URL, timeoutMs = 120000 } = {}) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.timeoutMs = timeoutMs;
  }

  async #request(path, init = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    let response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, { ...init, signal: controller.signal });
    } catch (err) {
      const reason = err.name === "AbortError" ? "the request timed out" : err.message;
      throw new VoiceForgeError(`Could not reach VoiceForge at ${this.baseUrl}: ${reason}`);
    } finally {
      clearTimeout(timer);
    }

    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const body = await response.json();
        if (body && body.error) message = body.error;
      } catch (_) {
        /* body was not JSON; keep the status message */
      }
      throw new VoiceForgeError(message, response.status);
    }
    return response;
  }

  /** Server status, including whether the speech model is loaded. */
  async health() {
    const response = await this.#request("/health");
    return response.json();
  }

  /** Available voice ids, such as "af_bella". */
  async voices() {
    const response = await this.#request("/voices");
    const data = await response.json();
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
    const response = await this.#request("/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return response.blob();
  }
}
