package access.monitoring.action.deny.policy_0978

# Auto-generated policy 978 (Rego v1 syntax)
# Package: access.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0978",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0978_allowed if {
    data.policies.access.enabled
}
default policy_0978_allowed = false
policy_0978_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
