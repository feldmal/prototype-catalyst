# Prototype Catalyst

Responsive static marketing website and early development workspace for a data automation and analytics consultancy. Prototype Catalyst is currently a working business name; the business entity has not yet been registered.

## Website

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

Local preview: `python -m http.server 8000 --directory public`.

## Website deployment and quote form

The marketing site is deployed through Cloudflare Workers Static Assets. The Worker handles `POST /api/quote`.

Configure these Worker variables in Cloudflare:
- `RESEND_API_KEY` — Resend API key (secret)
- `QUOTE_TO_EMAIL` — inbox receiving project inquiries
- `QUOTE_FROM_EMAIL` — sender address authorized by Resend

Keep secrets out of GitHub. The quote endpoint validates same-origin requests, JSON content type, payload size, required fields, email format, and allowed service selections. It includes a honeypot and a Cloudflare Workers rate-limit binding (3 submissions per minute per client IP). Turnstile server-side verification must be integrated and tested before relying on it as an active protection.

The current quote form collects contact and project inquiry details only; it does not accept customer files. Submissions are delivered by email using Resend. Do not invite customers to send confidential datasets, credentials, regulated personal information, or other sensitive records through the public form.

## Automation engine (development prototype)

The reusable Python automation engine is in `automation-engine/`. It currently provides:
- CSV/XLSX upload with a 25 MB limit
- A tracked job lifecycle (queued, processing, completed, failed)
- A sample `clean_table` workflow using Pandas
- Job status and output download endpoints
- Docker Compose local development

Run it with Docker Desktop:

```bash
cd automation-engine
docker compose up --build
```

Then open http://127.0.0.1:8000/docs.

**Important:** this engine is a local development prototype only. It has no customer authentication, tenant isolation, malware scanning, durable distributed queue, production object storage, or production deployment. Its API is bound to localhost in Docker Compose. Do not expose it publicly or process real customer/confidential data.

## Planned hybrid architecture

- Cloudflare: marketing site, DNS, edge protections, and customer-facing entry point.
- Python API and workers: file validation and customer-specific processing workflows.
- PostgreSQL: application metadata, customers, jobs, and usage records.
- Private object storage: source uploads and generated outputs.
- Metabase: hosted analytics and reporting, isolated by customer.

The platform should be modular: client-specific transformations become separate tested workflow modules rather than one-off changes to the API.

## Production readiness work remaining

1. Add authentication and enforce business/tenant ownership in every API and data access path.
2. Move job metadata to PostgreSQL and files to private object storage.
3. Replace in-process background tasks with a durable queue and separate worker process.
4. Add malware scanning, retention/deletion controls, audit events, quotas, and monitoring.
5. Add customer-specific workflow configuration and isolated execution.
6. Add and test Turnstile server-side verification on the quote endpoint.
7. Review customer data processing terms, retention policy, security controls, and separate service terms before accepting customer data.
8. Replace the temporary Workers URL with the final custom domain and update canonical URLs, social metadata, sitemap, and robots file.
9. Verify production sending domain configuration in Resend.

## Status

Marketing website and email inquiry endpoint are operational components. The automation engine is a local development prototype. Customer portal, customer file uploads, and managed data hosting are not yet operational.
