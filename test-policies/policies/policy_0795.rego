package compliance.validation.context.check.utils.policy_0795

# Auto-generated policy 795 (Rego v1 syntax)
# Package: compliance.validation.context.check.utils

# Metadata
metadata := {
    "policy_id": "0795",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0795_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0795_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0795_allowed if {
    input.user.role == "admin"
}
policy_0795_allowed if {
    input.user.active
    input.resource.public
}
