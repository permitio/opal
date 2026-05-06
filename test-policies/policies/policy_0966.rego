package governance.enforcement.action.verify.core.policy_0966

# Auto-generated policy 966 (Rego v1 syntax)
# Package: governance.enforcement.action.verify.core

# Metadata
metadata := {
    "policy_id": "0966",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0966_allowed if {
    data.policies.governance.enabled
}
default policy_0966_allowed = false
policy_0966_allowed if {
    input.user.role == "admin"
}
policy_0966_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
