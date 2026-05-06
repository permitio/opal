package governance.monitoring.user.check.policy_0817

# Auto-generated policy 817 (Rego v1 syntax)
# Package: governance.monitoring.user.check

# Metadata
metadata := {
    "policy_id": "0817",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0817_allowed if {
    input.user.active
    input.resource.public
}
policy_0817_allowed if {
    data.policies.governance.enabled
}
policy_0817_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
