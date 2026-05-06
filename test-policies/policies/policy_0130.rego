package governance.validation.user.deny.policy_0130

# Auto-generated policy 130 (Rego v1 syntax)
# Package: governance.validation.user.deny

# Metadata
metadata := {
    "policy_id": "0130",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0130_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0130_allowed if {
    data.policies.governance.enabled
}
policy_0130_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
