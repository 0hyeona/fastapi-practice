# GitHub OAuth frontend integration

These are prepared changes for the existing moeum frontend; the original frontend folder has not been edited.

From the moeum frontend directory, run:

```powershell
git apply --check "C:/Users/ouskx/IdeaProjects/fastapi-practice/fastapi-practice/frontend-integration/github-oauth/frontend.patch"
git apply "C:/Users/ouskx/IdeaProjects/fastapi-practice/fastapi-practice/frontend-integration/github-oauth/frontend.patch"
npm run build
```

Alternatively, copy the two files under src into the corresponding frontend paths after reviewing the changes.

Flow: GitHub → backend callback → React /auth/github/callback#login_code=... →
POST /api/auth/github/exchange → save existing moeum.access_token sessionStorage key →
GET /api/auth/me → /dashboard.

The frontend never sends GitHub code/state to the backend callback again. The actual login token
is never placed in a URL. The opaque handoff code expires after 60 seconds, is stored as a hash,
cannot authenticate as a Bearer token, and is consumed atomically on exchange. The callback
clears the URL immediately. Do not add third-party analytics to the callback page.

Backend environment (Render uses its own environment settings):

```dotenv
GITHUB_REDIRECT_URI=https://fastapi-practice-jwse.onrender.com/api/auth/github/callback
FRONTEND_AUTH_CALLBACK_URL=http://127.0.0.1:5173/auth/github/callback
FRONTEND_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
```

Match localhost/127.0.0.1 to the frontend browser address. Production frontend callback must use HTTPS.
Deploy the frontend changes together with the backend. Missing callback configuration now returns
503 before starting OAuth, rather than returning a successful login JSON to the browser.
No schema migration is required: pending handoffs reuse auth_sessions with a non-Bearer hash
namespace and a short expiry. Existing user creation and GitHub account lookup are unchanged.
Tokens are returned only by the exchange API with Cache-Control: no-store. Use HTTPS for the API.

No live GitHub authorization, Render deployment, or write to the original frontend was performed here.
