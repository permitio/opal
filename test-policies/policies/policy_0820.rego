package audit.enforcement.context.deny.utils.policy_0820

# Auto-generated policy 820 (Rego v1 syntax)
# Package: audit.enforcement.context.deny.utils

# Metadata
metadata := {
    "policy_id": "0820",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0820_allowed if {
    input.user.role == "admin"
}
policy_0820_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0820_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0820_allowed if {
    data.policies.audit.enabled
}
