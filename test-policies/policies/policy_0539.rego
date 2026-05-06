package governance.authorization.context.deny.helpers.policy_0539

# Auto-generated policy 539 (Rego v1 syntax)
# Package: governance.authorization.context.deny.helpers

# Metadata
metadata := {
    "policy_id": "0539",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0539_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0539_allowed = false
policy_0539_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
