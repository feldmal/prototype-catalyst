const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status,
  headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" }
});

const clean = (value, max = 2000) => String(value ?? "").trim().slice(0, max);

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/quote") {
      if (request.method !== "POST") return json({ error: "Method not allowed." }, 405);

      const origin = request.headers.get("Origin");
      if (origin && origin !== url.origin) return json({ error: "Request origin not allowed." }, 403);

      let body;
      try { body = await request.json(); }
      catch { return json({ error: "Please submit the form again." }, 400); }

      // Honeypot field: bots often fill hidden inputs that humans never see.
      if (clean(body.website, 200)) return json({ ok: true });

      const name = clean(body.name, 120);
      const business = clean(body.business, 160);
      const email = clean(body.email, 254);
      const service = clean(body.service, 120);
      const budget = clean(body.budget, 80);
      const timeline = clean(body.timeline, 80);
      const details = clean(body.details, 5000);

      if (!name || !email || !service || !details) {
        return json({ error: "Please complete the required fields." }, 400);
      }
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        return json({ error: "Please enter a valid email address." }, 400);
      }
      if (!env.RESEND_API_KEY || !env.QUOTE_TO_EMAIL || !env.QUOTE_FROM_EMAIL) {
        return json({ error: "The inquiry service is not configured yet. Please try again later." }, 503);
      }

      const text = [
        "New Prototype Catalyst project inquiry",
        "",
        `Name: ${name}`,
        `Business: ${business || "Not provided"}`,
        `Email: ${email}`,
        `Service: ${service}`,
        `Budget: ${budget || "Not provided"}`,
        `Timeline: ${timeline || "Not provided"}`,
        "",
        "Project details:",
        details
      ].join("\n");

      const sent = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          "authorization": `Bearer ${env.RESEND_API_KEY}`,
          "content-type": "application/json"
        },
        body: JSON.stringify({
          from: env.QUOTE_FROM_EMAIL,
          to: [env.QUOTE_TO_EMAIL],
          reply_to: email,
          subject: `New project inquiry — ${name}`,
          text
        })
      });

      if (!sent.ok) {
        // Do not expose provider response or customer details to the browser.
        return json({ error: "We couldn't send your inquiry just now. Please try again later." }, 502);
      }
      return json({ ok: true });
    }

    return env.ASSETS.fetch(request);
  }
};
