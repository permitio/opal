package governance.validation.action.deny.utils.policy_0452

# Auto-generated policy 452 (Rego v1 syntax)
# Package: governance.validation.action.deny.utils

# Metadata
metadata := {
    "policy_id": "0452",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0452_allowed if {
    input.user.active
    input.resource.public
}
policy_0452_allowed if {
    data.policies.governance.enabled
}
policy_0452_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
