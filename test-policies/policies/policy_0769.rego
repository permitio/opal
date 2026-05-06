package governance.authorization.policy.validate.policy_0769

# Auto-generated policy 769 (Rego v1 syntax)
# Package: governance.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0769",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0769_allowed if {
    input.user.role == "admin"
}
policy_0769_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0769_allowed if {
    data.policies.governance.enabled
}
