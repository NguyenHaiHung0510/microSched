## 2023-10-27 - [Missing Default Security Headers in FastAPI]
**Vulnerability:** FastAPI applications do not include default security headers (like X-Frame-Options, X-Content-Type-Options, etc.), leaving the application open to common web vulnerabilities like clickjacking and MIME-type sniffing.
**Learning:** Default configurations in frameworks often prioritize ease of use over strict security, requiring explicit additions of security headers.
**Prevention:** Always add a global middleware to enforce standard security headers for all HTTP responses in FastAPI applications.