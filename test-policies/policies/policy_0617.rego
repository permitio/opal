package security.authorization.user.verify.utils.policy_0617

# Auto-generated policy 617 (Rego v1 syntax)
# Package: security.authorization.user.verify.utils

# Metadata
metadata := {
    "policy_id": "0617",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0617_allowed if {
    data.policies.security.enabled
}
policy_0617_allowed if {
    input.user.role == "admin"
}
default policy_0617_allowed = false
policy_0617_allowed if {
    input.user.active
    input.resource.public
}
