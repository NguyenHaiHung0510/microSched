## 2024-05-24 - [Security Enhancement]
**Vulnerability:** Missing defense-in-depth security headers
**Learning:** Adding a global FastAPI middleware can easily set security headers across all endpoints, protecting against common vulnerabilities like clickjacking and MIME-type sniffing.
**Prevention:** Always consider implementing basic security headers (X-Frame-Options, X-Content-Type-Options, HSTS) in new projects.
