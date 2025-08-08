# APIM + MCP Security (OBO recommended)

This document explains how to secure the User → App (Frontend) → Backend → Agent (Semantic Kernel) → MCP Server path with Azure API Management (APIM) and Microsoft Entra ID using the OAuth 2.0 On‑Behalf‑Of (OBO) flow. This avoids Device Code flow and ensures the backend exchanges the user token for a downstream token to call MCP via APIM.

---

## High‑level flow (OBO)

1) User signs in from the Streamlit frontend using MSAL Authorization Code flow with PKCE and acquires an access token for the Backend API scope (audience = the backend App ID URI).
2) Frontend calls the backend and includes Authorization: Bearer <user_access_token_for_backend>.
3) Backend validates the token against Azure AD JWKS (audience and optional scope), then performs OBO to acquire a downstream access token for the MCP API (audience = the MCP App ID URI secured by APIM) using its confidential client credentials (secret or certificate).
4) The SK Agent attaches the OBO downstream token as `Authorization: Bearer <token>` when calling the MCP server through APIM using `MCPStreamableHttpPlugin` (SSE/HTTP).
5) APIM `validate-jwt` checks the incoming token and optionally forwards `Authorization` to the MCP upstream. It can also set headers like `X-Principal-Id` based on token claims.

---

## Components and files

- Frontend (Streamlit)
  - File: `agentic_ai/applications/frontend.py`
  - Auth helper: `agentic_ai/applications/msal_streamlit.py`
  - Behavior:
    - Signs in the user with MSAL (Authorization Code with PKCE) and requests a token for the Backend API scope (not the MCP API scope).
    - Sends Authorization to backend for chat, history, and reset endpoints.

- Backend (FastAPI)
  - File: `agentic_ai/applications/backend.py`
  - Behavior:
    - Validates JWT with Azure AD JWKS using PyJWT (PyJWKClient).
    - Audience must match the Backend API App ID URI; optional scope enforcement for the backend scope (e.g., `access_as_user`).
    - Performs OBO using MSAL Confidential Client to get a downstream token for the MCP API scope.
    - Propagates the downstream (MCP) token to the SK agent constructor.

- Semantic Kernel Agent (Single Agent)
  - File: `agentic_ai/agents/semantic_kernel/single_agent/chat_agent.py`
  - Behavior:
    - Accepts downstream (MCP) `access_token` from backend.
    - Adds `Authorization: Bearer <token>` to `MCPStreamableHttpPlugin` headers.

- MCP Server (FastMCP)
  - File: `agentic_ai/backend_services/mcp_service.py`
  - Behavior:
    - Exposes tools over HTTP/SSE (no direct auth), protected by APIM at the edge.

- APIM policy
  - File: `agentic_ai/applications/apim_inbound_policy.xml`
  - Behavior:
    - CORS for the frontend origin.
    - `validate-jwt` with tenant, audience (MCP API), and required scope.
    - Forwards `Authorization` downstream and sets `X-Principal-Id` claim.

---

## Azure AD app registrations

You need three app registrations in the same tenant:

1) Downstream API app (protects MCP via APIM)
   - Expose an API with an App ID URI: `api://<mcp-api-app-id>`.
   - Add a scope: `contoso.mcp.fullaccess`.

2) Backend API app (FastAPI)
   - Expose an API with App ID URI: `api://<backend-app-id>`.
   - Add a scope: `access_as_user` (or similar) for the frontend to call the backend.
   - Configure client credentials (secret or certificate). This app will perform OBO.
   - Grant API permissions to call the MCP API app (Application type: “Delegated permissions” for `contoso.mcp.fullaccess`) and grant admin consent.

3) Frontend public client (Streamlit)
   - Type: public client (desktop/native) or SPA, using Authorization Code with PKCE.
   - Add API permission to the Backend API scope (`api://<backend-app-id>/access_as_user`).
   - No secret required.

Note the following identifiers:
- Tenant ID: AAD_TENANT_ID
- Frontend Client ID: CLIENT_ID (public client)
- Backend App (API) ID: BACKEND_CLIENT_ID (confidential client)
- Backend API App ID URI (audience): BACKEND_API_AUDIENCE (e.g., `api://<backend-app-id>`)
- MCP API App ID URI (audience): MCP_API_AUDIENCE (e.g., `api://<mcp-api-app-id>`)
- Backend scope to request from the frontend: `api://<backend-app-id>/access_as_user`
- MCP downstream scope the backend requests with OBO: `api://<mcp-api-app-id>/contoso.mcp.fullaccess`

