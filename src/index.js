const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status,
  headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", "x-content-type-options": "nosniff" }
});

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
