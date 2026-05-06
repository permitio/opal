package governance.monitoring.resource.allow.logic.policy_0897

# Auto-generated policy 897 (Rego v1 syntax)
# Package: governance.monitoring.resource.allow.logic

# Metadata
metadata := {
    "policy_id": "0897",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0897_allowed = false
policy_0897_allowed if {
    data.policies.governance.enabled
}
policy_0897_allowed if {
    input.user.active
    input.resource.public
}
policy_0897_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
