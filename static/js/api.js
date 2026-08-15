/* Thin wrapper over fetch for the BetterOps JSON API.
 *
 * Every endpoint returns the same error envelope, so error handling lives here once:
 *   { "error": { "code": "...", "message": "...", "details": {...} } }
 *
 * The session cookie is HttpOnly, so there is no token to attach — `credentials:
 * "same-origin"` is all that is needed.
 */

const Api = (() => {
  class ApiError extends Error {
    constructor(status, code, message, details) {
      super(message);
      this.status = status;
      this.code = code;
      this.details = details || {};
    }

    /** First field-level message, if the server sent one. */
    get firstDetail() {
      const keys = Object.keys(this.details);
      return keys.length ? `${keys[0]}: ${this.details[keys[0]]}` : null;
    }
  }

  async function request(method, path, body) {
    const options = {
      method,
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    };

    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }

    let response;
    try {
      response = await fetch(path, options);
    } catch (networkError) {
      throw new ApiError(0, "network_error", "Could not reach the server.", {});
    }

    if (response.status === 204) return null;

    let payload = null;
    try {
      payload = await response.json();
    } catch (parseError) {
      payload = null;
    }

    if (!response.ok) {
      const error = (payload && payload.error) || {};
      throw new ApiError(
        response.status,
        error.code || "error",
        error.message || `Request failed (${response.status}).`,
        error.details
      );
    }

    return payload;
  }

  return {
    ApiError,
    get: (path) => request("GET", path),
    post: (path, body) => request("POST", path, body),
    put: (path, body) => request("PUT", path, body),
    del: (path) => request("DELETE", path),
  };
})();
