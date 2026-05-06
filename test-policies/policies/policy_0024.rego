package security.enforcement.context.verify.policy_0024

# Auto-generated policy 24 (Rego v1 syntax)
# Package: security.enforcement.context.verify

# Metadata
metadata := {
    "policy_id": "0024",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0024_allowed if {
    input.user.role == "admin"
}
policy_0024_allowed if {
    data.policies.security.enabled
}
