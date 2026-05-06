package governance.monitoring.user.allow.core.policy_0643

# Auto-generated policy 643 (Rego v1 syntax)
# Package: governance.monitoring.user.allow.core

# Metadata
metadata := {
    "policy_id": "0643",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0643_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0643_allowed if {
    data.policies.governance.enabled
}
policy_0643_allowed if {
    input.user.active
    input.resource.public
}
default policy_0643_allowed = false
