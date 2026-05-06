package governance.monitoring.action.allow.core.policy_0854

# Auto-generated policy 854 (Rego v1 syntax)
# Package: governance.monitoring.action.allow.core

# Metadata
metadata := {
    "policy_id": "0854",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0854_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0854_allowed if {
    input.user.active
    input.resource.public
}
policy_0854_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0854_allowed if {
    data.policies.governance.enabled
}
