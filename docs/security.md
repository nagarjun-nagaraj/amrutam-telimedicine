# Security Documentation

## Authentication & Authorization

**Password Security:**
- bcrypt hashing (cost factor 12)
- Strength requirements: 8+ chars, uppercase, lowercase, digit, special char
- Account lockout: 5 failed attempts → 30 min lock

**JWT Tokens:**
- Access token: 30 min expiry
- Refresh token: 7 days, stored as SHA-256 hash, rotated on use
- Payload: {user_id, role, email, expiry}

**MFA:**
- TOTP (Google Authenticator compatible)
- 30-second validity window

**RBAC:**
- Roles: patient, doctor, admin
- Guards on every protected endpoint
- Ownership checks (users access only their data)

## OWASP Top 10 Coverage

| Risk | Mitigation |
|------|-----------|
| A01: Broken Access Control | RBAC on all endpoints, ownership checks |
| A02: Cryptographic Failures | bcrypt, JWT HS256, TLS 1.2+ |
| A03: Injection | SQLAlchemy ORM only (parameterized queries) |
| A04: Insecure Design | Threat modeling, defense in depth |
| A05: Security Misconfiguration | Security headers, no debug in prod |
| A06: Vulnerable Components | Pinned versions, monthly updates |
| A07: Auth Failures | Account lockout, MFA, token rotation |
| A08: Software Integrity | CI/CD with tests, version control |
| A09: Logging Failures | Audit logs for all writes |
| A10: SSRF | No user-controlled URLs |

## Threat Scenarios

**1. Credential Stuffing**
- Attack: Use leaked passwords from other sites
- Mitigation: Account lockout, rate limiting (10/min), MFA

**2. JWT Token Theft**
- Attack: XSS steals token from browser
- Mitigation: Short expiry (30 min), token rotation

**3. SQL Injection**
- Attack: Malicious SQL in parameters
- Mitigation: ORM only, input validation

**4. Double Booking**
- Attack: Concurrent slot booking
- Mitigation: SELECT FOR UPDATE lock, unique constraints

**5. Payment Replay**
- Attack: Reuse captured payment request
- Mitigation: Idempotency keys, timestamp validation

## Data Protection

**Encryption:**
- At rest: PostgreSQL disk encryption (AES-256)
- In transit: TLS 1.2+
- Passwords: bcrypt (never plaintext)

**Audit Trail:**
Every sensitive action logged:
- User ID, action, resource, IP address, timestamp
- Success/failure status
- Old/new values for updates

## Rate Limiting

| Endpoint | Limit |
|----------|-------|
| POST /auth/login | 10/min per IP |
| POST /auth/register | 5/min per IP |
| All others | 60/min per IP |