package risk.authorization.action.allow.policy_0221

# Auto-generated policy 221 (Rego v1 syntax)
# Package: risk.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0221",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0221_allowed if {
    input.user.active
    input.resource.public
}
policy_0221_allowed if {
    input.user.role == "admin"
}
policy_0221_allowed if {
    data.policies.risk.enabled
}
