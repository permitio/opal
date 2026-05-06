package access.monitoring.resource.allow.policy_0107

# Auto-generated policy 107 (Rego v1 syntax)
# Package: access.monitoring.resource.allow

# Metadata
metadata := {
    "policy_id": "0107",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0107_allowed if {
    data.policies.access.enabled
}
policy_0107_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0107_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
