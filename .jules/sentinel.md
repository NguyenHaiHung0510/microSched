## 2025-07-28 - Add Security Headers Middleware
**Vulnerability:** The FastAPI application was missing standard security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security`).
**Learning:** These headers provide essential defense-in-depth protections against MIME sniffing, clickjacking, and man-in-the-middle attacks. Their absence is a common oversight in fast-paced API development.
**Prevention:** Implement a standard security headers middleware early in the application bootstrap process.
