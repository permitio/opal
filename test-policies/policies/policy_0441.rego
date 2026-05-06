package audit.authorization.context.deny.core.policy_0441

# Auto-generated policy 441 (Rego v1 syntax)
# Package: audit.authorization.context.deny.core

# Metadata
metadata := {
    "policy_id": "0441",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0441_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0441_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0441_allowed if {
    input.user.active
    input.resource.public
}
