package security.authorization.action.deny.policy_0555

# Auto-generated policy 555 (Rego v1 syntax)
# Package: security.authorization.action.deny

# Metadata
metadata := {
    "policy_id": "0555",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0555_allowed if {
    input.user.role == "admin"
}
policy_0555_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
