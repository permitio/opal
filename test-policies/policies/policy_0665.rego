package risk.authentication.policy.check.core.policy_0665

# Auto-generated policy 665 (Rego v1 syntax)
# Package: risk.authentication.policy.check.core

# Metadata
metadata := {
    "policy_id": "0665",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0665_allowed if {
    input.user.active
    input.resource.public
}
policy_0665_allowed if {
    input.user.role == "admin"
}
