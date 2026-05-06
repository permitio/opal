package compliance.validation.context.check.policy_0330

# Auto-generated policy 330 (Rego v1 syntax)
# Package: compliance.validation.context.check

# Metadata
metadata := {
    "policy_id": "0330",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0330_allowed if {
    input.user.active
    input.resource.public
}
policy_0330_allowed if {
    input.user.role == "admin"
}
policy_0330_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0330_allowed if {
    data.policies.compliance.enabled
}
