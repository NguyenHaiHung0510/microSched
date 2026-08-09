## 2025-07-29 - Missing Security Headers
**Vulnerability:** The FastAPI backend lacked default security HTTP headers like X-Frame-Options, X-Content-Type-Options, Strict-Transport-Security, and Referrer-Policy.
**Learning:** Default FastAPI installations don't apply these out of the box, leaving the application open to clickjacking and MIME-sniffing.
**Prevention:** Apply a middleware in standard web application templates to enforce security headers across all responses.

## 2025-08-09 - Missing Content-Security-Policy Header
**Vulnerability:** The backend application did not implement a Content-Security-Policy header.
**Learning:** A standard middleware handling security headers missed CSP, leaving the front-end more vulnerable to cross-site scripting (XSS).
**Prevention:** Always include a restrictive Content-Security-Policy when implementing security headers middleware.