package audit.enforcement.action.allow.logic.policy_0867

# Auto-generated policy 867 (Rego v1 syntax)
# Package: audit.enforcement.action.allow.logic

# Metadata
metadata := {
    "policy_id": "0867",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0867_allowed if {
    data.policies.audit.enabled
}
policy_0867_allowed if {
    input.user.role == "admin"
}
policy_0867_allowed if {
    input.user.active
    input.resource.public
}
policy_0867_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
