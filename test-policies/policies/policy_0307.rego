package governance.enforcement.context.deny.utils.policy_0307

# Auto-generated policy 307 (Rego v1 syntax)
# Package: governance.enforcement.context.deny.utils

# Metadata
metadata := {
    "policy_id": "0307",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0307_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0307_allowed if {
    input.user.role == "admin"
}
policy_0307_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
