package governance.monitoring.context.validate.utils.policy_0414

# Auto-generated policy 414 (Rego v1 syntax)
# Package: governance.monitoring.context.validate.utils

# Metadata
metadata := {
    "policy_id": "0414",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0414_allowed = false
policy_0414_allowed if {
    input.user.active
    input.resource.public
}
policy_0414_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0414_allowed if {
    data.policies.governance.enabled
}
