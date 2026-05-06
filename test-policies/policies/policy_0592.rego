package access.validation.user.allow.core.policy_0592

# Auto-generated policy 592 (Rego v1 syntax)
# Package: access.validation.user.allow.core

# Metadata
metadata := {
    "policy_id": "0592",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0592_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0592_allowed if {
    data.policies.access.enabled
}
default policy_0592_allowed = false
policy_0592_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
