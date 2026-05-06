package access.authentication.resource.allow.logic.policy_0764

# Auto-generated policy 764 (Rego v1 syntax)
# Package: access.authentication.resource.allow.logic

# Metadata
metadata := {
    "policy_id": "0764",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0764_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0764_allowed if {
    data.policies.access.enabled
}
policy_0764_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
