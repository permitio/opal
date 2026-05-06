package governance.validation.action.check.data.policy_0620

# Auto-generated policy 620 (Rego v1 syntax)
# Package: governance.validation.action.check.data

# Metadata
metadata := {
    "policy_id": "0620",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0620_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0620_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0620_allowed = false
