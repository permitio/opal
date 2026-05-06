package access.monitoring.action.deny.policy_0874

# Auto-generated policy 874 (Rego v1 syntax)
# Package: access.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0874",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0874_allowed if {
    input.user.role == "admin"
}
policy_0874_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0874_allowed = false
