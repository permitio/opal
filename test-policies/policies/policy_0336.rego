package access.enforcement.action.check.policy_0336

# Auto-generated policy 336 (Rego v1 syntax)
# Package: access.enforcement.action.check

# Metadata
metadata := {
    "policy_id": "0336",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0336_allowed if {
    data.policies.access.enabled
}
policy_0336_allowed if {
    input.user.role == "admin"
}
