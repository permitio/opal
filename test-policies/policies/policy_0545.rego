package risk.authentication.policy.deny.policy_0545

# Auto-generated policy 545 (Rego v1 syntax)
# Package: risk.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0545",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0545_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0545_allowed if {
    input.user.role == "admin"
}
