package governance.validation.user.check.utils.policy_0413

# Auto-generated policy 413 (Rego v1 syntax)
# Package: governance.validation.user.check.utils

# Metadata
metadata := {
    "policy_id": "0413",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0413_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0413_allowed if {
    data.policies.governance.enabled
}
policy_0413_allowed if {
    input.user.role == "admin"
}
