/* Login and registration.
 *
 * On success the server sets an HttpOnly session cookie; nothing is stored client-side.
 */

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("auth-form");
  const errorNode = document.getElementById("form-error");
  const submit = document.getElementById("auth-submit");
  const isRegister = form.dataset.mode === "register";

  function showError(message) {
    errorNode.textContent = message;
    errorNode.hidden = false;
  }

  function firstFieldMessage(error) {
    if (!(error instanceof Api.ApiError)) return null;
    const keys = Object.keys(error.details);
    if (!keys.length) return null;
    const field = keys[0].replace(/^body\.?/, "");
    return `${field}: ${error.details[keys[0]]}`;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorNode.hidden = true;
    submit.disabled = true;

    const body = {
      email: form.email.value.trim(),
      password: form.password.value,
    };
    if (isRegister) {
      body.name = form.name.value.trim();
      const organization = form.organization_name.value.trim();
      if (organization) body.organization_name = organization;
    }

    try {
      await Api.post(isRegister ? "/api/auth/register" : "/api/auth/login", body);
      // The `next` parameter lets a protected page bounce the user back after login.
      const next = new URLSearchParams(window.location.search).get("next");
      window.location.href = next && next.startsWith("/") ? next : "/dashboard";
    } catch (error) {
      showError(firstFieldMessage(error) || error.message);
      submit.disabled = false;
    }
  });
});
