package security.validation.policy.check.utils.policy_0170

# Auto-generated policy 170 (Rego v1 syntax)
# Package: security.validation.policy.check.utils

# Metadata
metadata := {
    "policy_id": "0170",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0170_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0170_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0170_allowed if {
    input.user.active
    input.resource.public
}
policy_0170_allowed if {
    input.user.role == "admin"
}
