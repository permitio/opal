package compliance.validation.action.deny.core.policy_0594

# Auto-generated policy 594 (Rego v1 syntax)
# Package: compliance.validation.action.deny.core

# Metadata
metadata := {
    "policy_id": "0594",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0594_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0594_allowed = false
policy_0594_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0594_allowed if {
    input.user.active
    input.resource.public
}
