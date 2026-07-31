## 2025-07-29 - Missing Security Headers
**Vulnerability:** The FastAPI backend lacked default security HTTP headers like X-Frame-Options, X-Content-Type-Options, Strict-Transport-Security, and Referrer-Policy.
**Learning:** Default FastAPI installations don't apply these out of the box, leaving the application open to clickjacking and MIME-sniffing.
**Prevention:** Apply a middleware in standard web application templates to enforce security headers across all responses.
