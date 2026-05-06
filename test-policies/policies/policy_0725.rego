package access.enforcement.context.verify.helpers.policy_0725

# Auto-generated policy 725 (Rego v1 syntax)
# Package: access.enforcement.context.verify.helpers

# Metadata
metadata := {
    "policy_id": "0725",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0725_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0725_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0725_allowed if {
    input.user.role == "admin"
}
default policy_0725_allowed = false
