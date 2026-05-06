package governance.authentication.policy.allow.core.policy_0078

# Auto-generated policy 78 (Rego v1 syntax)
# Package: governance.authentication.policy.allow.core

# Metadata
metadata := {
    "policy_id": "0078",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0078_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0078_allowed if {
    input.user.role == "admin"
}
