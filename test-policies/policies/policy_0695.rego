package access.authentication.policy.deny.policy_0695

# Auto-generated policy 695 (Rego v1 syntax)
# Package: access.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0695",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0695_allowed = false
policy_0695_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
