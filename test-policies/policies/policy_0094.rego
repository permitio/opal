package security.enforcement.resource.allow.policy_0094

# Auto-generated policy 94 (Rego v1 syntax)
# Package: security.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0094",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0094_allowed if {
    data.policies.security.enabled
}
default policy_0094_allowed = false
