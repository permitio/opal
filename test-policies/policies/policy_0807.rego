package security.authentication.user.allow.core.policy_0807

# Auto-generated policy 807 (Rego v1 syntax)
# Package: security.authentication.user.allow.core

# Metadata
metadata := {
    "policy_id": "0807",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0807_allowed = false
policy_0807_allowed if {
    data.policies.security.enabled
}
