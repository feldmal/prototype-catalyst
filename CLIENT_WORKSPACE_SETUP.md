# Client workspace test setup

The workspace UI is in \`public/portal.html\` and uses the same-site Worker proxy in \`src/index.js\`. The browser never receives the automation API bearer token.

## Local development

1. Copy \`.dev.vars.example\` to \`.dev.vars\` in the repository root.
2. Put local test values in \`.dev.vars\` (this file is ignored by Git).
3. Run the FastAPI automation service on port 8000.
4. Start Wrangler from the repository root and open the local \`/portal.html\`.

For local Wrangler development, \`AUTOMATION_API_URL\` is typically \`http://127.0.0.1:8000\`.

## Configure the deployed Worker

Set the non-secret \`AUTOMATION_API_URL\` Worker variable in the Cloudflare dashboard. It must be a reachable HTTPS base URL; a deployed Cloudflare Worker cannot reach your computer's \`127.0.0.1\`.

Set these as Worker secrets using Wrangler:

\`\`\`powershell
npx wrangler secret put AUTOMATION_API_TOKEN
npx wrangler secret put PORTAL_ACCESS_CODE
\`\`\`

\`AUTOMATION_API_TOKEN\` must match the FastAPI \`R2_UPLOAD_API_TOKEN\`. Use a separate access code for \`PORTAL_ACCESS_CODE\`. Never commit secret values or place the backend bearer token in browser code.

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
3. Select Clean Table or Validate Data and a CSV or XLSX file.
4. For validation, optionally enter required, date, and numeric columns.
5. Run the workflow, wait for completion, and download the result.

Only these two workflows are shown because they are ready for the current single-file upload interface. Multi-file Combine Files and configurable Transform/Aggregate workflows need their own UI controls before they should be offered here.

## Before inviting customers

This is a limited test workspace, not a production account system. The shared access code does not provide individual user identities, per-business access control, or customer-specific job history. Use non-sensitive sample files until those protections and data-retention controls are implemented and reviewed.
