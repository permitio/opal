package access.monitoring.resource.validate.logic.policy_0546

# Auto-generated policy 546 (Rego v1 syntax)
# Package: access.monitoring.resource.validate.logic

# Metadata
metadata := {
    "policy_id": "0546",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0546_allowed if {
    input.user.active
    input.resource.public
}
default policy_0546_allowed = false
policy_0546_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0546_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