---

## APIM configuration

- Create (or update) an API that fronts your MCP server (FastMCP) upstream.
- Import the policy from `agentic_ai/applications/apim_inbound_policy.xml`.
  - Parameterize named values: `aad-tenant-id`, `mcp-app-id-uri`, `required-scope`.
  - Add your frontend origin(s) to the CORS list.
- Ensure a route points to your MCP SSE/HTTP endpoint (e.g., `/mcp` or `/sse`).
- If using subscription keys on the same API, either disable keys or handle them alongside JWT.

---

## Environment configuration

Application `.env` (in `agentic_ai/applications/`):

- AAD_TENANT_ID="<tenant-guid>"
- CLIENT_ID="<frontend-public-client-id>"                       # Frontend MSAL client id
- BACKEND_CLIENT_ID="<backend-app-client-id>"                  # Confidential client
- BACKEND_CLIENT_SECRET="<backend-app-client-secret>"          # Or configure certificate
- BACKEND_API_AUDIENCE="api://<backend-app-id>"                # What frontend tokens target
- MCP_API_AUDIENCE="api://<mcp-api-app-id>"                    # What OBO targets
- REQUIRED_SCOPE_BACKEND="access_as_user"                      # Enforced by backend
- REQUIRED_SCOPE_MCP="contoso.mcp.fullaccess"                  # Requested by backend via OBO
- BACKEND_URL="http://localhost:7000"
- MCP_SERVER_URI="https://<your-apim-gateway>/mcp/sse"         # Match your APIM route
- Azure OpenAI settings…
- AGENT_MODULE="agents.semantic_kernel.single_agent.chat_agent"

Streamlit secrets (`.streamlit/secrets.toml`):

- BACKEND_SCOPE = "api://<backend-app-id>/access_as_user"

MCP local (if running FastMCP locally):

- Start FastMCP (defaults to `http://localhost:8000`).
- Configure APIM to forward from a public path to this upstream.

---

## Quick start

1) Create the three Entra apps (MCP API, Backend API/confidential client, Frontend public client) and grant the frontend permission to the Backend API scope.
2) In the Backend app, add delegated permission to the MCP API scope and grant admin consent.
3) Configure APIM policy and backend route to your MCP upstream.
4) Fill in `.env` and Streamlit secrets with tenant, client ids, audiences, and scopes; add backend secret/cert.
5) Run the MCP service locally (or ensure your upstream is reachable).
6) Start backend (`uvicorn ...` or the VS Code task) and Streamlit frontend.
7) Sign in (interactive auth with PKCE), then chat. Verify APIM trace shows `validate-jwt` success and upstream calls.

---

## Troubleshooting

- 401 No bearer token: Frontend didn’t send Authorization; ensure you’re signed in and sending the Backend token.
- 401 Token invalid/audience: `BACKEND_API_AUDIENCE` mismatch; confirm the Backend App ID URI matches the token audience.
- 403 Insufficient backend scope: Ensure frontend requests `access_as_user` and backend enforces it.
- OBO failures (HTTP 400/500 from AAD):
  - AADSTS65001/650052: Consent required – grant admin consent on Backend app to call MCP API.
  - AADSTS50013/500011: Invalid resource or application – verify `MCP_API_AUDIENCE` and app IDs.
  - AADSTS700016/7000218: Invalid client/credential – check Backend client id/secret or certificate config.
- CORS preflight blocked: Add your frontend origin to APIM CORS policy and include OPTIONS in allowed methods.
- SSE connection issues (502/504): Confirm `MCP_SERVER_URI` targets the APIM route that maps to the SSE endpoint and that APIM timeout settings are sufficient.

---

## Notes

- This guide documents the SK single‑agent path with OBO. Other agent implementations can follow the same pattern as long as the backend accepts the user token, performs OBO for the MCP API, and the agent/plugin sets the Authorization header on MCP calls.
- Keep APIM policy and backend audience/scope settings in sync with your Entra app registration values.
- Prefer Authorization Code with PKCE for interactive clients; avoid Device Code flow unless there is no browser available and you fully understand the trade‑offs.
