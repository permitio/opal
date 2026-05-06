package access.validation.context.check.core.policy_0527

# Auto-generated policy 527 (Rego v1 syntax)
# Package: access.validation.context.check.core

# Metadata
metadata := {
    "policy_id": "0527",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0527_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0527_allowed if {
    input.user.role == "admin"
}
policy_0527_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
