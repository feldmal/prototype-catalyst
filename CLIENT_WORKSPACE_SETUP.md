# Client workspace test setup

The workspace UI is in \`public/portal.html\` and uses the same-site Worker proxy in \`src/index.js\`. The browser never receives the automation API bearer token.

## Configure the Worker

Set these values for local development or the deployed Worker:

- \`AUTOMATION_API_URL\`: base URL of the FastAPI automation service (for local Wrangler development, typically \`http://127.0.0.1:8000\`; for deployment, a reachable HTTPS API URL).
- \`AUTOMATION_API_TOKEN\`: the FastAPI \`R2_UPLOAD_API_TOKEN\`.
- \`PORTAL_ACCESS_CODE\`: a separate access code that testers enter on the workspace page.

Set secrets with Wrangler (do not put their values in source files):

\`\`\`powershell
npx wrangler secret put AUTOMATION_API_TOKEN
npx wrangler secret put PORTAL_ACCESS_CODE
\`\`\`

Set \`AUTOMATION_API_URL\` as a Worker variable in the Cloudflare dashboard or local \`.dev.vars\`. Do not commit \`.dev.vars\`.

For local testing, run the FastAPI service on port 8000 and start Wrangler from the repository root. A deployed Cloudflare Worker cannot reach your computer's \`127.0.0.1\`; the automation API must be deployed to a reachable HTTPS endpoint before the deployed site can use it.

## Configure R2 bucket CORS

The browser uploads each file part directly to its presigned R2 URL. In the R2 bucket CORS policy, allow:

- Allowed origin: the exact site origin used for testing (for example, your local Wrangler origin and/or the deployed site origin).
- Allowed method: \`PUT\`.
- Allowed headers: \`*\` or the headers required by your signed upload.
- Expose headers: \`ETag\`.

The browser needs to read each part's \`ETag\` to complete the multipart upload.

## Test flow

1. Open \`/portal.html\`.
2. Enter the configured portal access code.
3. Select a single-file workflow and a CSV or XLSX file.
4. Run the workflow, wait for the status to complete, and download the result.

Only single-file workflows are shown because the current R2 multipart submission API supports one input file per job.

## Before inviting customers

This is a limited test workspace, not a production account system. The shared access code does not provide individual user identities, per-business access control, or customer-specific job history. Use non-sensitive sample files until those protections and data-retention controls are implemented and reviewed.
