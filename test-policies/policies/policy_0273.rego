package security.authentication.user.validate.policy_0273

# Auto-generated policy 273 (Rego v1 syntax)
# Package: security.authentication.user.validate

# Metadata
metadata := {
    "policy_id": "0273",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0273_allowed = false
policy_0273_allowed if {
    data.policies.security.enabled
}
policy_0273_allowed if {
    input.user.role == "admin"
}
