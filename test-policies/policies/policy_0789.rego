package audit.monitoring.action.deny.policy_0789

# Auto-generated policy 789 (Rego v1 syntax)
# Package: audit.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0789",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0789_allowed if {
    input.user.role == "admin"
}
policy_0789_allowed if {
    input.user.active
    input.resource.public
}
default policy_0789_allowed = false
policy_0789_allowed if {
    data.policies.audit.enabled
}
