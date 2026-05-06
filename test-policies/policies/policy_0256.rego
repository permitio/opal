package security.authorization.policy.check.policy_0256

# Auto-generated policy 256 (Rego v1 syntax)
# Package: security.authorization.policy.check

# Metadata
metadata := {
    "policy_id": "0256",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0256_allowed = false
policy_0256_allowed if {
    input.user.role == "admin"
}
policy_0256_allowed if {
    data.policies.security.enabled
}
policy_0256_allowed if {
    input.user.active
    input.resource.public
}
