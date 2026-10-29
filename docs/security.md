# GateForge Security Model & Threat Assessment

GateForge is architected following zero-trust principles and defense-in-depth methodologies.

---

## 1. Cryptographic Key Management & Storage

### Plaintext Token Format
API keys follow the industry-standard prefixed format:
```
gfg_live_7a9f4c2e1b8d6a0f3e5c9b2a1d4e7f0a8c2e1b8d
^^^^^^^^ ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 Prefix  High-entropy cryptographically random bytes (secrets.token_urlsafe)
```

### One-Way Deterministic SHA-256 Hashing
- **Zero Plaintext Storage:** Plaintext tokens are returned strictly once during initial key creation. Neither the database nor Redis cache stores plaintext secrets.
- **Deterministic Digest:** GateForge computes `SHA-256(raw_key)` to perform constant-time primary key lookups without exposing credentials to SQL injection or memory dump extraction.
- **Masked Previews:** Dashboards and list endpoints expose only `gfg_live_7a9f••••••••••••8c2e`, providing safe visual identification while preventing token exfiltration.

---

## 2. Enterprise IP Allowlisting & CIDR Filtering

For sensitive production workloads, API keys can be bound to corporate CIDR blocks or fixed egress IPs:
- Supports IPv4 (`192.168.1.0/24`, `10.0.0.5`) and IPv6 (`2001:db8::/32`, `::1`).
- Evaluates `X-Forwarded-For` proxy chains with proper multi-hop parsing, falling back to connection socket IP.
- Enforced at the gateway edge before processing route handlers. Mismatched IPs immediately receive an RFC-compliant `403 Forbidden` response.

---

## 3. Threat Model & Mitigation Strategies

| Threat Vector | Attack Mechanism | GateForge Mitigation |
| :--- | :--- | :--- |
| **Database Compromise** | Attacker dumps SQL database tables | All stored keys are SHA-256 digests; raw keys cannot be recovered |
| **Timing Attacks** | Measuring response times on key validation | Constant-time hash computation & uniform lookup paths |
| **Cache Stampede / Dog-piling** | Thousands of concurrent requests hit expired key | Anti-stampede random jitter (0–30s) decorrelating cache expiries |
| **Distributed DDoS / Abuse** | Bursting high request volumes across nodes | Atomic sliding-window rate limiting executed via Redis Lua |
| **Cascading Downstream Failure** | Redis or Database latency spikes | Circuit Breaker pattern with immediate fail-fast & graceful degradation |
| **Spoofed Client IP** | Attacker forging `X-Forwarded-For` | Configurable proxy trust boundaries & multi-hop extraction |

---

## 4. Operational Security Best Practices

1. **Rotate Keys Regularly:** GateForge provides instant key revocation (`PATCH /api/v1/keys/{id}/revoke`), which purges the Redis edge cache in real time.
2. **Restrict Key Scopes:** Always adhere to the principle of least privilege by scoping keys (e.g., `read:reports` instead of global access).
3. **Bind IP Allowlist:** Bind production keys to your VPC NAT gateway or corporate static IP addresses.
