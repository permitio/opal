package governance.monitoring.resource.check.policy_0300

# Auto-generated policy 300 (Rego v1 syntax)
# Package: governance.monitoring.resource.check

# Metadata
metadata := {
    "policy_id": "0300",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0300_allowed if {
    data.policies.governance.enabled
}
policy_0300_allowed if {
    input.user.role == "admin"
}
default policy_0300_allowed = false
policy_0300_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
