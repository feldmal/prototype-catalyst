# Prototype Catalyst — Website

Responsive static marketing website for a data automation and analytics consultancy. Prototype Catalyst is currently a working business name; the business entity has not yet been registered.

## Pages
- `public/index.html` — homepage
- `public/automation.html` — spreadsheet/file automation services
- `public/analytics.html` — data visualization and managed analytics
- `public/examples.html` — illustrative demonstrations using fictional data
- `public/about.html` — company approach
- `public/quote.html` — project inquiry form
- `public/privacy.html` — current website privacy notice
- `public/terms.html` — draft website terms
- `public/portal.html` — client workspace preview only; not a functional login
- `public/404.html` — not-found page
- `public/sitemap.xml` and `public/robots.txt` — search engine discovery

## Local preview
From the repository root, run `python -m http.server 8000 --directory public` and open http://localhost:8000.

## Cloudflare deployment
The repository includes `wrangler.jsonc` configured to serve static assets from `./public` using Workers Static Assets. The Worker handles `POST /api/quote`.

## Quote form configuration
Configure these Worker variables in Cloudflare:
- `RESEND_API_KEY` — Resend API key (secret)
- `QUOTE_TO_EMAIL` — inbox receiving project inquiries
- `QUOTE_FROM_EMAIL` — sender address authorized by Resend

Keep secrets out of GitHub. The recipient can be changed in Worker settings without changing form code.

The endpoint validates same-origin requests, JSON content type, payload size, required fields, email format, and allowed service selections. It includes a honeypot field and generic provider/network error handling. These are baseline protections, not a substitute for Cloudflare Turnstile and rate limiting before broad public promotion.

## Privacy and customer data
The current quote form collects contact and project inquiry details only; it does not accept file uploads. Submissions are delivered by email using Resend. Do not invite customers to send confidential datasets, credentials, regulated personal information, or other sensitive records through the public form.

The privacy notice describes the current website only. Before accepting customer data or offering managed hosting, add and review a customer data processing agreement, retention/deletion policy, security controls, and separate service terms.

## Search and accessibility
Marketing pages include canonical URLs and social metadata. `sitemap.xml` lists indexable marketing pages; the portal preview is excluded from indexing. Shared navigation includes keyboard focus support and a skip link.

## Planned application architecture
The next stage may include a Python API and background processing workers, business-scoped accounts, private object storage, customer-specific datasets, usage metering, and dashboard integration. Enforce tenant authorization on the server and in the data layer. Do not commit customer data, credentials, API keys, or secrets to this repository.

## Launch checklist
1. Confirm the business name and legal status before representing the business as an LLC.
2. Replace the temporary Workers URL with the final custom domain; update canonical URLs, Open Graph URLs, sitemap, and robots file.
3. Review privacy notice and website terms with a qualified professional.
4. Configure Cloudflare Turnstile and server-side verification, plus appropriate rate limiting, before broad public promotion.
5. Verify a production sending domain in Resend and update `QUOTE_FROM_EMAIL`.
6. Keep the client workspace clearly labeled as a preview until authentication, private storage, tenant isolation, and file-processing security are implemented and tested.

## Status
Marketing website and email inquiry endpoint. Customer portal, customer file uploads, and managed data hosting are not operational.
