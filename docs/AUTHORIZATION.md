# Authentication and authorization

## Architecture

FDR Nexus uses server-side opaque sessions. Login generates a cryptographically
random session value and CSRF value. Only SHA-256 hashes of those values are
stored in `auth_sessions`; the session value is sent in an HttpOnly,
SameSite cookie and expires according to `SESSION_TTL_MINUTES`. The CSRF value
is readable by the same-origin frontend and must be sent as `X-CSRF-Token` on
state-changing requests. `AUTH_COOKIE_SECURE=true` is required when serving
over HTTPS.

Passwords are stored as PBKDF2-HMAC-SHA256 records with a per-password random
salt and 600,000 iterations. Login errors do not reveal whether a username
exists. Logout revokes the server-side session.

## Permission matrix

| Capability | Administrator | Institution user | Reviewing officer | Scope |
|---|---:|---:|---:|---|
| Dashboard, institutions, FDR read access | Yes | Yes | Yes | Institution users/officers see assigned institutions only |
| Register institution | Yes | No | No | Global administrator operation |
| Submit FDR | Yes | Yes | No | Institution users only for assigned institutions |
| Preview/commit imports | Yes | No | No | Imports are global and restricted to administrators |
| Review FDR | Yes | No | Yes | Assigned institutions for officers |
| Scan/update discrepancies | Yes | No | Yes | Assigned institutions for officers |
| Create release request | Yes | Yes | No | Institution users only for assigned FDRs |
| Decide release request | Yes | No | Yes | Assigned institutions for officers |
| Export FDR data | Yes | No | Yes | Assigned institutions for officers |
| View audit log | Yes | No | Yes | Current prototype exposes the administrative audit view to officers |
| Manage users and role assignments | Yes | No | No | Administrator only |

User and officer accounts have explicit `user_institutions` assignments.
Administrators have global scope. An institution user cannot change a URL or
payload institution ID to cross that boundary. The authenticated user, not a
request body or header, supplies audit actor identity.

## Bootstrap and migration

`Base.metadata.create_all` creates new authentication tables for an empty
database. The startup compatibility migration adds authentication foreign-key
columns to an existing SQLite database without dropping existing tables or
records. Set both bootstrap environment variables before first startup to
create the initial administrator; there is no universal default password.
