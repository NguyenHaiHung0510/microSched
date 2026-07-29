## 2026-07-29 - [Missing Security Headers]
**Vulnerability:** The application was missing basic security headers (e.g. `X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security`), leaving it potentially vulnerable to clickjacking and mime-type sniffing, and not enforcing HTTPS.
**Learning:** Security headers are easily overlooked but represent a foundational defense-in-depth measure that should be implemented at the global application level.
**Prevention:** A global HTTP middleware was added in FastAPI (`backend/app/main.py`) to automatically apply `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and `Strict-Transport-Security` headers to all responses.
