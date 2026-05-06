package security.authentication.resource.check.policy_0188

# Auto-generated policy 188 (Rego v1 syntax)
# Package: security.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0188",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0188_allowed if {
    data.policies.security.enabled
}
default policy_0188_allowed = false
