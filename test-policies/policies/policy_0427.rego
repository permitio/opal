package security.authorization.resource.allow.policy_0427

# Auto-generated policy 427 (Rego v1 syntax)
# Package: security.authorization.resource.allow

# Metadata
metadata := {
    "policy_id": "0427",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0427_allowed = false
policy_0427_allowed if {
    data.policies.security.enabled
}
