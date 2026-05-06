package audit.validation.user.deny.utils.policy_0595

# Auto-generated policy 595 (Rego v1 syntax)
# Package: audit.validation.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0595",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0595_allowed = false
policy_0595_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0595_allowed if {
    data.policies.audit.enabled
}
policy_0595_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
