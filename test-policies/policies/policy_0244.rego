package compliance.authorization.policy.deny.policy_0244

# Auto-generated policy 244 (Rego v1 syntax)
# Package: compliance.authorization.policy.deny

# Metadata
metadata := {
    "policy_id": "0244",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0244_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0244_allowed if {
    input.user.role == "admin"
}
