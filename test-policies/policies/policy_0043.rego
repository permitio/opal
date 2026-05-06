package governance.monitoring.context.check.policy_0043

# Auto-generated policy 43 (Rego v1 syntax)
# Package: governance.monitoring.context.check

# Metadata
metadata := {
    "policy_id": "0043",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0043_allowed if {
    data.policies.governance.enabled
}
policy_0043_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0043_allowed = false
policy_0043_allowed if {
    input.user.active
    input.resource.public
}
