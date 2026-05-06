package governance.authorization.policy.validate.policy_0483

# Auto-generated policy 483 (Rego v1 syntax)
# Package: governance.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0483",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0483_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0483_allowed if {
    data.policies.governance.enabled
}
policy_0483_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0483_allowed = false
