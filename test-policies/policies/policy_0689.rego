package governance.enforcement.action.allow.logic.policy_0689

# Auto-generated policy 689 (Rego v1 syntax)
# Package: governance.enforcement.action.allow.logic

# Metadata
metadata := {
    "policy_id": "0689",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0689_allowed = false
policy_0689_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
