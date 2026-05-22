# Security Review

Reviewed target: `proxy-setup/README.md` from `daily-office`.

## Summary

The original material was a convenience snippet for setting corporate proxy
environment variables. It was not malware-like and did not execute hidden code,
but it normalized several unsafe operational patterns:

- storing proxy credentials as plaintext in a PowerShell profile;
- leaking credentials into command output, logs, shell history, or screenshots;
- keeping proxy settings active longer than intended;
- recommending persistent Git proxy configuration with credentials;
- suggesting TLS verification disablement as a workaround;
- using empty strings instead of removing environment variables;
- omitting `no_proxy` defaults for loopback and internal traffic;
- not encoding usernames or passwords with special URL characters;
- not validating proxy hostnames or ports;
- implying Docker and WSL inherit the same settings when they often do not.

## Risk matrix

| Risk | Severity | Why it matters | Mitigation in this version |
| --- | --- | --- | --- |
| Plaintext credentials in profile | High | Profile files are easy to copy, commit, or back up accidentally | Runtime credential prompt; no secret in profile |
| Disabling TLS verification | High | Enables silent man-in-the-middle attacks | Removed from guidance; use approved corporate CA instead |
| Persistent global Git proxy with secret | High | Credentials remain after the session and may leak through config dumps | Avoided by default; cleanup commands documented only for stale entries |
| Environment variable inheritance | Medium | Child processes can read active proxy credentials | Session-scoped use, status masking, explicit clear command |
| Empty-string cleanup | Medium | Some tools treat empty variables inconsistently | Variables are restored or removed |
| Missing `no_proxy` | Medium | Local and internal traffic may be sent to proxy unnecessarily | Defaults include localhost, 127.0.0.1, and ::1 |
| Special characters in credentials | Medium | Proxy URL can break or be interpreted incorrectly | Username and password are URL-encoded |
| Uppercase proxy variables | Low/Medium | Needed by some tools, risky in CGI-like contexts | Optional with `-IncludeUppercase` |
| Host/port typos | Low | Misroutes traffic or creates confusing failures | Host and port validation |

## Trust boundary

This module only changes process-level environment variables for the current
PowerShell session. It does not install services, modify the registry, create
scheduled tasks, change system proxy settings, or rewrite tool-specific config.

No local proxy server is started. The corporate proxy remains the remote trust
anchor, and its behavior must be governed by company policy.

## Residual risk

No proxy helper can be absolutely safe once credentials must be exposed to
processes through environment variables. The best control is to keep activation
temporary, run only trusted commands while active, and clear the session after
use.

For stronger isolation, use a short-lived dedicated terminal window or a
company-approved authentication helper that does not require password-bearing
proxy URLs.
