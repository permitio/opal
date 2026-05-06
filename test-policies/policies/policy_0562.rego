package governance.monitoring.action.deny.logic.policy_0562

# Auto-generated policy 562 (Rego v1 syntax)
# Package: governance.monitoring.action.deny.logic

# Metadata
metadata := {
    "policy_id": "0562",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0562_allowed if {
    data.policies.governance.enabled
}
policy_0562_allowed if {
    input.user.active
    input.resource.public
}
policy_0562_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0562_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
