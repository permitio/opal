package audit.authorization.policy.deny.policy_0391

# Auto-generated policy 391 (Rego v1 syntax)
# Package: audit.authorization.policy.deny

# Metadata
metadata := {
    "policy_id": "0391",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0391_allowed if {
    input.user.role == "admin"
}
policy_0391_allowed if {
    data.policies.audit.enabled
}
