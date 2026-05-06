package governance.monitoring.resource.check.helpers.policy_0773

# Auto-generated policy 773 (Rego v1 syntax)
# Package: governance.monitoring.resource.check.helpers

# Metadata
metadata := {
    "policy_id": "0773",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0773_allowed if {
    input.user.active
    input.resource.public
}
policy_0773_allowed if {
    data.policies.governance.enabled
}
policy_0773_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0773_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
