package risk.authorization.policy.deny.policy_0636

# Auto-generated policy 636 (Rego v1 syntax)
# Package: risk.authorization.policy.deny

# Metadata
metadata := {
    "policy_id": "0636",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0636_allowed if {
    input.user.role == "admin"
}
default policy_0636_allowed = false
policy_0636_allowed if {
    data.policies.risk.enabled
}
