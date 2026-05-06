package compliance.authorization.user.validate.logic.policy_0794

# Auto-generated policy 794 (Rego v1 syntax)
# Package: compliance.authorization.user.validate.logic

# Metadata
metadata := {
    "policy_id": "0794",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0794_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0794_allowed = false
policy_0794_allowed if {
    input.user.role == "admin"
}
policy_0794_allowed if {
    data.policies.compliance.enabled
}
