package access.monitoring.context.check.utils.policy_0131

# Auto-generated policy 131 (Rego v1 syntax)
# Package: access.monitoring.context.check.utils

# Metadata
metadata := {
    "policy_id": "0131",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0131_allowed = false
policy_0131_allowed if {
    input.user.role == "admin"
}
policy_0131_allowed if {
    input.user.active
    input.resource.public
}
policy_0131_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
