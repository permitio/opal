package risk.authorization.user.allow.data.policy_0337

# Auto-generated policy 337 (Rego v1 syntax)
# Package: risk.authorization.user.allow.data

# Metadata
metadata := {
    "policy_id": "0337",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0337_allowed if {
    input.user.role == "admin"
}
policy_0337_allowed if {
    data.policies.risk.enabled
}
