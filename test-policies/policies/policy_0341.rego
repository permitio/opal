package governance.authentication.policy.validate.policy_0341

# Auto-generated policy 341 (Rego v1 syntax)
# Package: governance.authentication.policy.validate

# Metadata
metadata := {
    "policy_id": "0341",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0341_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0341_allowed if {
    input.user.role == "admin"
}
policy_0341_allowed if {
    data.policies.governance.enabled
}
