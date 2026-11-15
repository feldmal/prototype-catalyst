# Prototype Catalyst — Website starter

A responsive, dependency-free static website for a data automation and analytics consultancy.

## Pages
- `index.html` — public homepage
- `automation.html` — spreadsheet/file automation services
- `analytics.html` — data visualization and managed analytics
- `examples.html` — illustrative demonstrations using fictional data
- `about.html` — company approach
- `quote.html` — request-a-quote form
- `portal.html` — client portal placeholder (not a functional login)

## Local preview
Run `python -m http.server 8000` from the project directory and open http://localhost:8000.

## Cloudflare
The repository includes `wrangler.jsonc` for deployment as a static site using Cloudflare Workers Static Assets. Connect this GitHub repository to a Worker in the Cloudflare dashboard and use the repository root as the static asset directory. The current site has no build step.

## Before public launch
1. Replace the working company name if needed.
2. Configure a real quote-request endpoint. The current form does not transmit or store submissions until connected to a form service or backend.
3. Add real contact details and reviewed privacy/terms pages.
4. Review service copy and sample figures. Demonstrations use fictional data.
5. The portal is only a placeholder. Do not present it as an operational login.

## Planned application architecture
The next stage is a Python API and background processing workers, business-scoped accounts, private object storage, customer-specific datasets, usage metering, and dashboard integration. Enforce tenant authorization on the server and in the data layer. Do not commit customer data, credentials, API keys, or secrets to this repository.

## Status
Early development — marketing frontend only.
