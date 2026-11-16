# Prototype Catalyst — Website starter

A responsive static marketing website for a data automation and analytics consultancy.

## Pages
- `public/index.html` — homepage
- `public/automation.html` — spreadsheet/file automation services
- `public/analytics.html` — data visualization and managed analytics
- `public/examples.html` — illustrative demonstrations using fictional data
- `public/about.html` — company approach
- `public/quote.html` — request-a-quote form prototype
- `public/portal.html` — client portal placeholder (not a functional login)
- `public/404.html` — not-found page

## Local preview
From the repository root, run `python -m http.server 8000 --directory public` and open http://localhost:8000.

## Cloudflare deployment
The repository includes `wrangler.jsonc` configured to serve static assets from `./public` using Workers Static Assets.

In Cloudflare, create a Worker connected to this GitHub repository and the `main` branch. Use the repository root as the project root, leave the build command blank, and set the deploy command to `npx wrangler deploy` (or use Cloudflare's default Wrangler deploy command).

## Before public launch
1. Replace the working company name if needed.
2. Configure the quote form Worker secrets: RESEND_API_KEY, QUOTE_TO_EMAIL, and QUOTE_FROM_EMAIL. The endpoint validates submissions and sends inquiries through Resend. Keep secrets out of GitHub.
3. Add real contact details and reviewed privacy/terms pages.
4. Review service copy and sample figures. Demonstrations use fictional data.
5. The client portal is a placeholder. It is not an operational login.

## Quote form configuration

The quote form posts to `/api/quote`, handled by `src/index.js`. Configure these Worker secrets in Cloudflare:
- `RESEND_API_KEY` — Resend API key (secret)
- `QUOTE_TO_EMAIL` — inbox receiving project inquiries
- `QUOTE_FROM_EMAIL` — verified sender address/domain in Resend

The recipient can be changed by updating `QUOTE_TO_EMAIL` in Worker settings; no form code changes are needed. Verify a sending domain in Resend before public launch. Do not commit API keys or secrets to GitHub.

## Planned application architecture
The next stage is a Python API and background processing workers, business-scoped accounts, private object storage, customer-specific datasets, usage metering, and dashboard integration. Enforce tenant authorization on the server and in the data layer. Do not commit customer data, credentials, API keys, or secrets to this repository.

## Status
Early development — marketing frontend only.
