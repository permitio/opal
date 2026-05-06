package governance.validation.user.allow.utils.policy_0739

# Auto-generated policy 739 (Rego v1 syntax)
# Package: governance.validation.user.allow.utils

# Metadata
metadata := {
    "policy_id": "0739",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0739_allowed = false
policy_0739_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0739_allowed if {
    input.user.active
    input.resource.public
}
policy_0739_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
