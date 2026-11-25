const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status,
  headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", "x-content-type-options": "nosniff" }
});


const constantTimeSecretMatch = async (candidate, expected) => {
  if (!candidate || !expected) return false;
  const encoder = new TextEncoder();
  const [left, right] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(candidate)),
    crypto.subtle.digest("SHA-256", encoder.encode(expected))
  ]);
  const a = new Uint8Array(left);
  const b = new Uint8Array(right);
  let difference = 0;
  for (let i = 0; i < a.length; i++) difference |= a[i] ^ b[i];
  return difference === 0;
};

const automationProxy = async (request, env, url) => {
  const method = request.method;
  const path = url.pathname.slice("/api/automation".length);
  const origin = request.headers.get("Origin");
  if (origin && origin !== url.origin) return json({ error: "Request origin not allowed." }, 403);

  if (!env.PORTAL_ACCESS_CODE) {
    return json({ error: "Workspace access has not been configured." }, 503);
  }
  const suppliedCode = request.headers.get("X-Portal-Access-Code") || "";
  if (!(await constantTimeSecretMatch(suppliedCode, env.PORTAL_ACCESS_CODE))) {
    return json({ error: "Invalid workspace access code." }, 401);
  }
  if (!env.AUTOMATION_API_URL || !env.AUTOMATION_API_TOKEN) {
    return json({ error: "The automation service is not connected yet." }, 503);
  }

  const uuid = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}";
  const allowed =
    (method === "GET" && path === "/workflows") ||
    (method === "POST" && path === "/r2/uploads") ||
    (method === "POST" && new RegExp("^/r2/uploads/" + uuid + "/parts/[1-9][0-9]*/url$").test(path)) ||
    (method === "POST" && new RegExp("^/r2/uploads/" + uuid + "/complete$").test(path)) ||
    (method === "DELETE" && new RegExp("^/r2/uploads/" + uuid + "$").test(path)) ||
    (method === "GET" && new RegExp("^/jobs/" + uuid + "$").test(path)) ||
    (method === "GET" && new RegExp("^/jobs/" + uuid + "/download$").test(path));
  if (!allowed) return json({ error: "This automation API route is not available through the workspace." }, 404);

  let body;
  const headers = new Headers({ "Authorization": "Bearer " + env.AUTOMATION_API_TOKEN });
  if (method === "POST") {
    const declaredLength = Number(request.headers.get("Content-Length") || 0);
    if (declaredLength > 32768) return json({ error: "Request is too large." }, 413);
    if (!(request.headers.get("Content-Type") || "").toLowerCase().includes("application/json")) {
      return json({ error: "Unsupported request format." }, 415);
    }
    body = await request.text();
    if (new TextEncoder().encode(body).byteLength > 32768) return json({ error: "Request is too large." }, 413);
    try {
      const parsed = JSON.parse(body);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("invalid");
    } catch {
      return json({ error: "Invalid request body." }, 400);
    }
    headers.set("Content-Type", "application/json");
  }

  const base = env.AUTOMATION_API_URL.replace(/\/+$/, "");
  let backend;
  try {
    backend = new URL(base);
    if (backend.protocol !== "https:" &&
        backend.hostname !== "localhost" &&
        backend.hostname !== "127.0.0.1") {
      return json({ error: "The automation API must use HTTPS." }, 503);
    }
  } catch {
    return json({ error: "The automation API URL is invalid." }, 503);
  }

  let response;
  try {
    response = await fetch(base + path, {
      method,
      headers,
      body,
      redirect: "follow"
    });
  } catch {
    return json({ error: "Could not reach the automation service." }, 502);
  }

  const responseHeaders = new Headers();
  for (const name of ["content-type", "content-disposition"]) {
    const value = response.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  responseHeaders.set("cache-control", "no-store");
  return withSecurityHeaders(new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders
  }));
};

const clean = (value, max = 2000) =>
  String(value ?? "").replace(/[\x00-\x1F\x7F]/g, " ").replace(/\s+/g, " ").trim().slice(0, max);

const withSecurityHeaders = response => {
  const headers = new Headers(response.headers);
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  headers.set("X-Frame-Options", "DENY");
  headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/automation/")) {
      return automationProxy(request, env, url);
    }
    if (url.pathname === "/api/quote") {
      if (request.method !== "POST") return json({ error: "Method not allowed." }, 405);
      if (request.headers.get("Origin") !== url.origin) return json({ error: "Request origin not allowed." }, 403);
      if (!(request.headers.get("Content-Type") || "").toLowerCase().includes("application/json")) {
        return json({ error: "Unsupported request format." }, 415);
      }

      // Apply the per-IP limit to quote submissions before parsing or sending email.
      const clientIp = request.headers.get("CF-Connecting-IP") || "unknown";
      const { success: withinLimit } = await env.QUOTE_RATE_LIMITER.limit({ key: clientIp });
      if (!withinLimit) {
        return json({ error: "Too many submissions. Please wait a minute before trying again." }, 429);
      }

      const declaredLength = Number(request.headers.get("Content-Length") || 0);
      if (declaredLength > 16000) return json({ error: "Your inquiry is too large. Please shorten the details and try again." }, 413);

      let body;
      try {
        const raw = await request.text();
        if (new TextEncoder().encode(raw).byteLength > 16000) {
          return json({ error: "Your inquiry is too large. Please shorten the details and try again." }, 413);
        }
        body = JSON.parse(raw);
      } catch {
        return json({ error: "Please submit the form again." }, 400);
      }
      if (!body || typeof body !== "object" || Array.isArray(body)) return json({ error: "Please submit the form again." }, 400);
      if (clean(body.website, 200)) return json({ ok: true });

      const name = clean(body.name, 120);
      const business = clean(body.business, 160);
      const email = clean(body.email, 254);
      const service = clean(body.service, 120);
      const budget = clean(body.budget, 80);
      const timeline = clean(body.timeline, 80);
      const details = clean(body.details, 5000);

      if (!name || !email || !service || !details) return json({ error: "Please complete the required fields." }, 400);
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254) {
        return json({ error: "Please enter a valid email address." }, 400);
      }
      const allowedServices = ["Data automation", "Data visualization and analytics", "Both services", "Not sure yet"];
      if (!allowedServices.includes(service)) return json({ error: "Please select a valid service." }, 400);
      if (!env.RESEND_API_KEY || !env.QUOTE_TO_EMAIL || !env.QUOTE_FROM_EMAIL) {
        return json({ error: "The inquiry service is temporarily unavailable. Please try again later." }, 503);
      }

      const text = [
        "New Prototype Catalyst project inquiry", "",
        `Name: ${name}`,
        `Business: ${business || "Not provided"}`,
        `Email: ${email}`,
        `Service: ${service}`,
        `Budget: ${budget || "Not provided"}`,
        `Timeline: ${timeline || "Not provided"}`, "",
        "Project details:", details
      ].join("\n");

      try {
        const sent = await fetch("https://api.resend.com/emails", {
          method: "POST",
          headers: { "authorization": `Bearer ${env.RESEND_API_KEY}`, "content-type": "application/json" },
          body: JSON.stringify({
            from: env.QUOTE_FROM_EMAIL, to: [env.QUOTE_TO_EMAIL], reply_to: email,
            subject: `New project inquiry — ${name}`, text
          })
        });
        if (!sent.ok) return json({ error: "We couldn't send your inquiry just now. Please try again later." }, 502);
      } catch {
        return json({ error: "We couldn't reach the inquiry service just now. Please try again later." }, 502);
      }
      return json({ ok: true });
    }
    return withSecurityHeaders(await env.ASSETS.fetch(request));
  }
};
